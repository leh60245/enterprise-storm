"""
통합 임베딩 서비스 (Unified Embedding Service)

AI와 Ingestion 양쪽에서 동일한 임베딩 모델을 사용하도록 강제합니다.
이를 통해 DB에 저장된 벡터와 검색 시 생성하는 벡터의 일관성을 보장합니다.

지원 프로바이더:
- huggingface: sentence-transformers/paraphrase-multilingual-mpnet-base-v2 (768차원, 기본값)
- openai: text-embedding-3-small (1536차원)

⚠️ 중요: DB에 이미 저장된 임베딩과 동일한 모델을 사용해야 합니다!
프로바이더를 변경하면 기존 데이터 재임베딩이 필요합니다.

사용 예시:
    # 기본 사용 (config에서 provider 자동 결정)
    service = EmbeddingService()
    embedding = service.embed_text("삼성전자 매출 현황")

    # 명시적 프로바이더 지정
    service = EmbeddingService(provider="huggingface")
    embeddings = service.embed_texts(["텍스트1", "텍스트2"])
"""
import os
import logging
from typing import List, Union, Optional, Literal
from abc import ABC, abstractmethod

import numpy as np

from .config import EMBEDDING_CONFIG

logger = logging.getLogger(__name__)


def get_optimal_device() -> str:
    """Return the best available accelerator in priority order: cuda > mps > cpu."""
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class BaseEmbedder(ABC):
    """임베딩 생성기 기본 클래스"""

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """단일 텍스트 임베딩"""
        pass

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """배치 텍스트 임베딩"""
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """임베딩 차원 수 반환"""
        pass


class HuggingFaceEmbedder(BaseEmbedder):
    """
    HuggingFace 기반 임베딩 생성기

    sentence-transformers 모델을 사용하여 768차원 임베딩을 생성합니다.
    GPU가 있으면 자동으로 CUDA를 사용합니다.
    """

    def __init__(
        self,
        model_name: str = None,
        device: str = None,
        batch_size: int = None,
    ):
        self.model_name = model_name or EMBEDDING_CONFIG["hf_model"]
        self.batch_size = batch_size or EMBEDDING_CONFIG["batch_size"]

        # Lazy import (transformers가 무거우므로)
        import torch
        from transformers import AutoTokenizer, AutoModel

        # 디바이스 설정
        if device is None:
            self.device = get_optimal_device()
        else:
            self.device = device
            if self.device.startswith("cuda") and not torch.cuda.is_available():
                logger.warning("Requested CUDA device but CUDA is unavailable. Falling back to CPU.")
                self.device = "cpu"
            elif self.device == "mps" and not torch.backends.mps.is_available():
                logger.warning("Requested MPS device but MPS is unavailable. Falling back to CPU.")
                self.device = "cpu"

        logger.info(f"🔄 Loading HuggingFace embedding model: {self.model_name}")
        logger.info(f"🚀 [System] Embedding Model loaded on: {self.device.upper()}")

        # 모델 로드
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModel.from_pretrained(self.model_name)
        self.model.to(self.device)
        self.model.eval()

        self._dimension = self.model.config.hidden_size
        logger.info(f"✅ Model loaded (dimension: {self._dimension})")

    def get_dimension(self) -> int:
        return self._dimension

    def _mean_pooling(self, model_output, attention_mask):
        """Mean Pooling - attention mask를 고려한 평균"""
        import torch

        token_embeddings = model_output[0]
        input_mask_expanded = (
            attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        )
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(
            input_mask_expanded.sum(1), min=1e-9
        )

    def embed_text(self, text: str) -> List[float]:
        """단일 텍스트 임베딩"""
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """배치 텍스트 임베딩"""
        import torch

        all_embeddings = []

        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i : i + self.batch_size]

            # 토큰화
            encoded_input = self.tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=EMBEDDING_CONFIG["max_length"],
                return_tensors="pt",
            )
            encoded_input = {k: v.to(self.device) for k, v in encoded_input.items()}

            # 임베딩 생성
            with torch.no_grad():
                model_output = self.model(**encoded_input)

            # Mean pooling
            embeddings = self._mean_pooling(
                model_output, encoded_input["attention_mask"]
            )

            # 정규화 (유사도 검색에 유용)
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

            # CPU로 이동 후 리스트 변환
            embeddings = embeddings.cpu().tolist()
            all_embeddings.extend(embeddings)

        return all_embeddings


class OpenAIEmbedder(BaseEmbedder):
    """
    OpenAI API 기반 임베딩 생성기

    text-embedding-3-small 모델을 사용하여 1536차원 임베딩을 생성합니다.
    LiteLLM을 통해 캐싱과 재시도 로직을 지원합니다.
    """

    def __init__(
        self,
        model_name: str = None,
        api_key: str = None,
        max_workers: int = 5,
    ):
        self.model_name = model_name or EMBEDDING_CONFIG["openai_model"]
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.max_workers = max_workers
        self._dimension = EMBEDDING_CONFIG["openai_dimension"]
        self.total_token_usage = 0

        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for OpenAI embeddings. "
                "Please set it in .env or as environment variable."
            )

        # LiteLLM 설정 (캐싱)
        self._setup_litellm()

        logger.info(f"✅ OpenAI Embedder initialized: {self.model_name}")

    def _setup_litellm(self):
        """LiteLLM 캐시 설정"""
        import warnings
        from pathlib import Path

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            if "LITELLM_LOCAL_MODEL_COST_MAP" not in os.environ:
                os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

            import litellm
            from litellm.caching.caching import Cache

            litellm.drop_params = True
            litellm.telemetry = False

            disk_cache_dir = os.path.join(Path.home(), ".storm_local_cache")
            litellm.cache = Cache(disk_cache_dir=disk_cache_dir, type="disk")

            self._litellm = litellm

    def get_dimension(self) -> int:
        return self._dimension

    def _get_single_embedding(self, text: str):
        """단일 텍스트 임베딩 (내부용)"""
        response = self._litellm.embedding(
            model=self.model_name,
            input=text,
            caching=True,
            api_key=self.api_key,
        )
        embedding = response.data[0]["embedding"]
        token_usage = response.get("usage", {}).get("total_tokens", 0)
        return text, embedding, token_usage

    def embed_text(self, text: str) -> List[float]:
        """단일 텍스트 임베딩"""
        _, embedding, tokens = self._get_single_embedding(text)
        self.total_token_usage += tokens
        return embedding

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """배치 텍스트 임베딩 (병렬 처리)"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if len(texts) == 1:
            return [self.embed_text(texts[0])]

        embeddings = []
        total_tokens = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._get_single_embedding, text): text
                for text in texts
            }

            for future in as_completed(futures):
                try:
                    text, embedding, tokens = future.result()
                    embeddings.append((text, embedding, tokens))
                    total_tokens += tokens
                except Exception as e:
                    logger.error(f"Embedding error for text: {futures[future][:50]}...")
                    logger.error(e)
                    # 에러 시 빈 벡터 추가 (차원 유지)
                    embeddings.append((futures[future], [0.0] * self._dimension, 0))

        # 원본 순서대로 정렬
        embeddings.sort(key=lambda x: texts.index(x[0]))
        self.total_token_usage += total_tokens

        return [e[1] for e in embeddings]

    def get_token_usage(self, reset: bool = False) -> int:
        """토큰 사용량 조회"""
        usage = self.total_token_usage
        if reset:
            self.total_token_usage = 0
        return usage


class EmbeddingService:
    """
    통합 임베딩 서비스

    config에서 지정한 provider에 따라 적절한 임베딩 모델을 사용합니다.
    AI와 Ingestion 양쪽에서 이 클래스를 사용하여 일관성을 보장합니다.

    ⚠️ 중요: 반드시 동일한 provider를 사용해야 벡터 검색이 정확합니다!
    """

    _instance: Optional["EmbeddingService"] = None
    _embedder: Optional[BaseEmbedder] = None

    def __new__(cls, provider: str = None, **kwargs):
        """싱글톤 패턴 (동일 provider일 경우)"""
        target_provider = provider or EMBEDDING_CONFIG["provider"]

        if cls._instance is None or cls._instance._provider != target_provider:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False

        return cls._instance

    def __init__(
        self,
        provider: Literal["huggingface", "openai"] = None,
        validate_dimension: bool = True,
        **kwargs,
    ):
        if self._initialized:
            return

        self._provider = provider or EMBEDDING_CONFIG["provider"]

        logger.info(f"🚀 Initializing EmbeddingService with provider: {self._provider}")

        # [안전장치] 차원 불일치 조기 감지
        if validate_dimension:
            try:
                from .config import validate_embedding_dimension_compatibility
                validate_embedding_dimension_compatibility()
            except Exception as e:
                logger.error(f"Dimension validation failed: {e}")
                raise

        if self._provider == "huggingface":
            self._embedder = HuggingFaceEmbedder(**kwargs)
        elif self._provider == "openai":
            self._embedder = OpenAIEmbedder(**kwargs)
        else:
            raise ValueError(
                f"Unsupported embedding provider: {self._provider}. "
                "Supported: 'huggingface', 'openai'"
            )

        self._initialized = True

        # 로드된 모델 차원과 설정 차원 확인
        actual_dim = self._embedder.get_dimension()
        expected_dim = EMBEDDING_CONFIG["dimension"]
        if actual_dim != expected_dim:
            raise RuntimeError(
                f"Model dimension mismatch: loaded model has {actual_dim}D, "
                f"but config expects {expected_dim}D"
            )

    @property
    def provider(self) -> str:
        """현재 프로바이더"""
        return self._provider

    @property
    def dimension(self) -> int:
        """임베딩 차원"""
        return self._embedder.get_dimension()

    def embed_text(self, text: str) -> List[float]:
        """
        단일 텍스트 임베딩

        Args:
            text: 임베딩할 텍스트

        Returns:
            List[float]: 임베딩 벡터
        """
        return self._embedder.embed_text(text)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        배치 텍스트 임베딩

        Args:
            texts: 임베딩할 텍스트 리스트

        Returns:
            List[List[float]]: 임베딩 벡터 리스트
        """
        return self._embedder.embed_texts(texts)

    def embed_to_numpy(self, texts: Union[str, List[str]]) -> np.ndarray:
        """
        NumPy 배열로 임베딩 반환

        Args:
            texts: 단일 텍스트 또는 텍스트 리스트

        Returns:
            np.ndarray: 임베딩 배열 (1D 또는 2D)
        """
        if isinstance(texts, str):
            return np.array(self.embed_text(texts))
        return np.array(self.embed_texts(texts))


# =============================================================================
# 편의 함수
# =============================================================================

def get_embedding_service(provider: str = None) -> EmbeddingService:
    """
    임베딩 서비스 인스턴스 반환 (편의 함수)

    Args:
        provider: 'huggingface' 또는 'openai' (None이면 config에서 결정)

    Returns:
        EmbeddingService: 싱글톤 인스턴스
    """
    return EmbeddingService(provider=provider)


def embed_text(text: str, provider: str = None) -> List[float]:
    """
    단일 텍스트 임베딩 (편의 함수)

    Args:
        text: 임베딩할 텍스트
        provider: 임베딩 프로바이더

    Returns:
        List[float]: 임베딩 벡터
    """
    service = get_embedding_service(provider)
    return service.embed_text(text)


def embed_texts(texts: List[str], provider: str = None) -> List[List[float]]:
    """
    배치 텍스트 임베딩 (편의 함수)

    Args:
        texts: 임베딩할 텍스트 리스트
        provider: 임베딩 프로바이더

    Returns:
        List[List[float]]: 임베딩 벡터 리스트
    """
    service = get_embedding_service(provider)
    return service.embed_texts(texts)


if __name__ == "__main__":
    # 테스트
    print("Testing EmbeddingService...")
    print(f"Provider: {EMBEDDING_CONFIG['provider']}")
    print(f"Dimension: {EMBEDDING_CONFIG['dimension']}")

    service = EmbeddingService()

    test_texts = [
        "삼성전자 2024년 매출 현황",
        "SK하이닉스 반도체 사업 분석",
    ]

    print(f"\nEmbedding {len(test_texts)} texts...")
    embeddings = service.embed_texts(test_texts)

    for i, (text, emb) in enumerate(zip(test_texts, embeddings)):
        print(f"  [{i+1}] '{text[:30]}...' -> [{len(emb)}D] {emb[:3]}...")

    print(f"\n✅ EmbeddingService test passed!")
    print(f"   Provider: {service.provider}")
    print(f"   Dimension: {service.dimension}")


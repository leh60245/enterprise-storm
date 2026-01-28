"""
Cross-Encoder Reranker Service
Path: src/services/reranker_service.py

Role:
- Re-scores retrieved documents using a Cross-Encoder model.
- Provides significantly higher accuracy than vector similarity alone.
"""

import logging
from typing import Any

import torch
from sentence_transformers import CrossEncoder

from src.common.config import AI_CONFIG

logger = logging.getLogger(__name__)

class RerankerService:
    """
    Cross-Encoder 기반 리랭킹 서비스
    권장 모델: 'BAAI/bge-reranker-v2-m3' or 'Dongjin-kr/ko-reranker'
    """

    def __init__(self, model_name: str = None):
        self.model_name = model_name or AI_CONFIG.get("reranker_model", "BAAI/bge-reranker-v2-m3")
        self.device = self._get_optimal_device()

        logger.info(f"🔄 Loading Reranker model: {self.model_name} on {self.device}")

        # 모델 로드 (첫 호출 시 다운로드 발생)
        self.model = CrossEncoder(
            model_name_or_path = self.model_name,
            device=self.device
        )
        logger.info("✅ Reranker model loaded.")

    def _get_optimal_device(self) -> str:
        if torch.cuda.is_available(): return "cuda"
        if torch.backends.mps.is_available(): return "mps"
        return "cpu"

    def rerank(
        self,
        query: str,
        docs: list[dict[str, Any]],
        top_k: int = 10
    ) -> list[dict[str, Any]]:
        """
        문서 리스트를 입력받아 관련성 점수(Score)를 다시 계산하고 정렬합니다.
        
        Args:
            query: 사용자 질문
            docs: 검색된 문서 리스트 (Dict 형태, 'content' 키 필수)
            top_k: 최종 반환할 개수
            
        Returns:
            점수순으로 정렬된 상위 k개 문서 리스트
        """
        if not docs:
            return []

        # Cross-Encoder 입력 쌍 생성: [[query, doc1], [query, doc2], ...]
        # [중요] 'content'가 최종 문맥(표 포함)이어야 정확함
        pairs = [(query, doc.get("content", "")) for doc in docs]

        # 점수 예측
        scores = self.model.predict(pairs)

        # 점수와 함께 문서 업데이트
        for i, doc in enumerate(docs):
            doc["score"] = float(scores[i]) # numpy float -> python float
            doc["source"] = "reranked"     # 출처 태그 갱신 (선택)

        # 점수 내림차순 정렬
        docs.sort(key=lambda x: x["score"], reverse=True)

        # 상위 k개 반환
        return docs[:top_k]

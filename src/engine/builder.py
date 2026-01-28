"""
STORM Engine Builder Module
LLM 설정(LMConfigs)과 검색 엔진(Retrieval Model) 객체를 생성합니다.
"""

import logging
import os

# Knowledge STORM Imports
from knowledge_storm import STORMWikiLMConfigs
from knowledge_storm.lm import AzureOpenAIModel, GoogleModel, OpenAIModel
from knowledge_storm.rm import SerperRM
from knowledge_storm.utils import load_api_key

# Configuration
from src.common.config import AI_CONFIG
from src.engine.retriever import HybridRM, PostgresRM

logger = logging.getLogger(__name__)


def build_lm_configs(provider: str = "openai") -> STORMWikiLMConfigs:
    """
    LLM Provider에 따른 STORMWikiLMConfigs 객체를 생성합니다.

    Args:
        provider: 'openai' 또는 'gemini'
    """
    lm_configs = STORMWikiLMConfigs()

    if provider == "gemini":
        google_api_key = AI_CONFIG.get("google_api_key")
        if not google_api_key:
            raise ValueError("GOOGLE_API_KEY not found in config")

        gemini_kwargs = {"api_key": google_api_key, "temperature": 1.0, "top_p": 0.9}

        # Models
        flash_model = "gemini-2.0-flash-exp"
        pro_model = "gemini-2.0-flash"

        conv_lm = GoogleModel(model=flash_model, max_tokens=2048, **gemini_kwargs)
        article_lm = GoogleModel(model=pro_model, max_tokens=8192, **gemini_kwargs)

        lm_configs.set_conv_simulator_lm(conv_lm)
        lm_configs.set_question_asker_lm(conv_lm)
        lm_configs.set_outline_gen_lm(article_lm)
        lm_configs.set_article_gen_lm(article_lm)
        lm_configs.set_article_polish_lm(article_lm)

        logger.info(f"✓ LM Configured: Google Gemini ({flash_model}, {pro_model})")

    else:  # openai (default)
        openai_api_key = AI_CONFIG.get("openai_api_key")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY not found in config")

        openai_kwargs = {"api_key": openai_api_key, "temperature": 1.0, "top_p": 0.9}

        # Azure OpenAI Support
        api_type = os.getenv("OPENAI_API_TYPE", "openai")
        ModelClass = OpenAIModel if api_type == "openai" else AzureOpenAIModel

        if api_type == "azure":
            openai_kwargs["api_base"] = os.getenv("AZURE_API_BASE")
            openai_kwargs["api_version"] = os.getenv("AZURE_API_VERSION")

        # Models
        gpt_mini = "gpt-4o-mini"
        gpt_4o = "gpt-4o"

        conv_lm = ModelClass(model=gpt_mini, max_tokens=500, **openai_kwargs)
        outline_lm = ModelClass(model=gpt_4o, max_tokens=500, **openai_kwargs)
        article_lm = ModelClass(model=gpt_mini, max_tokens=3000, **openai_kwargs)
        polish_lm = ModelClass(model=gpt_4o, max_tokens=4000, **openai_kwargs)

        lm_configs.set_conv_simulator_lm(conv_lm)
        lm_configs.set_question_asker_lm(conv_lm)
        lm_configs.set_outline_gen_lm(outline_lm)
        lm_configs.set_article_gen_lm(article_lm)
        lm_configs.set_article_polish_lm(polish_lm)

        logger.info(f"✓ LM Configured: OpenAI {api_type} ({gpt_mini}, {gpt_4o})")

    return lm_configs


def build_hybrid_rm(
    company_name: str, top_k: int = 10, min_score: float = 0.5
) -> HybridRM:
    """
    PostgresRM(내부) + SerperRM(외부)을 결합한 HybridRM을 생성합니다.
    """
    # 1. Internal RM (Postgres)
    # 초기화 시 DB 연결은 sync engine을 사용하지만, 검색은 빠릅니다.
    internal_rm = PostgresRM(k=top_k, min_score=min_score)

    logger.info(f"✓ Internal RM initialized (k={top_k})")

    # 2. External RM (Serper)
    serper_key = AI_CONFIG.get("serper_api_key") or load_api_key("SERPER_API_KEY")

    external_rm = SerperRM(serper_search_api_key=serper_key, k=top_k)
    logger.info(f"✓ External RM initialized (k={top_k})")

    # 3. Hybrid RM (Ratio 3:7)
    # 내부 문서보다 최신 웹 정보에 가중치를 조금 더 둠 (조정 가능)
    hybrid_rm = HybridRM(internal_rm, external_rm, internal_k=3, external_k=7)
    logger.info("✓ HybridRM assembled (3:7 ratio)")

    return hybrid_rm

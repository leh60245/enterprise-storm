
import logging

from openai import AsyncOpenAI

from src.common.config import AI_CONFIG
from src.database.models.query_analysis_result import QueryAnalysisResult

# 1. 분석 결과의 구조를 정의 (Pydantic)
logger = logging.getLogger(__name__)


class LLMQueryAnalyzer:
    def __init__(self):
        # 분석용 모델은 싸고 빠른 모델(gpt-4o-mini) 사용 권장
        self.client = AsyncOpenAI(api_key=AI_CONFIG["openai_api_key"])
        self.model = "gpt-4o-mini"

    async def analyze(self, query: str) -> QueryAnalysisResult:
        """
        LLM을 사용하여 사용자 질문을 분석하고 구조화된 데이터를 반환합니다.
        """
        system_prompt = """
        You are an expert Query Analyst for a financial RAG system.
        Analyze the user's question and extract structured information.

        - intent: Determine if the user wants simple facts (factoid) or deep analysis/comparison (analytical).
        - target_companies: Extract company names. Standardize them if possible (e.g., 'SamJeon' -> 'Samsung Electronics').
        - keywords: Extract key terms for vector search database.

        [Guidelines for 'target_companies']
        1. Extract explicit company names (e.g., "SamJeon" -> "Samsung Electronics").
        2. If the user mentions a group/sector (e.g., "Semiconductor leaders", "Competitors of Naver"), 
           USE YOUR KNOWLEDGE to list the top relevant Korean companies (Max 5).
        3. Convert abbreviations to full Korean names if possible (e.g., "Hynix" -> "SK하이닉스").
        4. If no company is mentioned, return an empty list.

        [Guidelines for 'is_competitor_query']
        - Set to True if the user asks for comparison, ranking, or competitors.

        [Output Constraint]
        - target_companies must contain specific company names, not generic terms.
        - Maximum 5 companies.
        """

        try:
            response = await self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                response_format=QueryAnalysisResult,
                temperature=0.0,
                max_tokens=300
            )
            result = response.choices[0].message.parsed
            logger.info(f"🔍 Query Analysis: {result.intent} | Companies: {result.target_companies}")
            return response.choices[0].message.parsed

        except Exception as e:
            logger.error(f"Query Analysis Failed: {e}")
            # 실패 시 기본값 반환 (안전장치)
            return QueryAnalysisResult(
                intent="general",
                target_companies=[],
                is_competitor_query=False,
                keywords=[query]
            )

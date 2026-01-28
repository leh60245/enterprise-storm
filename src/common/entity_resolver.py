"""
Company Entity Resolver using RapidFuzz
Path: src/common/entity_resolver.py

Role:
- Maps user query inputs (e.g., "삼전", "하이닉스", "samsung") to 
  canonical company names in the database (e.g., "삼성전자", "SK하이닉스").
- Uses a hybrid approach: Synonym Dictionary + Fuzzy Matching.
"""

import logging

from rapidfuzz import fuzz, process, utils

logger = logging.getLogger(__name__)

class CompanyEntityResolver:
    """
    기업명 정규화 클래스 (Singleton 권장)
    """

    # 1. 하드코딩된 동의어 사전 (약어 -> 정식 명칭)
    # 현업에서는 이를 DB 별도 테이블(company_synonyms)로 관리하기도 합니다.
    SYNONYM_MAP = {
        # 대기업 약어
        "삼전": "삼성전자",
        "하이닉스": "SK하이닉스",
        "현차": "현대자동차",
        "기아차": "기아",
        "엘지전자": "LG전자",
        "엘전": "LG전자",
        "엘지화학": "LG화학",
        "포스코": "POSCO홀딩스",
        "한전": "한국전력",

        # 영문/한글 혼용
        "samsung": "삼성전자",
        "sk hynix": "SK하이닉스",
        "hynix": "SK하이닉스",
        "lg energy": "LG에너지솔루션",
        "lgensol": "LG에너지솔루션",
        "엔솔": "LG에너지솔루션",
        "naver": "NAVER",
        "kakao": "카카오",

        # 금융권
        "국민은행": "KB금융",
        "신한은행": "신한지주",
        "우리은행": "우리금융지주",
    }

    def __init__(self, db_company_list: list[str] = None):
        """
        Args:
            db_company_list: DB에 실제로 존재하는 기업명 리스트 (Source of Truth)
        """
        self.db_companies = db_company_list or []

        # 검색 속도 향상을 위해 전처리(소문자화 등)된 리스트를 내부적으로 가질 수 있음
        self._processed_companies = [
            utils.default_process(name) for name in self.db_companies
        ]

        logger.info(f"EntityResolver initialized with {len(self.db_companies)} companies.")

    def update_company_list(self, new_list: list[str]):
        """DB 업데이트 시 기업 목록 갱신"""
        self.db_companies = new_list
        self._processed_companies = [
            utils.default_process(name) for name in new_list
        ]
        logger.info(f"EntityResolver updated. Total companies: {len(self.db_companies)}")

    def resolve(self, query: str, threshold: float = 65.0) -> str | None:
        """
        사용자 입력을 정식 기업명으로 변환합니다.

        Algorithm:
        1. Exact Match (정확 일치)
        2. Synonym Match (동의어 사전)
        3. Fuzzy Match (유사도 검색)
        """
        if not query or not self.db_companies:
            return None

        clean_query = query.strip()

        # 1. Exact Match (이미 정확하다면 바로 리턴)
        if clean_query in self.db_companies:
            return clean_query

        # 2. Synonym Match (약어 처리)
        # 띄어쓰기 무시 및 소문자 변환 후 사전 조회
        normalized_key = clean_query.replace(" ", "").lower()
        if normalized_key in self.SYNONYM_MAP:
            canonical = self.SYNONYM_MAP[normalized_key]
            # 사전 결과가 실제 DB 리스트에 있는지 검증 (안전장치)
            if canonical in self.db_companies:
                logger.debug(f"Entity Resolution (Synonym): '{query}' -> '{canonical}'")
                return canonical

        # 3. Fuzzy Match (유사도 검색 - RapidFuzz)
        # extractOne: 가장 유사한 하나를 찾음
        # scorer=fuzz.WRatio: 대소문자, 띄어쓰기, 부분 일치 등을 종합적으로 고려하는 점수
        result = process.extractOne(
            clean_query,
            self.db_companies,
            scorer=fuzz.WRatio,
            score_cutoff=threshold
        )

        if result:
            match_name, score, _ = result
            logger.info(f"Entity Resolution (Fuzzy): '{query}' -> '{match_name}' (Score: {score:.2f})")
            return match_name

        logger.warning(f"Entity Resolution Failed: '{query}' (No match above threshold {threshold})")
        return None

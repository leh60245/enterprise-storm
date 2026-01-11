# src/common/db_utils.py
"""
DB 유틸리티 모듈 (Database Utilities)

DB 조회 관련 헬퍼 함수들을 제공합니다.
AI(Read)와 Ingestion(Write) 양쪽에서 공용으로 사용됩니다.

사용 예시:
    from src.common.db_utils import get_available_companies

    companies = get_available_companies()
    for company in companies:
        print(company)
"""
import logging
from typing import List

from .db_connection import get_db_connection

logger = logging.getLogger(__name__)


def get_available_companies() -> List[str]:
    """
    DB의 Companies 테이블에서 기업명 리스트를 조회하여 반환합니다.

    Returns:
        List[str]: 기업명 리스트 (가나다순 정렬)
                   예: ['SK하이닉스', '삼성전자', '현대자동차', ...]

    Raises:
        SystemExit: DB 연결 실패 시 프로그램 종료

    Example:
        >>> companies = get_available_companies()
        >>> print(companies)
        ['SK하이닉스', '삼성전자', '현대자동차']
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # PostgreSQL 테이블명 대소문자 구분을 위해 쌍따옴표 필수
                cur.execute('SELECT company_name FROM "Companies" ORDER BY company_name ASC')
                rows = cur.fetchall()
                # rows는 튜플 리스트: [(company_name,), ...]
                return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"[Error] 기업 목록 조회 실패: {e}")
        return []


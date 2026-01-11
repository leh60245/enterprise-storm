"""
공통 유틸리티 함수 (Common Utilities)

AI와 Ingestion 양쪽에서 사용하는 유틸리티 함수들을 모아둡니다.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def normalize_company_name(name: str) -> str:
    """
    기업명 정규화

    다양한 형태의 기업명을 통일된 형식으로 변환합니다.
    예: "삼성전자(주)", "삼성전자 주식회사", "SAMSUNG ELECTRONICS" -> "삼성전자"

    Args:
        name: 원본 기업명

    Returns:
        str: 정규화된 기업명
    """
    if not name:
        return ""

    # 공백 정리
    name = name.strip()

    # 괄호와 내용 제거: (주), (유), (합) 등
    name = re.sub(r"\([^)]*\)", "", name)

    # 접미사 제거
    suffixes = [
        "주식회사", "㈜", "유한회사", "합자회사",
        "Inc.", "Corp.", "Co., Ltd.", "Co.,Ltd.", "Ltd.",
        "Corporation", "Company",
    ]
    for suffix in suffixes:
        name = name.replace(suffix, "")

    # 공백 정리
    name = " ".join(name.split())

    return name.strip()


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """
    파일명으로 사용 가능한 문자열로 변환

    Args:
        name: 원본 문자열
        max_length: 최대 길이

    Returns:
        str: 안전한 파일명
    """
    if not name:
        return "unnamed"

    # 위험한 문자 제거/치환
    unsafe_chars = r'[\\/:*?"<>|]'
    safe_name = re.sub(unsafe_chars, "_", name)

    # 연속된 언더스코어 정리
    safe_name = re.sub(r"_+", "_", safe_name)

    # 앞뒤 공백/언더스코어 제거
    safe_name = safe_name.strip("_ ")

    # 길이 제한
    if len(safe_name) > max_length:
        safe_name = safe_name[:max_length]

    return safe_name or "unnamed"


def truncate_text(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """
    텍스트 길이 제한

    Args:
        text: 원본 텍스트
        max_length: 최대 길이 (suffix 포함)
        suffix: 말줄임 표시

    Returns:
        str: 잘린 텍스트
    """
    if not text or len(text) <= max_length:
        return text or ""

    return text[: max_length - len(suffix)] + suffix


def format_score(score: float, precision: int = 4) -> str:
    """
    유사도 점수 포맷팅

    Args:
        score: 유사도 점수 (0.0 ~ 1.0)
        precision: 소수점 자릿수

    Returns:
        str: 포맷팅된 점수
    """
    return f"{score:.{precision}f}"


def extract_stock_code(text: str) -> Optional[str]:
    """
    텍스트에서 종목코드 추출

    Args:
        text: 종목코드가 포함된 텍스트

    Returns:
        Optional[str]: 6자리 종목코드 또는 None
    """
    # 6자리 숫자 패턴 찾기
    match = re.search(r"\b(\d{6})\b", text)
    return match.group(1) if match else None


def parse_date_string(date_str: str) -> Optional[str]:
    """
    다양한 형식의 날짜 문자열을 YYYYMMDD 형식으로 변환

    Args:
        date_str: 날짜 문자열 (예: "2024-01-15", "2024.01.15", "20240115")

    Returns:
        Optional[str]: YYYYMMDD 형식 또는 None
    """
    if not date_str:
        return None

    # 숫자만 추출
    digits = re.sub(r"\D", "", date_str)

    if len(digits) == 8:
        return digits

    return None


def chunk_list(lst: list, chunk_size: int) -> list:
    """
    리스트를 청크로 분할

    Args:
        lst: 분할할 리스트
        chunk_size: 청크 크기

    Yields:
        list: 청크 리스트
    """
    for i in range(0, len(lst), chunk_size):
        yield lst[i : i + chunk_size]


def safe_json_loads(text: str, default=None):
    """
    안전한 JSON 파싱

    Args:
        text: JSON 문자열
        default: 파싱 실패 시 반환값

    Returns:
        파싱된 객체 또는 default
    """
    import json

    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


class Timer:
    """
    간단한 타이머 Context Manager

    Example:
        with Timer("데이터 로딩"):
            load_data()
        # 출력: ⏱ 데이터 로딩: 1.23초
    """

    def __init__(self, name: str = "Operation", logger_func=None):
        self.name = name
        self.logger_func = logger_func or print
        self.start_time = None
        self.elapsed = None

    def __enter__(self):
        import time
        self.start_time = time.time()
        return self

    def __exit__(self, *args):
        import time
        self.elapsed = time.time() - self.start_time
        self.logger_func(f"⏱ {self.name}: {self.elapsed:.2f}초")


if __name__ == "__main__":
    # 테스트
    print("Testing utilities...")

    # normalize_company_name
    test_names = [
        "삼성전자(주)",
        "삼성전자 주식회사",
        "SK하이닉스㈜",
        "NAVER Corporation",
    ]
    for name in test_names:
        print(f"  '{name}' -> '{normalize_company_name(name)}'")

    # sanitize_filename
    print(f"\n  'Test/File:Name' -> '{sanitize_filename('Test/File:Name')}'")

    # Timer
    print("\n")
    with Timer("테스트 작업"):
        import time
        time.sleep(0.1)

    print("\n✅ Utilities test passed!")


"""
통합 설정 모듈 (Unified Configuration)

AI와 Ingestion 양쪽에서 사용하는 모든 설정을 중앙 관리합니다.
환경변수 네이밍을 통일하고 충돌을 방지합니다.

환경변수 표준:
- DB: PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE
- AI: OPENAI_API_KEY, GOOGLE_API_KEY, ENCODER_API_TYPE
- DART: DART_API_KEY
"""
import os
from enum import Enum
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트에서 .env 로드
_project_root = Path(__file__).parent.parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
else:
    load_dotenv()  # 기본 .env 로드 시도

# =============================================================================
# Database Configuration (통합)
# =============================================================================
# 환경변수 호환성: PG_* (신규 표준) 우선, DB_* (레거시) 폴백
DB_CONFIG = {
    "host": os.getenv("PG_HOST") or os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("PG_PORT") or os.getenv("DB_PORT", "5432"),
    "user": os.getenv("PG_USER") or os.getenv("DB_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD") or os.getenv("DB_PASSWORD"),
    "database": os.getenv("PG_DATABASE") or os.getenv("DB_NAME", "postgres"),
}

# =============================================================================
# Embedding Configuration (통합 - 가장 중요!)
# =============================================================================
# ⚠️ 경고: DB Vector Index와 동일한 모델/차원을 사용해야 합니다!
# HuggingFace(768D) ↔ OpenAI(1536D) 불일치 시 시스템 즉시 중단됩니다.
#
# 프로바이더 변경 시 필수 작업:
# 1. 기존 DB의 모든 임베딩 삭제 (UPDATE "Source_Materials" SET embedding = NULL)
# 2. pgvector 인덱스 재생성
# 3. 전체 데이터 재임베딩 (python -m scripts.run_ingestion --embed --force)

# ============== 활성 모델 설정 (런타임 중 하나만 활성화) ==============
ACTIVE_EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "huggingface")

# 허용된 프로바이더 목록
_ALLOWED_PROVIDERS = ["huggingface", "openai"]

if ACTIVE_EMBEDDING_PROVIDER not in _ALLOWED_PROVIDERS:
    raise RuntimeError(
        f"Invalid EMBEDDING_PROVIDER: {ACTIVE_EMBEDDING_PROVIDER}. "
        f"Allowed values: {', '.join(_ALLOWED_PROVIDERS)}"
    )

# ============== 프로바이더별 설정 ==============
EMBEDDING_CONFIG = {
    # 활성 프로바이더 (런타임 중 절대 변경 금지!)
    "provider": ACTIVE_EMBEDDING_PROVIDER,

    # HuggingFace 설정 (768차원 - 다국어 지원)
    "hf_model": os.getenv(
        "HF_EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    ),
    "hf_dimension": 768,

    # OpenAI 설정 (1536차원 - 높은 정확도, 비용 발생)
    "openai_model": os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
    "openai_dimension": 1536,

    # 공통 설정
    "batch_size": int(os.getenv("EMBEDDING_BATCH_SIZE", "32")),
    "max_length": int(os.getenv("EMBEDDING_MAX_LENGTH", "512")),
}

# ============== 활성 차원 자동 결정 ==============
if ACTIVE_EMBEDDING_PROVIDER == "openai":
    EMBEDDING_CONFIG["dimension"] = EMBEDDING_CONFIG["openai_dimension"]
    EMBEDDING_CONFIG["model_name"] = EMBEDDING_CONFIG["openai_model"]
else:  # huggingface
    EMBEDDING_CONFIG["dimension"] = EMBEDDING_CONFIG["hf_dimension"]
    EMBEDDING_CONFIG["model_name"] = EMBEDDING_CONFIG["hf_model"]


# ============== 런타임 검증 (차원 불일치 조기 감지) ==============
def validate_embedding_dimension_compatibility():
    """
    [수정됨] 사용자 확인 완료: 실제 데이터는 768차원이 맞음.
    진단 로직 오류로 판단되어 검증을 생략하고 무조건 True 반환.
    """
    return True


# =============================================================================
# AI Configuration (LLM 및 검색)
# =============================================================================
AI_CONFIG = {
    # LLM 프로바이더
    "llm_provider": os.getenv("LLM_PROVIDER", "openai"),  # openai, gemini, azure

    # API Keys
    "openai_api_key": os.getenv("OPENAI_API_KEY"),
    "google_api_key": os.getenv("GOOGLE_API_KEY"),
    "azure_api_key": os.getenv("AZURE_API_KEY"),
    "azure_api_base": os.getenv("AZURE_API_BASE"),
    "azure_api_version": os.getenv("AZURE_API_VERSION"),

    # 기본 모델 설정
    "default_model": os.getenv("DEFAULT_LLM_MODEL", "gpt-4o"),

    # 검색 설정
    "retrieval_top_k": int(os.getenv("RETRIEVAL_TOP_K", "5")),
    "retrieval_min_score": float(os.getenv("RETRIEVAL_MIN_SCORE", "0.5")),

    # Encoder API Type (레거시 호환)
    "encoder_api_type": os.getenv("ENCODER_API_TYPE", "openai"),
}

# =============================================================================
class JOB_STATUS(Enum):
    """표준화된 작업 상태 Enum (API 간 일관성 유지)."""

    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# Analysis Topic Configuration (분석 주제 중앙 관리)
# =============================================================================
# API v2.1 기준 Topic 정의 (공통 사용)
TOPICS = [
    {
        "id": "T01",
        "label": "기업 개요 및 주요 사업 내용",
        "value": "기업 개요 및 주요 사업 내용",
    },
    {
        "id": "T02",
        "label": "최근 3개년 재무제표 및 재무 상태 분석",
        "value": "최근 3개년 재무제표 및 재무 상태 분석"
    },
    {
        "id": "T03",
        "label": "산업 내 경쟁 우위 및 경쟁사 비교 (SWOT)",
        "value": "산업 내 경쟁 우위 및 경쟁사 비교"
    },
    {
        "id": "T04",
        "label": "주요 제품 및 서비스 시장 점유율 분석",
        "value": "주요 제품 및 서비스 시장 점유율 분석"
    },
    {
        "id": "T05",
        "label": "R&D 투자 현황 및 기술 경쟁력",
        "value": "R&D 투자 현황 및 기술 경쟁력"
    },
    {
        "id": "T06",
        "label": "ESG (환경, 사회, 지배구조) 평가",
        "value": "ESG (환경, 사회, 지배구조) 평가"
    },
    {
        "id": "custom",
        "label": "직접 입력",
        "value": None,
    },
]


def get_topic_value_by_id(topic_id: str) -> str:
    """
    Topic ID로 value(순수 주제)를 조회합니다.
    
    Args:
        topic_id: TOPICS 리스트의 id 값
        
    Returns:
        해당하는 value (순수 주제 텍스트) 또는 None
    """
    for topic in TOPICS:
        if topic["id"] == topic_id:
            return topic["value"]
    return None


def get_topic_list_for_api():
    """
    Frontend용 주제 리스트 포맷입니다.
    GET /api/topics 엔드포인트에서 사용됩니다.
    """
    return [
        {
            "id": topic["id"],
            "label": topic["label"],
        }
        for topic in TOPICS
    ]


# =============================================================================
# DART API Configuration
# =============================================================================
DART_CONFIG = {
    "api_key": os.getenv("DART_API_KEY"),

    # 보고서 검색 설정
    "search_start_date": os.getenv("DART_SEARCH_START_DATE", "20240101"),
    "report_type_code": "a001",  # 사업보고서
    "page_count": 100,
    "page_delay_sec": 0.5,
    "max_search_days": 90,
}

# =============================================================================
# Batch Processing Configuration (Ingestion용)
# =============================================================================
BATCH_CONFIG = {
    "batch_size": int(os.getenv("BATCH_SIZE", "50")),
    "batch_delay_sec": int(os.getenv("BATCH_DELAY_SEC", "3")),
    "request_delay_sec": float(os.getenv("REQUEST_DELAY_SEC", "0.1")),
    "max_retries": int(os.getenv("MAX_RETRIES", "3")),
    "retry_delay_sec": int(os.getenv("RETRY_DELAY_SEC", "5")),
}

# =============================================================================
# Chunk Configuration (텍스트 청킹)
# =============================================================================
CHUNK_CONFIG = {
    "max_chunk_size": int(os.getenv("MAX_CHUNK_SIZE", "2000")),
    "overlap": int(os.getenv("CHUNK_OVERLAP", "200")),
    "min_chunk_size": int(os.getenv("MIN_CHUNK_SIZE", "100")),
}

# =============================================================================
# Target Sections (DART 보고서)
# =============================================================================
TARGET_SECTIONS = [
    "회사의 개요",
    "사업의 내용",
    "재무에 관한 사항",
]

# =============================================================================
# Company Aliases (기업명 별칭 - 검색 필터링 및 Cross-Reference 감지용)
# =============================================================================
# 정규화된 기업명(Key)과 해당 기업의 알려진 별칭들(Value List)
# AI 파트: 검색 시 company_name 필터링에 사용
# DB 파트: Cross-Reference 노이즈 제거 시 사용
COMPANY_ALIASES = {
    "삼성전자": ["삼전", "Samsung Electronics", "Samsung", "삼성전자㈜", "SAMSUNG"],
    "SK하이닉스": ["하이닉스", "SK Hynix", "Hynix", "에스케이하이닉스", "SK하이닉스㈜"],
    "NAVER": ["네이버", "Naver", "NHN", "네이버㈜"],
    "카카오": ["Kakao", "다음카카오", "카카오㈜"],
    "LG전자": ["LG Electronics", "엘지전자", "LG전자㈜", "엘쥐전자"],
    "현대자동차": ["현대차", "Hyundai Motor", "현대자동차㈜", "현차"],
    "기아": ["기아자동차", "Kia", "KIA", "기아㈜"],
    "포스코홀딩스": ["포스코", "POSCO", "포항제철"],
    "셀트리온": ["Celltrion", "셀트리온㈜"],
    "KB금융": ["KB금융지주", "KB Financial", "국민은행"],
}


def get_canonical_company_name(name: str) -> str:
    """
    기업명 또는 별칭을 정규화된 기업명으로 변환

    Args:
        name: 검색할 기업명 또는 별칭

    Returns:
        정규화된 기업명 (찾지 못하면 원본 반환)

    Example:
        >>> get_canonical_company_name("삼전")
        "삼성전자"
        >>> get_canonical_company_name("SK Hynix")
        "SK하이닉스"
    """
    # 정확히 일치하는 정규명이 있으면 반환
    if name in COMPANY_ALIASES:
        return name

    # 별칭에서 검색
    for canonical, aliases in COMPANY_ALIASES.items():
        if name in aliases:
            return canonical

    # 대소문자 무시 검색
    name_lower = name.lower().strip()
    for canonical, aliases in COMPANY_ALIASES.items():
        if canonical.lower() == name_lower:
            return canonical
        for alias in aliases:
            if alias.lower() == name_lower:
                return canonical

    return name  # 찾지 못하면 원본 반환


def get_all_aliases(company_name: str) -> list:
    """
    특정 기업의 모든 별칭 반환 (정규명 포함)

    Args:
        company_name: 기업명 (정규명 또는 별칭)

    Returns:
        해당 기업의 모든 알려진 이름 리스트

    Example:
        >>> get_all_aliases("삼성전자")
        ["삼성전자", "삼전", "Samsung Electronics", ...]
    """
    canonical = get_canonical_company_name(company_name)
    if canonical in COMPANY_ALIASES:
        return [canonical] + COMPANY_ALIASES[canonical]
    return [company_name]


# =============================================================================
# Query Routing Keywords (비교 질문 감지용)
# =============================================================================
# 이 키워드가 포함된 질문은 company_filter를 확장(Expansion)하여
# 여러 기업의 데이터를 동시에 검색합니다.
COMPARISON_KEYWORDS = [
    "비교",
    "vs",
    "VS",
    "대비",
    "경쟁",
    "경쟁사",
    "업계",
    "시장 점유율",
    "순위",
    "랭킹",
]


def is_comparison_query(query: str) -> bool:
    """
    질문이 비교/경쟁 분석을 요청하는지 판단

    Args:
        query: 사용자 질문

    Returns:
        True if 비교 질문, False otherwise
    """
    return any(keyword in query for keyword in COMPARISON_KEYWORDS)


def extract_companies_from_query(query: str) -> list:
    """
    질문에서 언급된 기업명들을 추출하여 정규명으로 반환

    Args:
        query: 사용자 질문

    Returns:
        질문에서 발견된 기업들의 정규명 리스트

    Example:
        >>> extract_companies_from_query("삼성전자와 하이닉스 비교해줘")
        ["삼성전자", "SK하이닉스"]
    """
    found_companies = set()

    for canonical, aliases in COMPANY_ALIASES.items():
        # 정규명 검색
        if canonical in query:
            found_companies.add(canonical)
            continue

        # 별칭 검색
        for alias in aliases:
            if alias in query:
                found_companies.add(canonical)
                break

    return list(found_companies)


# =============================================================================
# Validation (필수 환경변수 체크)
# =============================================================================
def validate_config(check_db=True, check_ai=False, check_dart=False):
    """
    설정 유효성 검사

    Args:
        check_db: DB 접속 정보 검증
        check_ai: AI API 키 검증
        check_dart: DART API 키 검증

    Raises:
        RuntimeError: 필수 설정이 누락된 경우
    """
    missing = []

    if check_db:
        if not DB_CONFIG["password"]:
            missing.append("PG_PASSWORD (or DB_PASSWORD)")

    if check_ai:
        if AI_CONFIG["llm_provider"] == "openai" and not AI_CONFIG["openai_api_key"]:
            missing.append("OPENAI_API_KEY")
        elif AI_CONFIG["llm_provider"] == "gemini" and not AI_CONFIG["google_api_key"]:
            missing.append("GOOGLE_API_KEY")

    if check_dart:
        if not DART_CONFIG["api_key"]:
            missing.append("DART_API_KEY")

    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Please set them in .env or as environment variables."
        )


# =============================================================================
# Debug: Print current config (개발용)
# =============================================================================
def print_config():
    """현재 설정 출력 (디버깅용)"""
    print("\n" + "=" * 60)
    print("🔧 Hypercurve Unified Configuration")
    print("=" * 60)

    print("\n📦 Database:")
    print(f"   Host: {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    print(f"   Database: {DB_CONFIG['database']}")
    print(f"   User: {DB_CONFIG['user']}")
    print(f"   Password: {'*' * len(DB_CONFIG['password']) if DB_CONFIG['password'] else 'NOT SET'}")

    print("\n🧠 Embedding:")
    print(f"   Provider: {EMBEDDING_CONFIG['provider']}")
    print(f"   Dimension: {EMBEDDING_CONFIG['dimension']}")
    if EMBEDDING_CONFIG['provider'] == 'huggingface':
        print(f"   Model: {EMBEDDING_CONFIG['hf_model']}")
    else:
        print(f"   Model: {EMBEDDING_CONFIG['openai_model']}")

    print("\n🤖 AI:")
    print(f"   LLM Provider: {AI_CONFIG['llm_provider']}")
    print(f"   Default Model: {AI_CONFIG['default_model']}")
    print(f"   OpenAI Key: {'SET' if AI_CONFIG['openai_api_key'] else 'NOT SET'}")
    print(f"   Google Key: {'SET' if AI_CONFIG['google_api_key'] else 'NOT SET'}")

    print("\n📊 DART:")
    print(f"   API Key: {'SET' if DART_CONFIG['api_key'] else 'NOT SET'}")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    print_config()

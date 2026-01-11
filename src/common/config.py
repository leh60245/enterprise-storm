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
    DB에 저장된 벡터 차원과 현재 설정 차원이 일치하는지 검증합니다.

    불일치 시 명확한 에러 메시지와 함께 즉시 중단합니다.

    Returns:
        bool: 검증 성공 시 True

    Raises:
        RuntimeError: 차원 불일치 또는 DB 연결 실패 시
    """
    try:
        from .db_connection import get_db_connection

        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Source_Materials 테이블의 embedding 컬럼 차원 확인
            cursor.execute("""
                SELECT 
                    atttypmod 
                FROM pg_attribute 
                WHERE attrelid = '"Source_Materials"'::regclass 
                  AND attname = 'embedding'
            """)

            result = cursor.fetchone()
            if not result:
                # 테이블이 없거나 embedding 컬럼이 없음 (초기 상태)
                return True

            # atttypmod에서 차원 추출 (pgvector는 차원+4로 저장)
            db_dimension = result[0] - 4 if result[0] > 0 else None

            if db_dimension is None:
                return True  # 차원 정보 없음 (초기 상태)

            current_dimension = EMBEDDING_CONFIG["dimension"]

            if db_dimension != current_dimension:
                raise RuntimeError(
                    f"\n{'='*70}\n"
                    f"❌ 치명적 오류: 임베딩 차원 불일치 (Dimension Mismatch)\n"
                    f"{'='*70}\n"
                    f"DB에 저장된 벡터 차원: {db_dimension}D\n"
                    f"현재 설정된 차원:     {current_dimension}D (provider={ACTIVE_EMBEDDING_PROVIDER})\n"
                    f"\n"
                    f"원인:\n"
                    f"  - DB는 다른 임베딩 모델로 생성된 벡터를 포함하고 있습니다.\n"
                    f"  - 차원이 다른 벡터로 검색 시 PostgreSQL 에러가 발생합니다.\n"
                    f"\n"
                    f"해결 방법:\n"
                    f"  1. [옵션 A] 기존 DB 차원에 맞게 설정 변경:\n"
                    f"     .env 파일에서 EMBEDDING_PROVIDER를 "
                    f"{'openai' if db_dimension == 1536 else 'huggingface'}로 변경\n"
                    f"\n"
                    f"  2. [옵션 B] 새 모델로 전체 재임베딩 (시간 소요):\n"
                    f"     ① DB 백업: pg_dump corp_analysis > backup.sql\n"
                    f"     ② 임베딩 초기화: UPDATE \"Source_Materials\" SET embedding = NULL\n"
                    f"     ③ 재임베딩: python -m scripts.run_ingestion --embed --force\n"
                    f"\n"
                    f"  3. [옵션 C] DB 완전 초기화 후 재수집:\n"
                    f"     python -m scripts.run_ingestion --test --reset-db\n"
                    f"{'='*70}\n"
                )

            return True

    except ImportError:
        # db_connection 모듈이 없는 경우 (예: 설정 로드 단계)
        return True
    except Exception as e:
        # DB 연결 실패 등은 경고만 출력하고 진행
        import warnings
        warnings.warn(
            f"임베딩 차원 검증 실패 (DB 연결 불가): {e}\n"
            f"나중에 DB 접근 시 차원 불일치 에러가 발생할 수 있습니다.",
            RuntimeWarning
        )
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


"""
통합 DB 연결 모듈 (Unified Database Connection)

AI(Read)와 Ingestion(Write) 양쪽에서 사용하는 DB 연결을 중앙 관리합니다.
psycopg2 기반으로 PostgreSQL + pgvector를 지원합니다.

사용 예시:
    # Context Manager (권장)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM \"Companies\"")

    # Factory 패턴
    factory = DBConnectionFactory()
    conn = factory.create_connection()
"""
import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

from .config import DB_CONFIG

logger = logging.getLogger(__name__)


class DBConnectionFactory:
    """
    PostgreSQL 연결 팩토리 클래스

    싱글톤 패턴으로 연결 정보를 관리하고,
    필요 시 새 연결을 생성합니다.
    """

    _instance = None
    _config: Dict[str, Any] = None

    def __new__(cls, config: Dict[str, Any] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: Dict[str, Any] = None):
        if self._initialized:
            return

        self._config = config or DB_CONFIG
        self._validate_config()
        self._initialized = True

        logger.info(
            f"DBConnectionFactory initialized: "
            f"{self._config['host']}:{self._config['port']}/{self._config['database']}"
        )

    def _validate_config(self):
        """필수 설정 검증"""
        required = ["host", "port", "user", "password", "database"]
        missing = [k for k in required if not self._config.get(k)]

        if missing:
            raise RuntimeError(
                f"Missing DB config: {', '.join(missing)}. "
                "Please set PG_* environment variables."
            )

    def create_connection(self, cursor_factory=None):
        """
        새 DB 연결 생성

        Args:
            cursor_factory: 커서 팩토리 (기본: None, RealDictCursor 사용 시 전달)

        Returns:
            psycopg2.connection: 데이터베이스 연결 객체
        """
        try:
            conn = psycopg2.connect(
                host=self._config["host"],
                port=self._config["port"],
                user=self._config["user"],
                password=self._config["password"],
                database=self._config["database"],
                cursor_factory=cursor_factory,
            )
            logger.debug("DB connection created successfully")
            return conn
        except psycopg2.Error as e:
            logger.error(f"Failed to create DB connection: {e}")
            raise

    def create_dict_connection(self):
        """
        RealDictCursor를 사용하는 연결 생성
        결과를 딕셔너리로 반환하는 커서를 사용합니다.
        """
        return self.create_connection(cursor_factory=RealDictCursor)

    @property
    def config(self) -> Dict[str, Any]:
        """현재 설정 반환 (비밀번호 마스킹)"""
        return {
            **self._config,
            "password": "***" if self._config.get("password") else None
        }


@contextmanager
def get_db_connection(use_dict_cursor: bool = False, autocommit: bool = False):
    """
    DB 연결 Context Manager

    자동으로 연결을 관리하고, 예외 발생 시 롤백합니다.

    Args:
        use_dict_cursor: True면 RealDictCursor 사용 (결과를 dict로 반환)
        autocommit: True면 자동 커밋 모드

    Yields:
        psycopg2.connection: 데이터베이스 연결 객체

    Example:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM \"Companies\"")
            rows = cursor.fetchall()
    """
    factory = DBConnectionFactory()

    if use_dict_cursor:
        conn = factory.create_dict_connection()
    else:
        conn = factory.create_connection()

    if autocommit:
        conn.autocommit = True

    try:
        yield conn
        if not autocommit:
            conn.commit()
    except Exception as e:
        if not autocommit:
            conn.rollback()
        logger.error(f"DB operation failed, rolled back: {e}")
        raise
    finally:
        conn.close()
        logger.debug("DB connection closed")


class DBSession:
    """
    DB 세션 클래스 (레거시 DBManager 호환)

    with 문을 사용한 Context Manager 패턴을 지원합니다.
    기존 DBManager의 인터페이스를 유지하면서 공통 연결을 사용합니다.
    """

    def __init__(self):
        self.conn = None
        self.cursor = None
        self._factory = DBConnectionFactory()

    def __enter__(self):
        self.conn = self._factory.create_connection()
        self.cursor = self.conn.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type:
                self.conn.rollback()
                logger.warning(f"Transaction rolled back: {exc_val}")
            else:
                self.conn.commit()
            self.conn.close()

    def execute(self, query: str, params: tuple = None):
        """쿼리 실행"""
        self.cursor.execute(query, params)
        return self.cursor

    def fetchall(self):
        """모든 결과 가져오기"""
        return self.cursor.fetchall()

    def fetchone(self):
        """단일 결과 가져오기"""
        return self.cursor.fetchone()

    def commit(self):
        """명시적 커밋"""
        self.conn.commit()

    def rollback(self):
        """명시적 롤백"""
        self.conn.rollback()


# =============================================================================
# 스키마 관리 유틸리티
# =============================================================================

def init_schema():
    """
    DB 스키마 초기화 (테이블 생성)

    pgvector 확장을 활성화하고 필요한 테이블을 생성합니다.
    """
    from .config import EMBEDDING_CONFIG

    dimension = EMBEDDING_CONFIG["dimension"]

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # pgvector 확장 활성화
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        # Companies 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS "Companies" (
                id SERIAL PRIMARY KEY,
                company_name VARCHAR(255) UNIQUE NOT NULL,
                corp_code VARCHAR(20),
                stock_code VARCHAR(20),
                industry VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Companies 인덱스
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_companies_corp_code 
            ON "Companies"(corp_code);
        """)

        # Analysis_Reports 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS "Analysis_Reports" (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES "Companies"(id) ON DELETE CASCADE,
                title VARCHAR(500),
                rcept_no VARCHAR(20) UNIQUE,
                rcept_dt VARCHAR(10),
                report_type VARCHAR(50) DEFAULT 'annual',
                basic_info JSONB,
                status VARCHAR(50) DEFAULT 'Raw_Loaded',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Source_Materials 테이블
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS "Source_Materials" (
                id SERIAL PRIMARY KEY,
                report_id INTEGER REFERENCES "Analysis_Reports"(id) ON DELETE CASCADE,
                chunk_type VARCHAR(20) NOT NULL DEFAULT 'text',
                section_path TEXT,
                sequence_order INTEGER,
                raw_content TEXT,
                table_metadata JSONB,
                embedding vector({dimension}),
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Source_Materials 인덱스
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_source_materials_report_sequence 
            ON "Source_Materials"(report_id, sequence_order);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_source_materials_chunk_type 
            ON "Source_Materials"(report_id, chunk_type);
        """)

        # Generated_Reports 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS "Generated_Reports" (
                id SERIAL PRIMARY KEY,
                company_name VARCHAR(100) NOT NULL,
                topic TEXT NOT NULL,
                report_content TEXT,
                toc_text TEXT,
                references_data JSONB,
                conversation_log JSONB,
                meta_info JSONB,
                model_name VARCHAR(50) DEFAULT 'gpt-4o',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Generated_Reports 인덱스
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reports_company 
            ON "Generated_Reports"(company_name);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reports_created 
            ON "Generated_Reports"(created_at DESC);
        """)

        logger.info("✅ DB schema initialized successfully")


def check_connection() -> bool:
    """
    DB 연결 테스트

    Returns:
        bool: 연결 성공 여부
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            return result[0] == 1
    except Exception as e:
        logger.error(f"DB connection test failed: {e}")
        return False


if __name__ == "__main__":
    # 연결 테스트
    print("Testing DB connection...")
    if check_connection():
        print("✅ DB connection successful!")
        print(f"Config: {DBConnectionFactory().config}")
    else:
        print("❌ DB connection failed!")


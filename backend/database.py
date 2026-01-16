"""
Database Connection Module
Task ID: FEAT-DB-001-PostgresIntegration

이 모듈은 PostgreSQL 데이터베이스 연결을 관리합니다.
- 환경 변수 기반 설정 (.env 파일)
- Connection timeout 5초 (서버 hang 방지)
- RealDictCursor를 통한 딕셔너리 형식 반환
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional

# 프로젝트 루트의 .env 파일 로드 (backend/.env)
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# ============================================================
# Database Connection Configuration
# ============================================================

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "1234"),
}

# ✅ 모듈 로드 시 DB에 접근하지 않음 (서버 시작 지연 방지)
print(f"🔧 DB Config: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")


# ============================================================
# Connection Management Functions
# ============================================================

def get_db_connection():
    """
    PostgreSQL 데이터베이스 연결을 생성하여 반환합니다.
    
    Returns:
        psycopg2.connection: 데이터베이스 연결 객체
        
    Raises:
        psycopg2.Error: 데이터베이스 연결 실패 시
        
    Usage:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM table")
        finally:
            conn.close()
    
    ⚠️ 중요: 사용 후 반드시 conn.close()를 호출해야 합니다.
    ⚠️ timeout 5초로 설정하여 서버 hang 방지
    """
    try:
        conn = psycopg2.connect(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            database=DB_CONFIG["database"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            connect_timeout=5  # 5초 timeout
        )
        return conn
    except psycopg2.Error as e:
        print(f"❌ DB Error: {type(e).__name__}: {str(e)}")
        raise


@contextmanager
def get_db_cursor(cursor_factory=None):
    """
    Context manager를 사용한 안전한 DB 커서 관리.
    자동으로 conn.close() 호출.
    
    Args:
        cursor_factory: Cursor 팩토리 (예: RealDictCursor)
        
    Usage:
        with get_db_cursor(RealDictCursor) as cur:
            cur.execute("SELECT * FROM table")
            result = cur.fetchall()
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=cursor_factory)
        yield cursor
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Database Error: {e}")
        raise
    finally:
        if conn:
            conn.close()


# ============================================================
# High-level Query Functions
# ============================================================

def query_report_by_id(report_id: int) -> Optional[Dict[str, Any]]:
    """
    ID로 리포트 조회 (Generated_Reports 테이블에서)
    
    Args:
        report_id: 리포트 ID
        
    Returns:
        딕셔너리 형식의 리포트 데이터 또는 None
    """
    try:
        with get_db_cursor(RealDictCursor) as cur:
            cur.execute("""
                SELECT id, company_name, topic, report_content,
                       toc_text, references_data, meta_info,
                       model_name, created_at
                FROM "Generated_Reports"
                WHERE id = %s
            """, (report_id,))
            
            result = cur.fetchone()
            return result
            
    except Exception as e:
        print(f"❌ Error querying report {report_id}: {e}")
        raise


def query_all_reports(limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
    """
    모든 리포트 조회 (최신순)
    
    Args:
        limit: 조회 개수 (기본값: 10)
        offset: 시작 위치 (기본값: 0)
        
    Returns:
        리포트 목록 (딕셔너리 배열)
    """
    try:
        with get_db_cursor(RealDictCursor) as cur:
            cur.execute("""
                SELECT id, company_name, topic, model_name, created_at
                FROM "Generated_Reports"
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            
            results = cur.fetchall()
            return results
            
    except Exception as e:
        print(f"❌ Error querying reports: {e}")
        raise


def test_connection():
    """
    데이터베이스 연결 테스트
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            result = cur.fetchone()
            print(f"✅ Database connection test passed!")
            print(f"   PostgreSQL: {result[0][:50]}...")
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Database connection test failed: {e}")
        return False


# ============================================================
# Module Test
# ============================================================

if __name__ == "__main__":
    print("\n[Database Module Test]\n")
    print("1. Testing database connection...")
    test_connection()

"""
Database Connection Module
Task ID: FEAT-DB-001-PostgresIntegration

이 모듈은 PostgreSQL 데이터베이스 연결을 관리합니다.
- 환경 변수 기반 설정 (.env 파일)
- Connection timeout 5초 (서버 hang 방지)
- RealDictCursor를 통한 딕셔너리 형식 반환
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from typing import Dict, Any, List, Optional

# ✅ [REFACTOR] Use centralized config from src.common
from src.common.config import DB_CONFIG

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


def query_reports_with_filters(
    *,
    company_name: Optional[str] = None,
    topic: Optional[str] = None,
    sort_by: str = "created_at",
    order: str = "desc",
    limit: int = 10,
    offset: int = 0,
) -> Dict[str, Any]:
    """리포트 조회 (필터/정렬 지원)"""

    allowed_sort = {
        "created_at": '"created_at"',
        "company_name": '"company_name"',
        "topic": '"topic"',
        "model_name": '"model_name"',
    }
    sort_clause = allowed_sort.get(sort_by, '"created_at"')
    order_clause = "ASC" if order and order.lower() == "asc" else "DESC"

    where_clause = []
    params: List[Any] = []

    if company_name:
        where_clause.append('"company_name" = %s')
        params.append(company_name)
    if topic:
        where_clause.append('"topic" ILIKE %s')
        params.append(f"%{topic}%")

    where_sql = f"WHERE {' AND '.join(where_clause)}" if where_clause else ""

    try:
        with get_db_cursor(RealDictCursor) as cur:
            count_sql = f"""
                SELECT COUNT(*) AS total
                FROM "Generated_Reports"
                {where_sql}
            """
            cur.execute(count_sql, params)
            total_row = cur.fetchone()
            total = total_row["total"] if total_row else 0

            query_sql = f"""
                SELECT id AS report_id, company_name, topic, model_name, created_at
                FROM "Generated_Reports"
                {where_sql}
                ORDER BY {sort_clause} {order_clause}
                LIMIT %s OFFSET %s
            """
            cur.execute(query_sql, [*params, limit, offset])
            results = cur.fetchall()

            return {
                "total": total,
                "reports": results,
            }

    except Exception as e:
        print(f"❌ Error querying reports: {e}")
        raise


def query_companies_from_db() -> List[Dict[str, Any]]:
    """
    Companies 테이블에서 기업 ID와 이름을 조회한다.
    
    Returns:
        List[Dict]: [{'id': 1, 'company_name': '삼성전자'}, ...]
    """
    # 1순위: Companies 테이블 (마스터 데이터)
    sql = 'SELECT id, company_name FROM "Companies" ORDER BY company_name ASC'
    
    try:
        with get_db_cursor(RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            
            # 데이터가 있으면 그대로 반환 (RealDictCursor 덕분에 이미 Dict 형태임)
            if rows:
                return rows
                
    except Exception as e:
        print(f"⚠️ Company query failed: {e}")

    # 2순위: 데이터가 없을 경우 (개발용 Fallback)
    # 주의: 이 경우 id는 가상으로 부여하거나 비워둡니다.
    print("⚠️ No companies found in DB, returning fallback data.")
    return [
        {"id": 1, "company_name": "SK하이닉스"},
        {"id": 2, "company_name": "현대엔지니어링"},
        {"id": 3, "company_name": "NAVER"},
        {"id": 4, "company_name": "삼성전자"},
        {"id": 5, "company_name": "LG전자"},
    ]


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

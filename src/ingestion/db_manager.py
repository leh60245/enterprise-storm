"""
DB Manager 모듈 - PostgreSQL 데이터베이스 연결 및 CRUD 작업 관리
"""
import psycopg2
from psycopg2.extras import Json
from typing import Optional, List, Dict

# [통합 아키텍처] 공통 모듈에서 설정 가져오기
from src.common.config import DB_CONFIG, EMBEDDING_CONFIG


class DBManager:
    """
    PostgreSQL 데이터베이스 연결 및 데이터 조작을 담당하는 클래스
    Context Manager 패턴을 지원하여 with 구문 사용이 가능합니다.
    """

    def __init__(self):
        self.conn = None
        self.cursor = None
        self.db_config = DB_CONFIG

    def __enter__(self):
        """Context Manager 진입: DB 연결"""
        try:
            self.conn = psycopg2.connect(**self.db_config)
            self.cursor = self.conn.cursor()
            return self
        except psycopg2.Error as e:
            print(f"❌ DB 연결 실패: {e}")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context Manager 종료: 연결 해제"""
        if self.conn:
            if exc_type:
                self.conn.rollback()
                print(f"⚠️ 트랜잭션 롤백: {exc_val}")
            else:
                self.conn.commit()
            self.conn.close()

    # ==================== 스키마 관리 ====================

    def reset_db(self):
        """[주의] 기존 테이블을 삭제하고 새로 만듭니다"""
        try:
            print("💥 기존 테이블 삭제 중...")
            self.cursor.execute('DROP TABLE IF EXISTS "Generated_Reports" CASCADE;')
            self.cursor.execute('DROP TABLE IF EXISTS "Source_Materials" CASCADE;')
            self.cursor.execute('DROP TABLE IF EXISTS "Analysis_Reports" CASCADE;')
            self.cursor.execute('DROP TABLE IF EXISTS "Companies" CASCADE;')
            self.conn.commit()
            print("🧹 DB 초기화 완료")
            self.init_db()
        except Exception as e:
            self.conn.rollback()
            print(f"❌ DB 리셋 실패: {e}")
            raise

    def init_db(self):
        """DB 테이블 생성 (존재하지 않는 경우에만)"""
        try:
            # pgvector 확장 활성화
            self.cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # 1. 기업 정보 테이블
            self.cursor.execute("""
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

            # corp_code 인덱스 추가
            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_companies_corp_code 
                ON "Companies"(corp_code);
            """)

            # 2. 분석 리포트 테이블
            self.cursor.execute(f"""
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

            # 3. 원천 데이터 테이블 (순차적 블록 처리 - 텍스트/테이블 통합)
            self.cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS "Source_Materials" (
                    id SERIAL PRIMARY KEY,
                    report_id INTEGER REFERENCES "Analysis_Reports"(id) ON DELETE CASCADE,
                    chunk_type VARCHAR(20) NOT NULL DEFAULT 'text',
                    section_path TEXT,
                    sequence_order INTEGER,
                    raw_content TEXT,
                    table_metadata JSONB,
                    embedding vector({EMBEDDING_CONFIG['dimension']}),
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 인덱스 추가 (순차적 블록 처리 지원)
            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_source_materials_report_sequence 
                ON "Source_Materials"(report_id, sequence_order);
            """)

            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_source_materials_chunk_type 
                ON "Source_Materials"(report_id, chunk_type);
            """)

            # 4. AI 생성 리포트 테이블 (company_id FK 추가)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS "Generated_Reports" (
                    id SERIAL PRIMARY KEY,
                    company_name VARCHAR(100) NOT NULL,
                    company_id INTEGER REFERENCES "Companies"(id) ON DELETE CASCADE,
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
            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_reports_company 
                ON "Generated_Reports"(company_name);
            """)
            
            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_reports_company_id 
                ON "Generated_Reports"(company_id);
            """)

            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_reports_created 
                ON "Generated_Reports"(created_at DESC);
            """)

            self.conn.commit()
            print("🛠️ DB 테이블 생성/확인 완료")
        except Exception as e:
            self.conn.rollback()
            print(f"❌ DB 생성 실패: {e}")
            raise

    # ==================== 기업 관리 ====================

    def insert_company(
        self,
        name: str,
        corp_code: str,
        stock_code: str,
        industry: Optional[str] = None
    ) -> Optional[int]:
        """
        기업 정보를 UPSERT 방식으로 처리합니다.

        Returns:
            int: Company ID
        """
        try:
            sql = """
                INSERT INTO "Companies" (company_name, corp_code, stock_code, industry)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (company_name) 
                DO UPDATE SET 
                    corp_code = EXCLUDED.corp_code,
                    stock_code = EXCLUDED.stock_code,
                    industry = COALESCE(EXCLUDED.industry, "Companies".industry),
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id;
            """
            self.cursor.execute(sql, (name, corp_code, stock_code, industry))
            result = self.cursor.fetchone()
            self.conn.commit()
            return result[0] if result else None
        except Exception as e:
            self.conn.rollback()
            print(f"❌ 기업 등록 실패 ({name}): {e}")
            raise

    def get_company_by_corp_code(self, corp_code: str) -> Optional[Dict]:
        """법인코드로 기업 조회"""
        sql = 'SELECT id, company_name, corp_code, stock_code FROM "Companies" WHERE corp_code = %s'
        self.cursor.execute(sql, (corp_code,))
        row = self.cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "company_name": row[1],
                "corp_code": row[2],
                "stock_code": row[3]
            }
        return None

    # ==================== 리포트 관리 ====================

    def insert_report(self, company_id: int, info: Dict) -> Optional[int]:
        """
        분석 리포트 헤더 생성 (중복 시 기존 ID 반환)

        Args:
            company_id: 기업 ID
            info: 보고서 정보 dict (title, rcept_no, rcept_dt 등)

        Returns:
            int: Report ID
        """
        # 중복 체크
        check_sql = 'SELECT id FROM "Analysis_Reports" WHERE rcept_no = %s'
        self.cursor.execute(check_sql, (info.get('rcept_no'),))
        exist = self.cursor.fetchone()
        if exist:
            return exist[0]

        try:
            sql = """
                INSERT INTO "Analysis_Reports" 
                (company_id, title, rcept_no, rcept_dt, report_type, basic_info, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'Raw_Loaded')
                RETURNING id;
            """
            self.cursor.execute(sql, (
                company_id,
                info.get('title'),
                info.get('rcept_no'),
                info.get('rcept_dt'),
                info.get('report_type', 'annual'),
                Json(info)
            ))
            self.conn.commit()
            return self.cursor.fetchone()[0]
        except Exception as e:
            self.conn.rollback()
            print(f"❌ 리포트 생성 실패: {e}")
            raise

    def update_report_status(self, report_id: int, status: str):
        """리포트 상태 업데이트"""
        sql = 'UPDATE "Analysis_Reports" SET status = %s WHERE id = %s'
        self.cursor.execute(sql, (status, report_id))
        self.conn.commit()

    def get_report_by_rcept_no(self, rcept_no: str) -> Optional[Dict]:
        """접수번호로 리포트 조회"""
        sql = 'SELECT id, company_id, title, status FROM "Analysis_Reports" WHERE rcept_no = %s'
        self.cursor.execute(sql, (rcept_no,))
        row = self.cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "company_id": row[1],
                "title": row[2],
                "status": row[3]
            }
        return None

    # ==================== 원천 데이터 관리 ====================

    def insert_source_material(
        self,
        report_id: int,
        content: str,
        chunk_type: str = 'text',
        section_path: Optional[str] = None,
        sequence_order: Optional[int] = None,
        table_metadata: Optional[Dict] = None,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        순차적 블록 저장 (텍스트 또는 테이블)

        Args:
            report_id: 리포트 ID
            content: 텍스트 내용 또는 Markdown 테이블
            chunk_type: 'text' 또는 'table'
            section_path: 섹션 경로 (예: "II. 사업의 내용 > 1. 사업의 개요")
            sequence_order: 문서 내 순서 (0부터 시작)
            table_metadata: 테이블 메타데이터 (단위, 제목 등)
            embedding: 임베딩 벡터 (선택)
            metadata: 추가 메타데이터 (선택)
        """
        try:
            sql = """
                INSERT INTO "Source_Materials" 
                (report_id, chunk_type, section_path, sequence_order, 
                 raw_content, table_metadata, embedding, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """
            # metadata 복사 후 추가 정보 병합 (원본 보호)
            meta = dict(metadata) if metadata else {}
            meta["length"] = len(content)
            meta["has_embedding"] = embedding is not None

            self.cursor.execute(sql, (
                report_id,
                chunk_type,
                section_path,
                sequence_order,
                content,
                Json(table_metadata) if table_metadata else None,
                embedding,
                Json(meta)
            ))
            self.conn.commit()
            return True
        except Exception as e:
            self.conn.rollback()
            print(f"❌ 원천 데이터 저장 실패: {e}")
            return False

    def insert_materials_batch(
        self,
        report_id: int,
        blocks: List[Dict],
        metadata: Optional[Dict] = None
    ) -> int:
        """
        여러 블록을 배치로 저장 (순차적 블록 처리)

        Args:
            report_id: 리포트 ID
            blocks: 블록 데이터 리스트 (각 블록은 chunk_type, section_path, content 포함)
            metadata: 공통 메타데이터

        Returns:
            int: 저장된 블록 수
            
        Raises:
            Exception: 블록 저장 실패 시 즉시 예외 전파 (Silent Failure 방지)
        """
        count = 0
        for idx, block in enumerate(blocks):
            success = self.insert_source_material(
                report_id=report_id,
                content=block.get('content', ''),
                chunk_type=block.get('chunk_type', 'text'),
                section_path=block.get('section_path'),
                sequence_order=block.get('sequence_order', idx),
                table_metadata=block.get('table_metadata'),
                metadata=metadata
            )
            # 🔴 FIX: Silent Failure 방지 - 실패 시 즉시 예외 발생
            if not success:
                error_msg = f"블록 저장 실패 (report_id={report_id}, block_idx={idx}, type={block.get('chunk_type')})"
                print(f"❌ {error_msg}")
                raise Exception(error_msg)
            count += 1
        return count

    def get_materials_by_report(self, report_id: int) -> List[Dict]:
        """리포트의 모든 원천 데이터 조회 (순서대로)"""
        sql = """
            SELECT id, chunk_type, section_path, sequence_order, 
                   raw_content, table_metadata, metadata 
            FROM "Source_Materials" 
            WHERE report_id = %s 
            ORDER BY sequence_order
        """
        self.cursor.execute(sql, (report_id,))
        rows = self.cursor.fetchall()
        return [
            {
                "id": row[0],
                "chunk_type": row[1],
                "section_path": row[2],
                "sequence_order": row[3],
                "raw_content": row[4],
                "table_metadata": row[5],
                "metadata": row[6]
            }
            for row in rows
        ]

    # ==================== AI 생성 리포트 관리 ====================

    def insert_generated_report(
        self,
        company_name: str,
        topic: str,
        report_content: str,
        toc_text: str,
        references_data: dict,
        conversation_log: dict,
        meta_info: dict,
        model_name: str = 'gpt-4o',
        company_id: Optional[int] = None
    ) -> Optional[int]:
        """
        AI가 생성한 리포트를 저장합니다.

        Args:
            company_name: 기업명
            topic: 리포트 주제
            report_content: 리포트 본문 (Markdown 등)
            toc_text: 목차 텍스트
            references_data: 참고 자료 데이터 (JSON)
            conversation_log: 대화 로그 (JSON)
            meta_info: 메타 정보 (JSON)
            model_name: 사용된 AI 모델명 (기본: gpt-4o)
            company_id: 기업 ID (FK, 선택) - None이면 company_name으로 자동 조회

        Returns:
            int: 생성된 리포트 ID (성공 시) 또는 None (실패 시)
        """
        try:
            # company_id가 없으면 company_name으로 조회
            if company_id is None:
                company = self.get_company_by_name(company_name)
                if company:
                    company_id = company['id']
            
            sql = """
                INSERT INTO "Generated_Reports" (
                    company_name, company_id, topic, report_content, toc_text,
                    references_data, conversation_log, meta_info, model_name
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """

            self.cursor.execute(
                sql,
                (
                    company_name,
                    company_id,
                    topic,
                    report_content,
                    toc_text,
                    Json(references_data),
                    Json(conversation_log),
                    Json(meta_info),
                    model_name
                )
            )

            result = self.cursor.fetchone()
            self.conn.commit()

            if result:
                report_id = result[0]
                print(f"✅ AI 생성 리포트 저장 완료 (ID: {report_id})")
                return report_id
            else:
                return None

        except Exception as e:
            self.conn.rollback()
            print(f"❌ AI 리포트 저장 실패 ({company_name} - {topic}): {e}")
            return None

    # ==================== 유틸리티 ====================

    def get_stats(self) -> Dict:
        """DB 통계 조회"""
        stats = {}

        self.cursor.execute('SELECT COUNT(*) FROM "Companies"')
        stats['companies'] = self.cursor.fetchone()[0]

        self.cursor.execute('SELECT COUNT(*) FROM "Analysis_Reports"')
        stats['reports'] = self.cursor.fetchone()[0]

        self.cursor.execute('SELECT COUNT(*) FROM "Source_Materials"')
        stats['materials'] = self.cursor.fetchone()[0]

        self.cursor.execute('''
            SELECT COUNT(*) FROM "Source_Materials" 
            WHERE embedding IS NOT NULL
        ''')
        stats['embedded_materials'] = self.cursor.fetchone()[0]

        self.cursor.execute('SELECT COUNT(*) FROM "Generated_Reports"')
        stats['generated_reports'] = self.cursor.fetchone()[0]

        return stats


"""
PostgreSQL Vector Search Connector for Enterprise STORM

이 모듈은 PostgreSQL DB의 Source_Materials 테이블에서
pgvector를 활용한 벡터 유사도 검색을 수행합니다.

Database Schema (Source_Materials):
    - id (PK): Integer
    - report_id (FK): Integer (Analysis_Reports 참조)
    - chunk_type: VARCHAR ('text', 'table', 'noise_merged')
    - section_path: TEXT (섹션 경로)
    - sequence_order: INTEGER (문서 내 등장 순서)
    - raw_content: TEXT (본문 또는 Markdown 표)
    - embedding: vector(768) (pgvector)
    - metadata: JSONB (메타데이터)
        - has_merged_meta: boolean (병합된 메타 정보 포함 여부)
        - is_noise_dropped: boolean (noise_merged 타입일 때만 존재)
        - has_embedding: boolean
        - context_injected: boolean
        - length: integer

Author: Enterprise STORM Team
Updated: 2026-01-11 - 통합 아키텍처 (src.common 모듈 사용)
"""

import os
import logging
from typing import List, Dict

import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor

# [통합 아키텍처] 공통 모듈 사용
try:
    from src.common.db_connection import DBConnectionFactory
    from src.common.embedding import EmbeddingService
    from src.common.config import DB_CONFIG
    _USE_UNIFIED_MODULES = True
except ImportError:
    # 폴백: 기존 방식 (독립 실행 시)
    from sentence_transformers import SentenceTransformer
    _USE_UNIFIED_MODULES = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PostgresConnector:
    """
    PostgreSQL 벡터 검색 커넥터

    DART 보고서 데이터가 저장된 PostgreSQL DB에서
    벡터 유사도 검색을 수행하고 STORM 호환 포맷으로 결과를 반환합니다.

    Attributes:
        conn: psycopg2 데이터베이스 연결 객체
        model: SentenceTransformer 임베딩 모델

    Example:
        >>> connector = PostgresConnector()
        >>> results = connector.search("삼성전자 매출 현황", top_k=5)
        >>> for r in results:
        ...     print(r['title'], r['score'])
    """

    def __init__(self):
        """
        PostgresConnector 초기화

        [통합 아키텍처] src.common 모듈 사용 가능 시 통합 DB 연결 및 임베딩 서비스 사용.
        독립 실행 시 기존 환경변수 방식으로 폴백.

        Required Environment Variables (폴백 시):
            - PG_HOST: PostgreSQL 호스트 주소
            - PG_PORT: PostgreSQL 포트 (기본값: 5432)
            - PG_USER: 데이터베이스 사용자명
            - PG_PASSWORD: 데이터베이스 비밀번호
            - PG_DATABASE: 데이터베이스 이름

        Raises:
            RuntimeError: DB 연결 정보가 누락되었거나 연결에 실패한 경우
        """
        if _USE_UNIFIED_MODULES:
            # [통합 아키텍처] 공통 모듈 사용
            try:
                factory = DBConnectionFactory()
                self.conn = factory.create_connection()
                logger.info(f"Successfully connected via unified DBConnectionFactory")

                # [안전장치] 차원 검증 먼저 실행
                try:
                    from src.common.config import validate_embedding_dimension_compatibility
                    validate_embedding_dimension_compatibility()
                except Exception as e:
                    logger.error(f"❌ Dimension validation failed: {e}")
                    raise

                # 통합 임베딩 서비스 사용
                self._embedding_service = EmbeddingService(validate_dimension=False)  # 이미 검증했으므로 skip
                self.model = None  # 레거시 호환
                logger.info(f"Using unified EmbeddingService (provider: {self._embedding_service.provider})")
            except Exception as e:
                raise RuntimeError(f"Failed to initialize via unified modules: {e}")
        else:
            # [폴백] 기존 환경변수 방식
            self._embedding_service = None

            # 환경변수에서 DB 접속 정보 로드
            self.host = os.environ.get("PG_HOST")
            self.port = os.environ.get("PG_PORT", "5432")
            self.user = os.environ.get("PG_USER")
            self.password = os.environ.get("PG_PASSWORD")
            self.database = os.environ.get("PG_DATABASE")

            # 필수 환경변수 검증
            missing_vars = []
            if not self.host:
                missing_vars.append("PG_HOST")
            if not self.user:
                missing_vars.append("PG_USER")
            if not self.password:
                missing_vars.append("PG_PASSWORD")
            if not self.database:
                missing_vars.append("PG_DATABASE")

            if missing_vars:
                raise RuntimeError(
                    f"Missing required environment variables: {', '.join(missing_vars)}. "
                    "Please set them in secrets.toml or as environment variables."
                )

            # DB 연결 설정
            try:
                self.conn = psycopg2.connect(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    database=self.database
                )
                logger.info(f"Successfully connected to PostgreSQL database: {self.database}")
            except psycopg2.Error as e:
                raise RuntimeError(f"Failed to connect to PostgreSQL: {e}")

            # 임베딩 모델 로드 (폴백)
            try:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')
                logger.info("Successfully loaded SentenceTransformer model (fallback mode)")
            except Exception as e:
                raise RuntimeError(f"Failed to load SentenceTransformer model: {e}")

    def _embed_query(self, query: str) -> np.ndarray:
        """
        쿼리 문자열을 벡터로 변환

        Args:
            query: 검색 쿼리 문자열

        Returns:
            임베딩 벡터 (numpy 배열)
        """
        if self._embedding_service is not None:
            # [통합 아키텍처] 공통 임베딩 서비스 사용
            embedding = self._embedding_service.embed_text(query)
            return np.array(embedding)
        else:
            # [폴백] SentenceTransformer 직접 사용
            embedding = self.model.encode(query, convert_to_numpy=True)
            return embedding

    def _fetch_window_context(
            self,
            table_rows: List[Dict],
            window_size: int = 1
    ) -> Dict[tuple, Dict[str, str]]:
        """
        테이블 타입 행들에 대해 Sliding Window Context를 조회

        sequence_order 기준으로 앞뒤 window_size만큼의 인접 청크를 가져와
        하나의 Context Block으로 구성합니다.

        Note:
            DB 업데이트로 인해 noise_merged 타입인 청크는 검색되지 않으므로,
            Sequence가 비어있을 경우 자동으로 건너뛰게 됩니다.

        Args:
            table_rows: chunk_type='table'인 검색 결과 행들
            window_size: 앞뒤로 가져올 청크 수 (기본값: 1)

        Returns:
            {(report_id, sequence_order): {'prev': prev_text, 'next': next_text}} 형태의 딕셔너리
        """
        if not table_rows:
            return {}

        context_map = {}

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            for row in table_rows:
                report_id = row['report_id']
                current_seq = row['sequence_order']

                context_data = {'prev': None, 'next': None}

                # 이전 청크 조회 (sequence_order - 1 ~ sequence_order - window_size)
                for offset in range(1, window_size + 1):
                    prev_seq = current_seq - offset
                    if prev_seq < 0:
                        continue

                    cur.execute("""
                        SELECT raw_content, section_path, chunk_type
                        FROM "Source_Materials"
                        WHERE report_id = %s AND sequence_order = %s
                    """, (report_id, prev_seq))

                    prev_row = cur.fetchone()
                    if prev_row and prev_row['chunk_type'] != 'noise_merged':
                        if context_data['prev'] is None:
                            context_data['prev'] = prev_row['raw_content']
                        else:
                            # 더 앞의 컨텍스트를 앞에 붙임
                            context_data['prev'] = prev_row['raw_content'] + "\n\n" + context_data['prev']

                # 다음 청크 조회 (sequence_order + 1 ~ sequence_order + window_size)
                for offset in range(1, window_size + 1):
                    next_seq = current_seq + offset

                    cur.execute("""
                        SELECT raw_content, section_path, chunk_type
                        FROM "Source_Materials"
                        WHERE report_id = %s AND sequence_order = %s
                    """, (report_id, next_seq))

                    next_row = cur.fetchone()
                    if next_row and next_row['chunk_type'] != 'noise_merged':
                        if context_data['next'] is None:
                            context_data['next'] = next_row['raw_content']
                        else:
                            # 더 뒤의 컨텍스트를 뒤에 붙임
                            context_data['next'] = str(context_data['next']) + "\n\n" + next_row['raw_content']

                context_map[(report_id, current_seq)] = context_data

        return context_map

    def search(self, query: str, top_k: int = 5, window_size: int = 1) -> List[Dict]:
        """
        벡터 유사도 검색 수행

        입력된 쿼리를 벡터화하여 PostgreSQL의 Source_Materials 테이블에서
        가장 유사한 문서들을 검색합니다.

        chunk_type이 'table'인 경우 Sliding Window Context를 적용하여
        앞뒤 인접 청크를 함께 가져와 하나의 Context Block으로 구성합니다.

        has_merged_meta가 true인 경우 LLM에게 병합된 메타 정보(단위, 범례 등)가
        문단 끝에 포함되어 있음을 알리는 안내 문구를 추가합니다.

        Args:
            query: 검색 쿼리 문자열
            top_k: 반환할 최대 결과 수 (기본값: 5)
            window_size: Table 청크의 앞뒤로 가져올 인접 청크 수 (기본값: 1)

        Returns:
            STORM 호환 포맷의 검색 결과 리스트
            [
                {
                    "content": "검색된 본문 내용",
                    "title": "섹션 경로 (section_path)",
                    "url": "dart_report_{report_id}",
                    "score": 0.85,  # 코사인 유사도 (1 - distance)
                    "has_merged_meta": true/false  # 병합된 메타 정보 포함 여부
                },
                ...
            ]

        Raises:
            psycopg2.Error: 데이터베이스 쿼리 실행 실패 시
        """
        # 쿼리 임베딩 생성
        query_embedding = self._embed_query(query)

        # numpy 배열을 PostgreSQL vector 형식 문자열로 변환
        embedding_str = "[" + ",".join(map(str, query_embedding.tolist())) + "]"

        results = []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 벡터 유사도 검색 SQL 실행
                # pgvector의 <=> 연산자: 코사인 거리 (0에 가까울수록 유사)
                # chunk_type이 'noise_merged'인 청크는 검색에서 제외
                cur.execute("""
                    SELECT 
                        id,
                        raw_content, 
                        section_path, 
                        chunk_type, 
                        report_id, 
                        sequence_order,
                        metadata,
                        COALESCE((metadata->>'has_merged_meta')::boolean, false) as has_merged_meta,
                        COALESCE((metadata->>'is_noise_dropped')::boolean, false) as is_noise_dropped,
                        (embedding <=> %s::vector) as distance
                    FROM "Source_Materials"
                    WHERE chunk_type != 'noise_merged'
                    ORDER BY distance ASC
                    LIMIT %s
                """, (embedding_str, top_k))

                rows = cur.fetchall()

                if not rows:
                    logger.warning(f"No results found for query: {query}")
                    return []

                # 🚨 is_noise_dropped 플래그 검증 (정상적으로 필터링되었는지 확인)
                noise_dropped_rows = [row for row in rows if row.get('is_noise_dropped', False)]
                if noise_dropped_rows:
                    logger.error(
                        f"[ALERT] {len(noise_dropped_rows)} rows with is_noise_dropped=true found in search results! "
                        "This should not happen - please check the Vector DB indexing."
                    )

                # Sliding Window Context: table 타입 행들에 대해 앞뒤 청크 조회
                table_rows = [row for row in rows if row['chunk_type'] == 'table']
                context_map = self._fetch_window_context(table_rows, window_size=window_size)

                # 결과 가공 및 STORM 포맷 변환
                for row in rows:
                    content = row['raw_content']
                    has_merged = row.get('has_merged_meta', False)

                    # chunk_type이 'table'인 경우 Sliding Window Context 적용
                    if row['chunk_type'] == 'table':
                        context_key = (row['report_id'], row['sequence_order'])
                        if context_key in context_map:
                            ctx = context_map[context_key]
                            prev_text = ctx.get('prev')
                            next_text = ctx.get('next')

                            # 앞뒤 문맥을 조합하여 Context Block 구성
                            if prev_text:
                                content = f"[이전 문맥]\n{prev_text}\n\n[표 데이터]\n{content}"
                            else:
                                content = f"[섹션: {row['section_path']}]\n\n[표 데이터]\n{content}"

                            if next_text:
                                content = f"{content}\n\n[이후 문맥]\n{next_text}"
                        else:
                            # 문맥이 없으면 section_path를 문맥으로 사용
                            content = f"[섹션: {row['section_path']}]\n\n[표 데이터]\n{content}"

                    # has_merged_meta가 true인 경우 LLM 안내 문구 추가
                    if has_merged:
                        content = (
                            "[참고: 이 문단 끝에 병합된 메타 정보(단위, 범례, 기준일자 등)가 포함되어 있습니다. "
                            "수치 해석 시 반드시 확인하세요.]\n\n" + content
                        )

                    # 코사인 거리를 유사도 점수로 변환 (1 - distance)
                    # distance가 0이면 score=1 (완전 일치)
                    score = 1 - float(row['distance'])

                    # URL에 고유 ID를 포함하여 각 검색 결과가 별도의 출처로 인식되도록 함
                    # 형식: dart_report_{report_id}_chunk_{id}
                    unique_url = f"dart_report_{row['report_id']}_chunk_{row['id']}"

                    results.append({
                        "content": content,
                        "title": row['section_path'],
                        "url": unique_url,
                        "score": score,
                        "has_merged_meta": has_merged
                    })

                logger.info(f"Found {len(results)} results for query: {query}")

                return results

        except psycopg2.Error as e:
            logger.error(f"Database query failed: {e}")
            self.conn.rollback()  # [핵심] 트랜잭션 복구!
            return []  # 빈 리스트 반환 (프로그램 중단 방지)

        except Exception as e:
            logger.error(f"Unexpected error in search: {e}")
            return []


    def close(self):
        """데이터베이스 연결 종료"""
        if self.conn:
            self.conn.close()
            logger.info("PostgreSQL connection closed")

    def __enter__(self):
        """Context manager 진입"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager 종료 시 연결 해제"""
        self.close()
        return False


# 테스트 코드
if __name__ == "__main__":
    import sys
    import toml

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


    def load_api_key(toml_file_path):
        """secrets.toml에서 환경변수 로드 (테스트용 로컬 함수)"""
        try:
            with open(toml_file_path, "r") as file:
                data = toml.load(file)
            for key, value in data.items():
                os.environ[key] = str(value)
        except FileNotFoundError:
            print(f"File not found: {toml_file_path}", file=sys.stderr)
        except toml.TomlDecodeError:
            print(f"Error decoding TOML file: {toml_file_path}", file=sys.stderr)


    # secrets.toml에서 환경변수 로드
    secrets_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "secrets.toml"
    )

    if os.path.exists(secrets_path):
        load_api_key(secrets_path)
        print(f"✓ Loaded secrets from: {secrets_path}")
    else:
        print(f"⚠ secrets.toml not found at: {secrets_path}")
        print("  Please create secrets.toml with PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE")
        sys.exit(1)

    try:
        # PostgresConnector 인스턴스 생성
        print("\n[1] Initializing PostgresConnector...")
        connector = PostgresConnector()
        print("✓ PostgresConnector initialized successfully")

        # 테스트 검색 수행
        test_query = "삼성전자 매출 현황"
        print(f"\n[2] Searching for: '{test_query}'")

        results = connector.search(test_query, top_k=3)

        if results:
            print(f"✓ Found {len(results)} results:\n")
            for i, result in enumerate(results, 1):
                print(f"--- Result {i} ---")
                print(f"  Title: {result['title']}")
                print(f"  URL: {result['url']}")
                print(f"  Score: {result['score']:.4f}")
                print(f"  Content (first 200 chars): {result['content'][:200]}...")
                print()
        else:
            print("⚠ No results found")

        # 연결 종료
        connector.close()
        print("[3] PostgresConnector test completed successfully")

    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)

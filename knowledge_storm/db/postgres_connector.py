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
    from src.common.config import (
        DB_CONFIG,
        COMPANY_ALIASES,
        get_canonical_company_name,
        get_all_aliases,
    )
    _USE_UNIFIED_MODULES = True
except ImportError:
    # 폴백: 기존 방식 (독립 실행 시)
    from sentence_transformers import SentenceTransformer
    _USE_UNIFIED_MODULES = False
    # 폴백용 기본 COMPANY_ALIASES
    COMPANY_ALIASES = {
        "삼성전자": ["삼전", "Samsung Electronics", "Samsung", "삼성전자㈜", "SAMSUNG"],
        "SK하이닉스": ["하이닉스", "SK Hynix", "Hynix", "에스케이하이닉스", "SK하이닉스㈜"],
    }
    def get_canonical_company_name(name: str) -> str:
        for canonical, aliases in COMPANY_ALIASES.items():
            if name == canonical or name in aliases:
                return canonical
        return name
    def get_all_aliases(company_name: str) -> list:
        canonical = get_canonical_company_name(company_name)
        if canonical in COMPANY_ALIASES:
            return [canonical] + COMPANY_ALIASES[canonical]
        return [company_name]

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

    def _extract_target_entities(self, query: str) -> List[str]:
        """
        쿼리에서 타겟 기업명(Entity) 추출

        COMPANY_ALIASES를 기반으로 쿼리 내 기업명을 식별하고,
        해당 기업의 모든 별칭을 반환합니다.

        Args:
            query: 검색 쿼리 문자열

        Returns:
            식별된 기업의 모든 알려진 이름 리스트 (별칭 포함)
            예: ["SK하이닉스", "하이닉스", "SK Hynix", ...]

        Example:
            >>> self._extract_target_entities("SK하이닉스 매출 현황")
            ["SK하이닉스", "하이닉스", "SK Hynix", ...]
        """
        target_keywords = []

        # 모든 기업의 정규명과 별칭을 순회하며 쿼리에 포함된 기업 찾기
        for canonical, aliases in COMPANY_ALIASES.items():
            all_names = [canonical] + aliases

            for name in all_names:
                if name.lower() in query.lower():
                    # 매칭된 기업의 모든 별칭 반환
                    target_keywords = get_all_aliases(canonical)
                    logger.debug(f"[Entity Extraction] Found entity '{canonical}' in query, aliases: {target_keywords}")
                    return target_keywords

        logger.debug(f"[Entity Extraction] No known company entity found in query: {query}")
        return target_keywords

    def _classify_query_intent(self, query: str) -> str:
        """
        질문 의도 분류: Factoid vs Analytical

        Rule-based 키워드 매칭을 사용하여 질문을 분류합니다.

        Args:
            query: 검색 쿼리 문자열

        Returns:
            "factoid" | "analytical"

        Classification Logic:
        - Factoid: 단순 사실 확인 (설립일, 주소, 대표, 전화번호 등)
        - Analytical: 비교/분석 정보 (점유율, 순위, 전망, SWOT, 경쟁 등)

        Example:
            >>> self._classify_query_intent("SK하이닉스 설립일")
            "factoid"
            >>> self._classify_query_intent("삼성전자 대비 시장 점유율")
            "analytical"
        """
        query_lower = query.lower()

        # Analytical Keywords (우선 검사 - 더 구체적)
        analytical_keywords = [
            # 비교/경쟁
            "비교", "대비", "vs", "경쟁", "경쟁사",
            # 분석
            "분석", "swot", "전망", "추세", "동향", "전략",
            # 시장/순위
            "점유율", "순위", "랭킹", "위치", "입지",
            # 재무 분석
            "성장률", "수익성", "안정성", "효율성",
            # 강점/약점
            "강점", "약점", "기회", "위협",
        ]

        for keyword in analytical_keywords:
            if keyword in query_lower:
                logger.debug(f"[Intent] Classified as ANALYTICAL (keyword: '{keyword}')")
                return "analytical"

        # Factoid Keywords
        factoid_keywords = [
            # 기본 정보
            "설립", "설립일", "창립", "주소", "위치", "본사",
            # 인물
            "대표", "대표이사", "ceo", "임원", "이사",
            # 연락처
            "전화", "전화번호", "팩스", "이메일", "연락처",
            # 주주/지분
            "주주", "지분", "소유", "최대주주",
            # 단순 개요
            "개요", "소개", "회사명", "법적", "상호",
        ]

        for keyword in factoid_keywords:
            if keyword in query_lower:
                logger.debug(f"[Intent] Classified as FACTOID (keyword: '{keyword}')")
                return "factoid"

        # 기본값: Analytical (보수적 접근 - 정보 손실 방지)
        logger.debug(f"[Intent] No specific keywords found, defaulting to ANALYTICAL")
        return "analytical"

    def _rerank_by_entity_match(
        self,
        query: str,
        results: List[Dict],
        boost_multiplier: float = 1.3,
        penalty_multiplier: float = 0.5,
        drop_unmatched_tables: bool = True,
        enable_dual_filter: bool = True
    ) -> List[Dict]:
        """
        Entity 매칭 기반 결과 리랭킹 + Dual Filtering

        [FEAT-002 추가] 질문 의도(Factoid vs Analytical)에 따라 필터링 강도 조절
        - Factoid: Strict Filter (Entity 불일치 시 DROP)
        - Analytical: Relaxed Filter (Entity 불일치 시 Penalty만)

        핵심 로직:
        - 매칭 시: 점수 × boost_multiplier (가산점)
        - 불일치 + Factoid: DROP (오답 방지)
        - 불일치 + Analytical: 점수 × penalty_multiplier (정보 보존)

        Args:
            query: 원본 검색 쿼리
            results: 검색 결과 리스트 (STORM 포맷)
            boost_multiplier: 매칭 시 점수 배율 (기본값: 1.3)
            penalty_multiplier: 불일치 시 점수 배율 (기본값: 0.5)
            drop_unmatched_tables: Table 타입 불일치 청크 드롭 여부 (기본값: True)
            enable_dual_filter: Dual Filtering 활성화 여부 (기본값: True)

        Returns:
            스코어가 조정된 결과 리스트 (정렬됨)
        """
        # 1. 쿼리에서 타겟 Entity 추출
        target_keywords = self._extract_target_entities(query)

        if not target_keywords:
            logger.info("[Rerank] No target entity found in query - skipping reranking")
            return results

        # 2. 질문 의도 분류 (Dual Filter)
        query_intent = "analytical"  # 기본값
        if enable_dual_filter:
            query_intent = self._classify_query_intent(query)
            logger.info(f"[Dual Filter] Query intent: {query_intent.upper()}")

        logger.info(f"[Rerank] Target entities for matching: {target_keywords[:3]}...")

        reranked_results = []
        dropped_count = 0

        for doc in results:
            # 3. 메타데이터 결합 (title + content의 일부)
            doc_title = doc.get('title', '')
            doc_content = doc.get('content', '')[:500]
            doc_meta = f"{doc_title} {doc_content}".lower()

            # 3.5. [FIX-Search-002] company_name 누락 시 PASS (Loose Matching)
            # Efficient 모드로 적재된 데이터에 company_name이 없을 수 있음
            doc_company_name = doc.get('_company_name', '')
            if not doc_company_name or doc_company_name == 'Unknown Company':
                # 메타데이터에 company_name이 없으면 필터링 우회 (데이터 살리기)
                doc['score'] = doc.get('score', 0)  # 점수 유지
                doc['_entity_match'] = None  # 매칭 여부 불명
                logger.debug(f"[Rerank] PASS (no company_name in metadata): {doc.get('url', 'unknown')[:40]}...")
                reranked_results.append(doc)
                continue

            # 4. 매칭 여부 확인 (대소문자 무시)
            is_matched = any(keyword.lower() in doc_meta for keyword in target_keywords)

            # 5. chunk_type 확인
            is_table_chunk = "[표 데이터]" in doc.get('content', '')

            # 6. 스코어 조정 (Dual Filtering 적용)
            original_score = doc.get('score', 0)

            if is_matched:
                # ✅ MATCH: 가산점
                doc['score'] = original_score * boost_multiplier
                doc['_entity_match'] = True
                logger.debug(f"[Rerank] MATCH: {doc.get('url', 'unknown')[:40]}... | "
                           f"Score: {original_score:.4f} → {doc['score']:.4f}")
                reranked_results.append(doc)

            else:
                # ❌ NO MATCH: 의도에 따라 처리

                # Case 1: Factoid 질문 → Strict Filter (DROP)
                if query_intent == "factoid":
                    dropped_count += 1
                    logger.debug(f"[Rerank] DROP (factoid + unmatched): {doc.get('url', 'unknown')[:40]}...")
                    continue

                # Case 2: Analytical 질문 → Relaxed Filter
                # Table 청크는 여전히 드롭, Text는 페널티만
                if is_table_chunk and drop_unmatched_tables:
                    dropped_count += 1
                    logger.debug(f"[Rerank] DROP (analytical + unmatched table): {doc.get('url', 'unknown')[:40]}...")
                    continue

                # Text 청크는 페널티 부여 후 유지
                doc['score'] = original_score * penalty_multiplier
                doc['_entity_match'] = False
                logger.debug(f"[Rerank] PENALTY (analytical + unmatched text): {doc.get('url', 'unknown')[:40]}... | "
                           f"Score: {original_score:.4f} → {doc['score']:.4f}")
                reranked_results.append(doc)

        # 7. 점수순 재정렬
        reranked_results.sort(key=lambda x: x.get('score', 0), reverse=True)

        logger.info(f"[Rerank] Completed: {len(reranked_results)} kept, {dropped_count} dropped (intent: {query_intent})")

        return reranked_results

    def _apply_source_tagging(self, results: List[Dict], enable: bool = True) -> List[Dict]:
        """
        Source Tagging: 청크 content에 출처 헤더 물리적 주입

        [FEAT-002] LLM이 정보의 주체를 명확히 구분할 수 있도록
        각 청크의 맨 앞에 [[출처: 회사명]] 태그를 삽입합니다.

        Args:
            results: 검색 결과 리스트
            enable: Source Tagging 활성화 여부 (기본값: True)

        Returns:
            출처 헤더가 추가된 결과 리스트

        Example:
            Before: "당사는 1949년에 설립되었습니다..."
            After:  "[[출처: SK하이닉스 사업보고서]]\n당사는 1949년에 설립되었습니다..."
        """
        if not enable:
            return results

        tagged_results = []
        for doc in results:
            # 메타데이터에서 출처 정보 추출
            company_name = doc.get('_company_name', 'Unknown Company')
            report_id = doc.get('_report_id', 'N/A')

            # 출처 헤더 생성
            source_tag = f"[[출처: {company_name} 사업보고서 (Report ID: {report_id})]]"

            # content 맨 앞에 출처 헤더 주입
            original_content = doc.get('content', '')
            doc['content'] = f"{source_tag}\n\n{original_content}"

            # 내부 메타데이터는 제거 (LLM에게 전달 불필요)
            doc.pop('_company_name', None)
            doc.pop('_report_id', None)

            tagged_results.append(doc)

            logger.debug(f"[Source Tag] Applied to {doc.get('url', 'unknown')[:40]}... | Company: {company_name}")

        logger.info(f"[Source Tag] Applied source tags to {len(tagged_results)} chunks")
        return tagged_results

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

    def search(
        self,
        query: str,
        top_k: int = 5,
        window_size: int = 1,
        company_filter: str = None,
        company_filter_list: List[str] = None
    ) -> List[Dict]:
        """
        벡터 유사도 검색 수행 (기업명 필터링 지원)

        입력된 쿼리를 벡터화하여 PostgreSQL의 Source_Materials 테이블에서
        가장 유사한 문서들을 검색합니다.

        기업명 필터링:
        - company_filter: 단일 기업명 필터 (기본 모드)
        - company_filter_list: 복수 기업명 필터 (비교 분석 모드)
        - 둘 다 None이면 전체 검색 (필터 없음)

        chunk_type이 'table'인 경우 Sliding Window Context를 적용하여
        앞뒤 인접 청크를 함께 가져와 하나의 Context Block으로 구성합니다.

        has_merged_meta가 true인 경우 LLM에게 병합된 메타 정보(단위, 범례 등)가
        문단 끝에 포함되어 있음을 알리는 안내 문구를 추가합니다.

        Args:
            query: 검색 쿼리 문자열
            top_k: 반환할 최대 결과 수 (기본값: 5)
            window_size: Table 청크의 앞뒤로 가져올 인접 청크 수 (기본값: 1)
            company_filter: 단일 기업명 필터 (metadata->>'company_name' = ?)
            company_filter_list: 복수 기업명 필터 (metadata->>'company_name' IN (?))

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

        # [FIX-Search-002] 기업명 필터 조건 생성
        # 메타데이터가 아닌 Companies 테이블 JOIN으로 기업명 조회 (efficient 모드 호환)
        company_condition = ""
        query_params = [embedding_str]

        if company_filter_list and len(company_filter_list) > 0:
            # 복수 기업 필터 (비교 분석 모드)
            placeholders = ", ".join(["%s"] * len(company_filter_list))
            company_condition = f"AND c.company_name IN ({placeholders})"
            query_params.extend(company_filter_list)
            logger.info(f"[Filter] Searching with company_filter_list: {company_filter_list}")
        elif company_filter:
            # 단일 기업 필터 (기본 모드)
            company_condition = "AND c.company_name = %s"
            query_params.append(company_filter)
            logger.info(f"[Filter] Searching with company_filter: {company_filter}")
        else:
            logger.info("[Filter] No company filter applied - searching all documents")

        query_params.append(top_k)

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # [FIX-Search-002] JOIN 기반 벡터 유사도 검색 SQL
                # - Source_Materials → Analysis_Reports → Companies JOIN
                # - 메타데이터에 company_name이 없어도 Companies 테이블에서 조회
                # - pgvector의 <=> 연산자: 코사인 거리 (0에 가까울수록 유사)
                sql = f"""
                    SELECT 
                        sm.id,
                        sm.raw_content, 
                        sm.section_path, 
                        sm.chunk_type, 
                        sm.report_id, 
                        sm.sequence_order,
                        sm.metadata,
                        c.company_name as resolved_company_name,
                        COALESCE((sm.metadata->>'has_merged_meta')::boolean, false) as has_merged_meta,
                        COALESCE((sm.metadata->>'is_noise_dropped')::boolean, false) as is_noise_dropped,
                        (sm.embedding <=> %s::vector) as distance
                    FROM "Source_Materials" sm
                    JOIN "Analysis_Reports" ar ON sm.report_id = ar.id
                    JOIN "Companies" c ON ar.company_id = c.id
                    WHERE sm.chunk_type != 'noise_merged'
                    {company_condition}
                    ORDER BY distance ASC
                    LIMIT %s
                """

                cur.execute(sql, query_params)

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

                    # [FIX-Search-002] Source Tagging을 위한 메타데이터 추가
                    # JOIN에서 가져온 resolved_company_name 우선 사용 (efficient 모드 호환)
                    chunk_metadata = row.get('metadata', {}) or {}
                    company_name = row.get('resolved_company_name') or chunk_metadata.get('company_name', 'Unknown Company')
                    report_id = row['report_id']

                    results.append({
                        "content": content,
                        "title": row['section_path'],
                        "url": unique_url,
                        "score": score,
                        "has_merged_meta": has_merged,
                        # Source Tagging용 메타데이터
                        "_company_name": company_name,
                        "_report_id": report_id,
                    })

                logger.info(f"Found {len(results)} results for query: {query}")

                # [FIX-Search-002] 빈 결과 크래시 방어
                # 검색 결과가 없으면 Reranker 호출하지 않고 즉시 반환
                if not results:
                    logger.warning(f"PostgresRM: Found 0 results for query '{query}'. Skipping rerank.")
                    return []

                # [FEAT-001] Entity Bias 방지: Entity 매칭 기반 리랭킹 + Dual Filtering
                # - Factoid 질문: Entity 불일치 시 DROP (Strict Filter)
                # - Analytical 질문: Entity 불일치 시 Penalty (Relaxed Filter)
                results = self._rerank_by_entity_match(
                    query=query,
                    results=results,
                    boost_multiplier=1.3,
                    penalty_multiplier=0.5,
                    drop_unmatched_tables=True,
                    enable_dual_filter=True  # [FEAT-002] Dual Filtering 활성화
                )

                # [FEAT-002] Source Tagging: 청크에 출처 헤더 물리적 주입
                # LLM이 정보의 출처를 명확히 인식하도록 [[출처: 회사명]] 태그 추가
                results = self._apply_source_tagging(
                    results=results,
                    enable=True  # Source Tagging 활성화
                )

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

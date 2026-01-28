"""
Vector Search Service - RAG Retrieval Orchestrator (Read-Only)

Refactored:
- Integrated LLMQueryAnalyzer for intelligent intent understanding
- Integrated EntityResolver for accurate company name matching (RapidFuzz)
- Implemented 'Competitor Logic': Relaxes filters for comparison queries
- Implemented 'Text-Driven Retrieval': Finds text first, then attaches tables
"""

import logging
from typing import Any

from src.common.embedding import EmbeddingService
from src.common.entity_resolver import CompanyEntityResolver
from src.database.models.query_analysis_result import QueryAnalysisResult
from src.database.models.source_material import SourceMaterial
from src.database.repositories import SourceMaterialRepository
from src.services.search.query_analyzer import LLMQueryAnalyzer
from src.services.reranker_service import RerankerService

logger = logging.getLogger(__name__)


class VectorSearchService:
    """
    Orchestrates the RAG retrieval process.
    """

    def __init__(
        self,
        source_material_repo: SourceMaterialRepository,
        embedding_service: EmbeddingService,
        query_analyzer: LLMQueryAnalyzer,
        reranker_service: RerankerService,
    ) -> None:
        self.repo = source_material_repo
        self.embedding_service = embedding_service
        self.analyzer = query_analyzer
        self.reranker = reranker_service
        self.entity_resolver = CompanyEntityResolver()

    async def initialize_resolver(self):
        """
        [Startup] 서버 시작 시 호출하여 DB의 모든 기업명을 메모리에 로드
        """
        companies = await self.repo.get_all_company_names()
        self.entity_resolver.update_company_list(companies)
        logger.info(f"EntityResolver initialized with {len(companies)} companies from DB.")

    async def search(
        self,
        query: str,
        top_k: int = 10,
        enable_rerank: bool = True,
        enable_source_tagging: bool = True
    ) -> list[dict[str, Any]]:
        """
        Execute the Search Pipeline:
        1. Analyze Query (Intent, Entities, Competitor Check)
        2. Resolve Entities (Fuzzy Match -> Canonical Name)
        3. Embed Query
        4. Retrieve (Dynamic Filtering)
        5. Forward Lookup (Attach Tables)
        6. Rerank
        """
        # 1. Query Analysis
        analysis: QueryAnalysisResult = await self.analyzer.analyze(query)
        logger.debug(f"Analysis: Intent={analysis.intent}, Raw Entities={analysis.target_companies}, IsCompetitor={analysis.is_competitor_query}")

        # 2. [NEW] Entity Resolution (기업명 정규화)
        # LLM이 "삼전"이라 해도 DB의 "삼성전자"로 변환
        resolved_companies = []
        for raw_name in analysis.target_companies:
            resolved = self.entity_resolver.resolve(raw_name)
            if resolved:
                resolved_companies.append(resolved)
            else:
                # 매칭 실패 시 원본 사용 (신규 상장사 등)
                resolved_companies.append(raw_name)

        logger.debug(f"Resolved Entities: {resolved_companies}")

        # 3. Embed Query
        query_embedding = self.embedding_service.embed_text(query)

        # 4. [NEW] Filter Strategy (경쟁사 로직 적용)
        # 경쟁사 질문이면 필터를 해제하여 다른 기업 문서도 검색 허용
        filter_list = resolved_companies
        if analysis.is_competitor_query:
            logger.info("⚡ Competitor intent detected: Relaxing company filter.")
            filter_list = None  # 필터 해제 (모든 기업 검색)

        # 5. DB Retrieval (Text Priority)
        # 우선 'text' 타입만 검색하여 문맥을 잡음
        raw_rows = await self.repo.search_by_vector(
            query_embedding,
            top_k=top_k * 2 if analysis.is_competitor_query else top_k, # 경쟁사 검색 시 후보군 확대
            company_filter_list=filter_list,
            chunk_type_filter="text"
        )

        if not raw_rows:
            return []

        # 6. Result Processing (Forward Lookup)
        processed_results = []
        for row in raw_rows:
            material: SourceMaterial = row[0]
            score = 1 - row[2]
            content = material.raw_content

            # [핵심] Text 뒤에 Table이 숨어있는지 확인 (Forward Lookup)
            next_chunk = await self.repo.get_nearest_next_chunk(material.report_id, material.sequence_order)

            if next_chunk:
                # 거리(5) & 타입(Table) 체크
                seq_gap = next_chunk.sequence_order - material.sequence_order
                if next_chunk.chunk_type == 'table' and seq_gap <= 5:
                    content += f"\n\n[관련 표 데이터]\n{next_chunk.raw_content}"

                    meta = next_chunk.meta_info or {}
                    if meta.get('has_merged_meta'):
                        content = "[참고: 표에 단위/범례 정보가 포함됨]\n" + content

            processed_results.append({
                "content": content,
                "title": material.section_path,
                "url": f"dart_report_{material.report_id}_chunk_{material.id}",
                "score": score,
                "_company_name": row[1],
                "_intent": analysis.intent,
                "_matched_entities": resolved_companies # 정규화된 이름 전달
            })

        # 7. Reranking
        if enable_rerank:
            processed_results = self._rerank_results(processed_results, analysis, resolved_companies)
            processed_results = processed_results[:top_k]

        # 8. Source Tagging
        if enable_source_tagging:
            processed_results = self._apply_source_tagging(processed_results)

        return processed_results

    # =========================================================================
    #  Internal Helper Methods
    # =========================================================================

    def _rerank_results(
        self,
        results: list[dict],
        analysis: QueryAnalysisResult,
        resolved_companies: list[str]
    ) -> list[dict]:
        """
        Heuristic Reranker (Improved)
        - Uses 'resolved_companies' for accurate matching
        - Adapts logic for 'competitor' queries
        """
        # 비교를 위해 소문자 변환
        targets = [c.lower() for c in resolved_companies]

        if not targets and not analysis.is_competitor_query:
            return results

        reranked = []
        boost_multiplier = 1.3
        penalty_multiplier = 0.5

        # 경쟁사 질문인 경우, 타겟 기업이 아니어도 점수를 깎지 않음 (관대함)
        is_relaxed_mode = analysis.is_competitor_query

        for doc in results:
            doc_company = doc.get('_company_name', '').lower()
            original_score = doc['score']

            # 매칭 여부 확인
            is_matched = False
            if not doc_company or doc_company == 'unknown company':
                is_matched = True
            else:
                is_matched = any(t in doc_company for t in targets)

            if is_matched:
                doc['score'] = original_score * boost_multiplier
                reranked.append(doc)
            else:
                # 불일치 시 처리
                if is_relaxed_mode:
                    # 경쟁사 질문이면 다른 기업 문서도 소중함 -> 점수 유지 (페널티 없음)
                    reranked.append(doc)
                elif analysis.intent == 'factoid':
                    # 단순 사실 질문인데 엉뚱한 기업 -> 제거
                    continue
                else:
                    # 분석 질문 -> 페널티 부여 후 유지
                    doc['score'] = original_score * penalty_multiplier
                    reranked.append(doc)

        # 점수순 정렬
        reranked.sort(key=lambda x: x['score'], reverse=True)
        return reranked

    def _apply_source_tagging(self, results: list[dict]) -> list[dict]:
        for doc in results:
            company = doc.get('_company_name', 'Unknown')
            try:
                rid = doc['url'].split('_')[2]
            except:
                rid = 'N/A'

            tag = f"[[출처: {company} 사업보고서 (Report ID: {rid})]]"
            doc['content'] = f"{tag}\n\n{doc['content']}"

            # Cleanup
            doc.pop('_company_name', None)
            doc.pop('_intent', None)
            doc.pop('_matched_entities', None)

        return results

"""
Unified Retriever Module for STORM

Refactored:
- Replaced legacy 'PostgresConnector' with 'VectorSearchService'.
- Removed redundant 'set_company_filter' (QueryAnalyzer handles it automatically).
- Maintains the exact output format (List[Dict]) for compatibility.
"""

import asyncio
import logging
from typing import Any

import dspy

from src.common.embedding import EmbeddingService
from src.database import AsyncDatabaseEngine
from src.database.repositories import SourceMaterialRepository
from src.services.search.query_analyzer import LLMQueryAnalyzer
from src.services.vector_search_service import VectorSearchService

logger = logging.getLogger(__name__)

class PostgresRM(dspy.Retrieve):
    """
    PostgreSQL Vector Search Retriever (Adapter)

    Connects STORM's synchronous interface to the new asynchronous VectorSearchService.
    Retrieves DART report chunks from the internal database.
    """

    def __init__(self, k: int = 10, min_score: float = 0.5):
        super().__init__(k=k)

        # 2. Initialize Dependencies (Service Assembler)
        self.db_engine = AsyncDatabaseEngine()
        self.embedding_service = EmbeddingService()
        self.query_analyzer = LLMQueryAnalyzer()

        self.min_score = min_score
        self.usage = 0

        logger.info(f"PostgresRM initialized with k={k}, min_score={min_score}")

    def get_usage_and_reset(self):
        """Track usage statistics."""
        usage = self.usage
        self.usage = 0
        return {"PostgresRM": usage}

    def forward(
        self,
        query_or_queries: str | list[str],
        exclude_urls: list[str] = None,
        k: int = None
    ) -> list[dict[str, Any]]:
        """
        Standard dspy.Retrieve entry point (Synchronous).
        """
        if exclude_urls is None:
            exclude_urls = []

        search_k = k if k is not None else self.k

        # Normalize queries to list
        queries = [query_or_queries] if isinstance(query_or_queries, str) else query_or_queries
        self.usage += len(queries)

        collected_results = []

        # Run Async Search Logic Synchronously
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            for query in queries:
                # 3. 비동기 검색 실행
                # (QueryAnalyzer가 내부에서 자동으로 기업명을 추출하여 필터링함)
                results = loop.run_until_complete(
                    self._search_async(query, search_k)
                )
                collected_results.extend(results)

            loop.close()

        except Exception as e:
            logger.error(f"Error executing async search: {e}")
            return []

        logger.info(f"PostgresRM: Found {len(collected_results)} results for {len(queries)} queries")
        return collected_results

    async def _search_async(self, query: str, k: int) -> list[dict[str, Any]]:
        """
        Internal Async Implementation using VectorSearchService.
        """
        async with self.db_engine.get_session() as session:
            # 4. Create Repository & Service with current session
            repo = SourceMaterialRepository(session)
            search_service = VectorSearchService(
                source_material_repo=repo,
                embedding_service=self.embedding_service,
                query_analyzer=self.query_analyzer
            )

            # 5. Execute Search (Service handles Analysis -> Embed -> Filter -> Rerank)
            raw_results = await search_service.search(query, top_k=k)

            # 6. Convert to STORM Dictionary Format
            formatted_results = []
            low_score_count = 0

            for res in raw_results:
                score = res.get('score', 0.0)

                # Filter by min_score
                if score < self.min_score:
                    low_score_count += 1
                    # (선택) 임계값 미만은 버리고 싶다면 아래 주석 해제
                    # continue

                entry = {
                    "content": res.get("content", ""),
                    "snippets": [res.get("content", "")], # STORM compat
                    "title": res.get("title", "No Title"),
                    "url": res.get("url", "local_db"),
                    "description": res.get("title", ""),
                    "score": score,
                    "source": "internal" # 명시적 소스 태그
                }
                formatted_results.append(entry)

            if low_score_count > 0:
                logger.warning(
                    f"PostgresRM: {low_score_count} results below threshold ({self.min_score})"
                )

            return formatted_results

    def close(self):
        """Cleanup resources."""
        pass


class HybridRM(dspy.Retrieve):
    """
    Hybrid Retrieval Model (Internal DB + External Search)

    Combines PostgresRM (Internal) and SerperRM (External).
    """

    def __init__(
        self,
        internal_rm,
        external_rm,
        internal_k: int = 3,
        external_k: int = 7
    ):
        if internal_rm is None or external_rm is None:
            raise ValueError("Both internal_rm and external_rm must be provided")

        super().__init__(k=internal_k + external_k)

        self.internal_rm = internal_rm
        self.external_rm = external_rm
        self.internal_k = internal_k
        self.external_k = external_k
        self.usage = 0

        logger.info(
            f"HybridRM initialized: Internal(k={internal_k}) + External(k={external_k})"
        )

    def get_usage_and_reset(self):
        usage = self.usage
        self.usage = 0

        internal_usage = self.internal_rm.get_usage_and_reset()
        external_usage = {}
        if hasattr(self.external_rm, 'get_usage_and_reset'):
            external_usage = self.external_rm.get_usage_and_reset()

        return {
            "HybridRM": usage,
            **internal_usage,
            **external_usage
        }

    def forward(
        self,
        query_or_queries: str | list[str],
        exclude_urls: list[str] = None
    ):
        if exclude_urls is None:
            exclude_urls = []

        queries = [query_or_queries] if isinstance(query_or_queries, str) else query_or_queries
        self.usage += len(queries)

        final_results = []

        for query in queries:
            logger.info(f"[HybridRM] Processing query: {query}")

            # 1. Internal Search (PostgresRM)
            internal_results = []
            try:
                # Sync wrapper call
                i_res = self.internal_rm.forward(query, exclude_urls=exclude_urls, k=self.internal_k)

                # Format standardization
                if hasattr(i_res, 'passages'): i_res = i_res.passages
                if not isinstance(i_res, list): i_res = [i_res] if i_res else []

                internal_results = i_res[:self.internal_k]
                for item in internal_results:
                    if isinstance(item, dict): item['source'] = 'internal'

            except Exception as e:
                logger.error(f"[HybridRM] Internal search error: {e}")

            # 2. External Search (SerperRM)
            external_results = []
            try:
                e_res = self.external_rm.forward(query, exclude_urls=exclude_urls)

                if hasattr(e_res, 'passages'): e_res = e_res.passages
                if not isinstance(e_res, list): e_res = [e_res] if e_res else []

                external_results = e_res[:self.external_k]
                for item in external_results:
                    if isinstance(item, dict): item['source'] = 'external'

            except Exception as e:
                logger.error(f"[HybridRM] External search error: {e}")

            # 3. Merge & Deduplicate (URL based)
            seen_urls = set()
            merged_results = []

            # Add Internal First
            for item in internal_results:
                url = item.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    merged_results.append(item)
                elif not url:
                    merged_results.append(item)

            # Add External
            for item in external_results:
                url = item.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    merged_results.append(item)
                elif not url:
                    merged_results.append(item)

            final_results.extend(merged_results)

        return final_results

    def close(self):
        if hasattr(self.internal_rm, 'close'): self.internal_rm.close()
        if hasattr(self.external_rm, 'close'): self.external_rm.close()

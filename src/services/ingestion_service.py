"""
Ingestion Service - Source Material Management & Embedding Generation

Responsibilities:
1. Receive parsed chunks (text/table) from Parser
2. Generate embeddings using EmbeddingService
3. Save to Database via SourceMaterialRepository
"""

import logging
from re import match
from typing import Any

from src.common.embedding import EmbeddingService
from src.database.models.source_material import SourceMaterial
from src.database.repositories import SourceMaterialRepository

logger = logging.getLogger(__name__)



class IngestionService:
    """
    Service for ingesting and managing source materials.
    Separates 'Write' logic from 'Read' (Search) logic.
    """
    NOISE_KEYWORDS = ["단위", "Unit", "범례", "참조", "※", "주)", "(주)", "(단위"]

    def __init__(
        self,
        source_repo: SourceMaterialRepository,
        embedding_service: EmbeddingService
    ):
        self.source_repo = source_repo
        self.embedding_service = embedding_service

    async def save_chunks(
        self,
        report_id: int,
        chunks: list[dict[str, Any]]
    ) -> list[SourceMaterial]:

        # 1. 전방 병합 전처리 수행
        valid_chunks = self._preprocess_chunks(chunks)

        # 2. 임베딩 생성 (Text만 검색하더라도, Table도 혹시 모르니 임베딩은 해둡니다)
        #    사용자 요청대로 "Text만 검색"할 거라면, Table은 임베딩 안 해도 되지만,
        #    나중에 특정 수치 검색 니즈가 있을 수 있으니 생성은 권장합니다.
        texts = [c['raw_content'] for c in valid_chunks]
        if texts:
            embeddings = self.embedding_service.embed_texts(texts)
            for chunk, vec in zip(valid_chunks, embeddings, strict=False):
                chunk['embedding'] = vec

        # 3. DB 저장
        return await self.source_repo.create_bulk(report_id, valid_chunks)

    async def get_chunks(self, report_id: int) -> list[SourceMaterial]:
        """
        Retrieve all chunks for a specific report.
        Useful for debugging or re-indexing.
        """
        return await self.source_repo.get_by_report_id(report_id)

    async def delete_report_chunks(self, report_id: int) -> bool:
        """
        Delete all chunks associated with a report.
        (Clean up before re-ingestion)
        """
        # Repository에 delete_by_filter 기능이 있다면 사용
        # 현재는 예시 로직
        chunks = await self.source_repo.get_by_report_id(report_id)
        for chunk in chunks:
            await self.source_repo.delete(chunk.id)
        return True

    def _is_noise_table(self, content: str) -> bool:
        """표가 단순 단위/범례 표인지 판별"""
        if not content:
            return False
        lines = content.strip().split("\n")
        data_rows = [line for line in lines if "|" in line and not match(r"^\|[\s\-:]+\|$", line.strip())]
        if len(data_rows) <= 2: # 행이 너무 적고
            for k in self.NOISE_KEYWORDS:
                if k in content:
                    return True # 키워드가 있으면 노이즈
        return False

    def _preprocess_chunks(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        [v3.1 Update] Forward Merge Strategy
        1. Noise Table (단위/범례): 바로 '뒤'에 오는 Table에 병합 (앞이 아님!)
        2. Reference (참조): 필터링 안 되면 그냥 Table로 둠 (검색 단계에서 Text 위주로 검색하므로 무관)
        """
        if not chunks: return []

        # 리스트 직접 조작을 위해 복사본 사용하지 않고 인덱스로 접근
        n = len(chunks)
        merge_flags = [False] * n  # 병합되어 사라질 청크 표시

        for i in range(n):
            if merge_flags[i]: continue  # 이미 처리됨

            curr = chunks[i]
            curr_type = curr.get("chunk_type", "text")
            curr_content = curr.get("raw_content", "")

            # [Case 1] Noise Table (단위 등) 발견 -> 뒤(Next) 확인
            # 바로 뒤 청크가 있는지 확인
            # 뒤에 'Table'이 오면 -> 거기에 병합 (단위 정보는 표의 머리말 역할)
            if (curr_type == 'table' and self._is_noise_table(curr_content) \
                and i + 1 < n \
                and chunks[i+1].get("chunk_type", "text") == 'table'):
                    next_chunk = chunks[i + 1]
                    # [Forward Merge]
                    # Next Content = [Current Noise] + \n + [Next Table]
                    next_chunk['raw_content'] = f"{curr_content}\n\n{next_chunk['raw_content']}"

                    # 메타데이터에 '병합됨' 표시
                    next_chunk['meta_info'] = next_chunk.get('meta_info', {})
                    next_chunk['meta_info']['has_merged_meta'] = True

                    # 현재 청크는 삭제 대상
                    merge_flags[i] = True
                    logger.debug(f"Forward merged noise (seq={curr['sequence_order']}) into next table")
                    continue

            # [Case 2] 일반 Table 처리
            # (Context Injection은 여기서 하지 않고, 검색 단계에서 'Text + Next Table' 전략 사용)
            # 따라서 별도 처리가 필요 없음. Raw Content 그대로 저장.

        # 병합되지 않은 살아있는 청크만 반환
        valid_chunks = [chunks[i] for i in range(n) if not merge_flags[i]]
        return valid_chunks

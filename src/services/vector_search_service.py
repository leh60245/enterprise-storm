"""
Vector Search Service - Embedding Management & RAG Retrieval (Service Layer)

Refactored:
- Aligned field name 'meta_info' with actual DB column (renamed from metadata).
"""

import logging
from typing import Any

from src.database.models.source_material import SourceMaterial
from src.database.repositories import EntityNotFound, SourceMaterialRepository

logger = logging.getLogger(__name__)


class VectorSearchService:
    """Service for managing source materials and vector search."""

    def __init__(
        self,
        source_material_repo: SourceMaterialRepository,
    ) -> None:
        if source_material_repo is None:
            raise ValueError("SourceMaterialRepository cannot be None")

        self.source_material_repo = source_material_repo

    async def save_chunks(
        self,
        report_id: int,
        chunks: list[dict[str, Any]],
    ) -> list[SourceMaterial]:
        """
        Bulk insert source material chunks with embeddings.
        """

        if report_id <= 0:
            raise ValueError("report_id must be positive")
        if not chunks:
            return []

        created_materials: list[SourceMaterial] = []

        for chunk in chunks:

            material_data = {
                "report_id": report_id,
                "chunk_type": chunk.get("chunk_type", "text"),
                "section_path": chunk.get("section_path", ""),
                "sequence_order": chunk.get("sequence_order", 0),
                "raw_content": chunk.get("raw_content", ""),
                "embedding": chunk.get("embedding"),
                "table_metadata": chunk.get("table_metadata"),
                "meta_info": chunk.get("meta_info"),
            }

            material = await self.source_material_repo.create(material_data)
            created_materials.append(material)

        return created_materials

    async def search_relevant_chunks(
        self,
        query_embedding: list[float],
        top_k: int = 10,
    ) -> list[SourceMaterial]:
        """Execute semantic similarity search for RAG retrieval."""

        if not query_embedding:
            raise ValueError("query_embedding cannot be empty")
        if top_k <= 0:
            raise ValueError("top_k must be > 0")

        return await self.source_material_repo.vector_search(query_embedding, top_k)

    async def get_chunks_for_report(
        self,
        report_id: int,
        chunk_type: str | None = None,
        limit: int | None = 500,
    ) -> list[SourceMaterial]:
        """Retrieve all chunks for a specific report."""

        filters: dict[str, Any] = {"report_id": report_id}
        if chunk_type:
            filters["chunk_type"] = chunk_type

        result = await self.source_material_repo.get_by_filter(filters)
        chunks = result if isinstance(result, list) else []
        sorted_chunks = sorted(chunks, key=lambda x: x.sequence_order)

        if limit is None:
            return sorted_chunks
        return sorted_chunks[:limit]

    async def get_chunk_context(
        self,
        chunk_id: int,
        context_window: int = 1,
    ) -> dict[str, Any]:
        """Retrieve a chunk with surrounding context."""

        target = await self.source_material_repo.get_by_id(chunk_id)
        if not target:
            raise EntityNotFound(f"Chunk with id {chunk_id} not found")

        all_chunks = await self.get_chunks_for_report(target.report_id, limit=None)

        target_idx = next(
            (i for i, c in enumerate(all_chunks) if c.id == chunk_id), None
        )

        if target_idx is None:
            return {"target": target, "previous": [], "next": []}

        start_idx = max(0, target_idx - context_window)
        end_idx = min(len(all_chunks), target_idx + context_window + 1)

        previous = all_chunks[start_idx:target_idx]
        next_chunks = all_chunks[target_idx + 1 : end_idx]

        return {
            "target": target,
            "previous": previous,
            "next": next_chunks,
        }

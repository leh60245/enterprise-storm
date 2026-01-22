"""
Source Material Repository

Refactored:
- Added 'model = SourceMaterial' (Required by BaseRepository)
- Removed explicit 'session' argument (Uses self.session)
- Added 'sequence_order' sorting for report reconstruction
- Added error handling with RepositoryError
"""

from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.source_material import SourceMaterial
from .base_repository import BaseRepository, RepositoryError


class SourceMaterialRepository(BaseRepository[SourceMaterial]):
    """
    Repository for SourceMaterial model.
    Handles vector search and retrieval of chunked text data.
    """
    
    # [필수] BaseRepository 상속 시 model 정의
    model = SourceMaterial

    async def get_by_report_id(self, report_id: int) -> List[SourceMaterial]:
        """
        Retrieve all source materials (chunks) for a specific analysis report.
        Ordered by sequence to reconstruct original flow.
        
        Args:
            report_id: ID of the parent AnalysisReport
            
        Returns:
            List of SourceMaterial ordered by sequence
        """
        try:
            stmt = (
                select(self.model)
                .where(self.model.report_id == report_id)
                .order_by(self.model.sequence_order.asc())  # 순서 보장
            )
            result = await self.session.execute(stmt)
            return result.scalars().all()
            
        except Exception as e:
            raise RepositoryError(
                f"Failed to get source materials for report {report_id}: {e}"
            ) from e

    async def vector_search(
        self, 
        embedding: List[float], 
        top_k: int = 5
    ) -> List[SourceMaterial]:
        """
        Perform vector similarity search using pgvector (L2 distance).
        
        Args:
            embedding: Query embedding vector
            top_k: Number of results to return
            
        Returns:
            List of most similar SourceMaterial entities
        """
        try:
            # pgvector의 l2_distance 연산자 (<->) 사용
            # 주의: DB에 vector extension과 인덱스가 있어야 성능 보장
            stmt = (
                select(self.model)
                .order_by(self.model.embedding.l2_distance(embedding))
                .limit(top_k)
            )
            result = await self.session.execute(stmt)
            return result.scalars().all()
            
        except Exception as e:
            raise RepositoryError(f"Vector search failed: {e}") from e
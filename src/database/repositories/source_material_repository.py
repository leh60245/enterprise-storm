"""
Source Material Repository
"""
from typing import Any

# pgvector 연산자 사용을 위해 필요 (cosine_distance)
from sqlalchemy import and_, distinct, select

from src.database.models.analysis_report import AnalysisReport
from src.database.models.company import Company
from src.database.models.source_material import SourceMaterial

from .base_repository import BaseRepository, RepositoryError


class SourceMaterialRepository(BaseRepository[SourceMaterial]):
    """
    Repository for SourceMaterial model.
    Handles vector search, metadata filtering, and context retrieval.
    """

    # [필수] BaseRepository 상속 시 model 정의
    model = SourceMaterial

    async def get_by_report_id(self, report_id: int) -> list[SourceMaterial]:
        """
        Retrieve all source materials (chunks) for a specific analysis report.
        Ordered by sequence to reconstruct original flow.

        Args:
            report_id: ID of the parent AnalysisReport

        Returns:
            list of SourceMaterial ordered by sequence
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

    async def search_by_vector(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        company_filter_list: list[str] | None = None,
        chunk_type_filter: str | None = None
    ) -> list[Any]:
        """
        Perform advanced vector search with company filtering.
        Replaces 'postgres_connector.py' search logic.

        Logic:
            1. JOIN SourceMaterial -> AnalysisReport -> Company
            2. Filter by company_names (if provided)
            3. Exclude 'noise_merged' chunks
            4. Order by Cosine Distance (embedding <=> query)

        Returns:
            List of Row objects containing (SourceMaterial, company_name, distance)
        """
        try:
            # Cosine Distance Operator (<=>)
            # SQLAlchemy pgvector extension provides 'cosine_distance'
            distance_col = self.model.embedding.cosine_distance(query_embedding).label("distance")

            stmt = (
                select(
                    self.model,
                    Company.company_name,
                    distance_col
                )
                .join(AnalysisReport, self.model.report_id == AnalysisReport.id)
                .join(Company, AnalysisReport.company_id == Company.id)
                .where(self.model.chunk_type != 'noise_merged')
            )

            # Apply Company Filter
            if company_filter_list:
                stmt = stmt.where(Company.company_name.in_(company_filter_list))

            # Apply Chunk Type Filter
            if chunk_type_filter:
                stmt = stmt.where(self.model.chunk_type == chunk_type_filter)

            # Order by Distance and Limit
            stmt = stmt.order_by(distance_col.asc()).limit(top_k)

            result = await self.session.execute(stmt)

            # Returns raw rows: (SourceMaterial object, company_name string, distance float)
            return result.all()

        except Exception as e:
            raise RepositoryError(f"Vector search failed: {e}") from e

    async def get_context_window(
        self,
        report_id: int,
        center_sequence: int,
        window_size: int = 1
    ) -> list[SourceMaterial]:
        """
        Retrieve adjacent chunks for context reconstruction (Sliding Window).
        Used for 'table' chunks to get surrounding text.

        Range: [center - window, center + window] (excluding noise)

        Args:
            report_id: ID of the report
            center_sequence: The sequence_order of the main chunk
            window_size: How many chunks to retrieve before/after

        Returns:
            List of SourceMaterial sorted by sequence_order
        """
        try:
            min_seq = center_sequence - window_size
            max_seq = center_sequence + window_size

            stmt = (
                select(self.model)
                .where(
                    and_(
                        self.model.report_id == report_id,
                        self.model.sequence_order.between(min_seq, max_seq),
                        self.model.chunk_type != 'noise_merged',
                        self.model.sequence_order != center_sequence # 본문 제외 (선택 사항, 여기선 주변부만 조회)
                    )
                )
                .order_by(self.model.sequence_order.asc())
            )

            result = await self.session.execute(stmt)
            return result.scalars().all()

        except Exception as e:
            raise RepositoryError(
                f"Failed to get context window for report {report_id}, seq {center_sequence}: {e}"
            ) from e

    async def create_bulk(
        self,
        report_id: int,
        chunks: list[dict[str, Any]]
    ) -> list[SourceMaterial]:
        """
        Bulk insert chunks for high-performance ingestion.

        Args:
            report_id: ID of the analysis report
            chunks: List of dictionaries containing chunk data

        Returns:
            List of created SourceMaterial objects (with IDs populated)
        """
        if not chunks:
            return []

        try:
            # 1. Dict -> ORM Object 변환
            new_objects = []
            for chunk in chunks:
                # 안전한 필드 매핑
                material = self.model(
                    report_id=report_id,
                    chunk_type=chunk.get("chunk_type", "text"),
                    section_path=chunk.get("section_path", ""),
                    sequence_order=chunk.get("sequence_order", 0),
                    raw_content=chunk.get("raw_content", ""),
                    embedding=chunk.get("embedding"),
                    table_metadata=chunk.get("table_metadata"),
                    meta_info=chunk.get("meta_info"),
                )
                new_objects.append(material)

            # 2. Bulk Add (Session에 추가)
            self.session.add_all(new_objects)

            # 3. Commit (DB 반영 및 ID 생성)
            await self.session.commit()

            # 4. Refresh (선택 사항: ID 등 DB 생성값 로드)
            # 대량 데이터의 경우 refresh는 성능 저하 원인이 될 수 있으나,
            # 반환값이 필요하다면 수행. 여기서는 객체 반환을 위해 유지.
            # (SQLAlchemy는 commit 후 객체 접근 시 자동으로 refresh 하기도 함)

            return new_objects

        except Exception as e:
            await self.session.rollback() # 에러 시 롤백
            raise RepositoryError(
                f"Bulk create failed for report {report_id}: {e}"
            ) from e

    async def get_nearest_next_chunk(self, report_id: int, current_seq: int) -> SourceMaterial | None:
        """
        현재 시퀀스 이후에 등장하는 '첫 번째 유효 청크'를 조회합니다.
        중간에 'noise_merged'로 죽은 청크들이 있어도 건너뛰고 진짜를 찾아옵니다.
        """
        stmt = (
            select(self.model)
            .where(
                self.model.report_id == report_id,
                self.model.sequence_order > current_seq,    # 현재보다 뒤에 있는 것 중
                self.model.chunk_type != 'noise_merged'     # 죽은 건 건너뜀
            )
            .order_by(self.model.sequence_order.asc())      # 가장 가까운 순서대로
            .limit(1)                                       # 딱 하나만
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_company_names(self) -> list[str]:
        """DB에 존재하는 모든 기업명 조회 (중복 제거)"""
        # meta_info ->> 'corp_name'이 있거나, 별도 컬럼이 있다면 사용
        # 여기서는 가정: meta_info JSONB 필드 내에 'corp_name'이 있다고 가정
        # 또는 별도의 Company 테이블이 있다면 거기서 가져오는 것이 Best.

        # 예시: SourceMaterial.meta_info['corp_name']을 조회
        # (PostgreSQL JSONB 문법 사용)
        stmt = select(distinct(self.model.meta_info['corp_name'].astext))
        result = await self.session.execute(stmt)
        companies = result.scalars().all()
        return [c for c in companies if c] # None 제거

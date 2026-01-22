"""
Generated Report Repository
"""

from typing import Any

from sqlalchemy import asc, desc, func, select

from ..models.generated_report import GeneratedReport
from .base_repository import BaseRepository, RepositoryError


class GeneratedReportRepository(BaseRepository[GeneratedReport]):
    """
    GeneratedReport 테이블 데이터 접근 객체.
    기본 CRUD 외에 리포트 목록 페이징 조회를 지원합니다.
    """

    model = GeneratedReport

    async def get_reports_paginated(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
        offset: int = 0,
        sort_by: str = "created_at",
        ascending: bool = False,
    ) -> list[GeneratedReport]:
        """필터 조건과 페이징을 적용하여 리포트 목록을 조회합니다."""
        try:
            stmt = select(self.model)

            # 1. 필터링
            if filters:
                for attr, value in filters.items():
                    if hasattr(self.model, attr) and value is not None:
                        if isinstance(value, str):
                            stmt = stmt.where(
                                getattr(self.model, attr).ilike(f"%{value}%")
                            )
                        else:
                            stmt = stmt.where(getattr(self.model, attr) == value)

            # 2. 동적 정렬 (Dynamic Sorting) [Legacy Parity]
            if hasattr(self.model, sort_by):
                sort_col = getattr(self.model, sort_by)
                stmt = stmt.order_by(asc(sort_col) if ascending else desc(sort_col))
            else:
                # 유효하지 않은 컬럼이면 기본값(최신순) 적용
                stmt = stmt.order_by(desc(self.model.created_at))

            # 3. 페이징
            stmt = stmt.limit(limit).offset(offset)

            result = await self.session.execute(stmt)
            return result.scalars().all()

        except Exception as e:
            raise RepositoryError(f"Failed to fetch paginated reports: {e}") from e

    async def count_reports(self, filters: dict[str, Any] | None = None) -> int:
        """필터 조건에 해당하는 전체 리포트 수를 반환합니다."""
        try:
            stmt = select(func.count()).select_from(self.model)

            if filters:
                for attr, value in filters.items():
                    if hasattr(self.model, attr) and value is not None:
                        if isinstance(value, str):
                            stmt = stmt.where(
                                getattr(self.model, attr).ilike(f"%{value}%")
                            )
                        else:
                            stmt = stmt.where(getattr(self.model, attr) == value)

            result = await self.session.execute(stmt)
            return result.scalar() or 0

        except Exception as e:
            raise RepositoryError(f"Failed to count reports: {e}") from e

    async def get_latest_by_company(self, company_id: int) -> GeneratedReport | None:
        """특정 기업의 가장 최근 리포트를 조회합니다."""
        try:
            stmt = (
                select(self.model)
                .where(self.model.company_id == company_id)
                .order_by(desc(self.model.created_at))
                .limit(1)
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            raise RepositoryError(
                f"Failed to get latest report for company {company_id}: {e}"
            ) from e

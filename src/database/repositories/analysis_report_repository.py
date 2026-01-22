"""
Analysis Report Repository

Refactored:
- Added 'model = AnalysisReport' to fix AttributeError.
- Implemented 'get_by_year' to handle fiscal period queries using 'rcept_dt'.
- Aligned session usage with BaseRepository pattern (self.session).
"""

from typing import Optional, List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.analysis_report import AnalysisReport
from .base_repository import BaseRepository, RepositoryError


class AnalysisReportRepository(BaseRepository[AnalysisReport]):
    """Repository for AnalysisReport model."""
    
    # [중요] BaseRepository 상속 시 필수 속성
    model = AnalysisReport

    async def get_by_rcept_no(self, rcept_no: str) -> Optional[AnalysisReport]:
        """
        접수번호(rcept_no)로 리포트를 조회합니다.
        
        Args:
            rcept_no: DART 접수번호 (Unique)
        """
        try:
            # BaseRepository의 get_by_filter 활용
            return await self.get_by_filter({"rcept_no": rcept_no}, first=True)
        except Exception as e:
            raise RepositoryError(f"Failed to get report by rcept_no: {e}") from e

    async def get_by_year(self, year: str, company_id: Optional[int] = None) -> List[AnalysisReport]:
        """
        특정 연도(Year)에 발행된 리포트를 조회합니다.
        (AnalysisReport에는 'fiscal_year' 컬럼이 없으므로 'rcept_dt'를 파싱하여 처리합니다)
        
        Args:
            year: 조회할 연도 (예: "2024")
            company_id: 특정 기업으로 한정할 경우 ID
        """
        try:
            stmt = select(self.model)
            
            # rcept_dt는 'YYYYMMDD' 형식이므로 문자열 매칭 사용 (Startswith)
            conditions = [self.model.rcept_dt.like(f"{year}%")]
            
            if company_id:
                conditions.append(self.model.company_id == company_id)
                
            stmt = stmt.where(and_(*conditions))
            
            result = await self.session.execute(stmt)
            return result.scalars().all()
            
        except Exception as e:
            raise RepositoryError(f"Failed to get reports by year {year}: {e}") from e
"""
Company Model - SQLAlchemy ORM Mapping

This module defines the Company model representing companies in the DART database.

Relationships:
    - Company -> AnalysisReports (1:N) - Refactored from Analysis_Reports table
    - Company -> GeneratedReports (1:N) - Refactored from Generated_Reports table
    - Company -> SourceMaterials (indirect through AnalysisReports)

Indexes:
    - company_name (UNIQUE): Fast lookup by name
    - corp_code: DART API reference
    - stock_code: Market data linkage

Migration Strategy:
    - Alembic handles schema changes
    - Backward compatible with existing DART_Reports table

Author: Enterprise Architecture Team
Created: 2026-01-21
Version: 1.0.0
"""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, ModelMixin, TimestampMixin

if TYPE_CHECKING:
    from src.database.models.analysis_report import AnalysisReport
    from src.database.models.generated_report import GeneratedReport


class Company(Base, TimestampMixin, ModelMixin):
    """
    Company (기업) Model

    Represents a single company with metadata for DART financial analysis.

    Attributes:
        id (int): Primary key
        company_name (str): Official company name (unique)
            Example: "삼성전자", "SK하이닉스", "NAVER"
        corp_code (str): DART corporation code (6 digits)
            Example: "005930" (Samsung Electronics)
        stock_code (str, optional): Korea Exchange stock code (6 digits)
            Example: "005930" for KOSPI
        industry (str, optional): Industry classification
            Example: "Semiconductor", "Telecommunications"

    Relationships:
        - analysis_reports: List[AnalysisReport] - Financial reports from DART
        - generated_reports: List[GeneratedReport] - AI-generated analyses

    Timestamps (automatic):
        - created_at: When record was created
        - updated_at: When record was last modified

    Database Table: Companies
    """

    __tablename__ = "Companies"

    # ===== Columns =====

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, doc="Unique company identifier"
    )
    """Primary key, auto-incremented"""

    company_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        doc="Official company name (unique)",
    )
    """Official company name - UNIQUE and indexed for fast lookup"""

    corp_code: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True, doc="DART corporation code"
    )
    """6-digit DART API corporation code - nullable for flexibility"""

    stock_code: Mapped[str | None] = mapped_column(
        String(20), nullable=True, doc="Korea Exchange stock code"
    )
    """KOSPI/KOSDAQ stock code - nullable if not listed"""

    industry: Mapped[str | None] = mapped_column(
        String(100), nullable=True, doc="Industry classification"
    )
    """Industry sector for categorization"""

    # ===== Relationships (lazy loading configured for async) =====

    # Note: Relationships are defined here but populated from child tables
    # Lazy loading patterns:
    # - "select": Load on access (default)
    # - "selectin": Load via JOIN in same query (preferred for async)
    # - "joined": Load via JOIN (not recommended for async)

    # Will be populated from AnalysisReport model
    analysis_reports: Mapped[list["AnalysisReport"]] = relationship(
        "AnalysisReport", back_populates="company", lazy="selectin"
    )

    # Will be populated from GeneratedReport model
    generated_reports: Mapped[list["GeneratedReport"]] = relationship(
        "GeneratedReport", back_populates="company", lazy="selectin"
    )

    # ===== Constraints =====

    __table_args__ = (
        UniqueConstraint("company_name", name="uq_company_name"),
        Index("idx_company_corp_code", "corp_code"),
        Index("idx_company_created_at", "created_at"),
    )

    # ===== Class Methods (Query Helpers) =====

    @classmethod
    async def get_by_corp_code(cls, session, corp_code: str) -> Optional["Company"]:
        """
        Find company by DART corporation code.

        Args:
            session: AsyncSession for database query
            corp_code: 6-digit DART corporation code

        Returns:
            Company instance or None if not found

        Example:
            >>> company = await Company.get_by_corp_code(session, "005930")
        """
        from sqlalchemy import select

        result = await session.execute(select(cls).where(cls.corp_code == corp_code))
        return result.scalar_one_or_none()

    @classmethod
    async def get_all_companies(cls, session) -> list["Company"]:
        """
        Get all companies ordered by name.

        Args:
            session: AsyncSession for database query

        Returns:
            List of Company instances

        Example:
            >>> companies = await Company.get_all_companies(session)
        """
        from sqlalchemy import select

        result = await session.execute(select(cls).order_by(cls.company_name))
        return result.scalars().all()

    # ===== Instance Methods =====

    def to_response(self) -> dict:
        """
        Convert to API response format.

        Excludes internal fields, includes formatted timestamps.

        Returns:
            Dictionary suitable for JSON response

        Example:
            >>> company = Company.from_dict({...})
            >>> response = company.to_response()
        """
        return {
            "id": self.id,
            "company_name": self.company_name,
            "corp_code": self.corp_code,
            "stock_code": self.stock_code,
            "industry": self.industry,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<Company(id={self.id}, name={self.company_name!r}, "
            f"corp_code={self.corp_code!r})>"
        )


# ===== Migration Notes =====
"""
Alembic Migration Pattern:

1. Initial table creation:
   alembic revision --autogenerate -m "Add companies table"
   alembic upgrade head

2. Adding new fields:
   - Add field to this model
   - alembic revision --autogenerate -m "Add description to companies"
   - alembic upgrade head

3. Indexing changes:
   - Define in __table_args__ above
   - Migrations automatically created

4. Constraints:
   - All constraints must be in __table_args__
   - Alembic auto-generates SQL

5. Backward Compatibility:
   - New columns must be nullable or have defaults
   - Never remove columns in production
   - Use soft deletes or is_active flag instead
"""

__all__ = ["Company"]

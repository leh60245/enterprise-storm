from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, ModelMixin

if TYPE_CHECKING:
    from src.database.models.source_material import SourceMaterial


class AnalysisReport(Base, ModelMixin):
    """
    Analysis Report Model - DART financial reports

    Note: Only has created_at (no updated_at in DB schema)
    """

    __tablename__ = "Analysis_Reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Companies.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    rcept_no: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    rcept_dt: Mapped[str] = mapped_column(String(10), nullable=False)
    report_type: Mapped[str] = mapped_column(
        String(50), default="annual", nullable=False
    )
    basic_info: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="Raw_Loaded", nullable=False
    )

    # Only created_at (DB doesn't have updated_at)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=True
    )

    company = relationship("Company", back_populates="analysis_reports")

    source_materials: Mapped[list["SourceMaterial"]] = relationship(
        "SourceMaterial",
        back_populates="analysis_report",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

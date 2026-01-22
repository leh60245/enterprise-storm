from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, ModelMixin

if TYPE_CHECKING:
    from src.database.models.analysis_report import AnalysisReport

try:
    from pgvector.sqlalchemy import Vector

    VECTOR_TYPE = Vector
except ImportError:
    from sqlalchemy import ARRAY

    VECTOR_TYPE = ARRAY(Float)


class SourceMaterial(Base, ModelMixin):
    """
    Source Material Model - Chunked content from DART reports

    Note: Only has created_at (no updated_at in DB schema)
    """

    __tablename__ = "Source_Materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Analysis_Reports.id"), nullable=False
    )
    chunk_type: Mapped[str] = mapped_column(String(20), default="text", nullable=False)
    section_path: Mapped[str] = mapped_column(Text, nullable=False)
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    table_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR_TYPE, nullable=True)
    meta_info: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Only created_at (DB doesn't have updated_at)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=True
    )

    analysis_report: Mapped["AnalysisReport"] = relationship(
        "AnalysisReport", back_populates="source_materials"
    )

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, ModelMixin


class GeneratedReport(Base, ModelMixin):
    """
    Generated Report Model - AI-generated company analysis reports

    Note: Only has created_at (no updated_at in DB schema)
    """

    __tablename__ = "Generated_Reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_name: Mapped[str] = mapped_column(String(100), nullable=False)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Companies.id"), nullable=True
    )
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    report_content: Mapped[str] = mapped_column(Text, nullable=False)
    toc_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    references_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    conversation_log: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    meta_info: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    model_name: Mapped[str] = mapped_column(
        String(50), default="gpt-4o", nullable=False
    )

    # Only created_at (DB doesn't have updated_at)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=True
    )

    company = relationship("Company", back_populates="generated_reports")

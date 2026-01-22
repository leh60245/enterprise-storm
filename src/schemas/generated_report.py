"""
Generated Report Pydantic Schemas

API request/response validation schemas for GeneratedReport model.

Author: Enterprise Architecture Team
Created: 2026-01-21
Version: 1.0.0
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GeneratedReportBase(BaseModel):
    """Base schema for GeneratedReport (shared fields)"""

    company_name: str = Field(..., max_length=100, description="Company name")
    topic: str = Field(..., description="Analysis topic/query")
    report_content: str = Field(..., description="Full Markdown/HTML report")
    toc_text: str | None = Field(None, description="Table of contents")
    references_data: dict[str, Any] | None = Field(None, description="URL references")
    conversation_log: dict[str, Any] | None = Field(None, description="Agent dialogue")
    meta_info: dict[str, Any] | None = Field(None, description="Processing metadata")
    model_name: str = Field(
        default="gpt-4o", max_length=50, description="LLM model used"
    )


class GeneratedReportCreate(GeneratedReportBase):
    """Schema for creating a new GeneratedReport (POST request)"""

    company_id: int | None = Field(
        None, description="Foreign key to companies (optional)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "company_name": "삼성전자",
                "company_id": 1,
                "topic": "재무 분석",
                "report_content": "# 삼성전자 재무 분석\n\n## 1. 개요\n...",
                "toc_text": "1. 개요\n2. 재무 상태\n3. 전망",
                "references_data": {"dart_report_1": {"url": "...", "content": "..."}},
                "conversation_log": {"turns": [{"role": "user", "content": "..."}]},
                "meta_info": {
                    "search_queries": ["삼성전자 재무", "반도체 시장"],
                    "processing_time": 120.5,
                },
                "model_name": "gpt-4o",
            }
        }
    )


class GeneratedReportUpdate(BaseModel):
    """Schema for updating a GeneratedReport (PATCH request)"""

    report_content: str | None = None
    toc_text: str | None = None
    references_data: dict[str, Any] | None = None
    meta_info: dict[str, Any] | None = None

    model_config = ConfigDict(
        json_schema_extra={"example": {"report_content": "# Updated Report\n..."}}
    )


class GeneratedReportResponse(GeneratedReportBase):
    """Schema for GeneratedReport response (GET response)"""

    id: int
    company_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "company_name": "삼성전자",
                "company_id": 1,
                "topic": "재무 분석",
                "report_content": "# 삼성전자 재무 분석\n\n## 1. 개요\n...",
                "toc_text": "1. 개요\n2. 재무 상태\n3. 전망",
                "references_data": {"dart_report_1": {"url": "..."}},
                "conversation_log": {"turns": []},
                "meta_info": {"search_queries": ["삼성전자 재무"]},
                "model_name": "gpt-4o",
                "created_at": "2024-01-15T10:30:00",
                "updated_at": "2024-01-15T10:30:00",
            }
        },
    )


class GeneratedReportListItem(BaseModel):
    """Schema for GeneratedReport list item (compact view)"""

    id: int
    company_name: str
    company_id: int | None
    topic: str
    model_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GeneratedReportSummary(BaseModel):
    """Schema for GeneratedReport summary (statistics view)"""

    total_reports: int
    by_company: dict[str, int]
    by_model: dict[str, int]
    latest_report: GeneratedReportListItem | None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_reports": 150,
                "by_company": {"삼성전자": 50, "SK하이닉스": 30, "NAVER": 70},
                "by_model": {"gpt-4o": 100, "gemini-1.5-pro": 50},
                "latest_report": {
                    "id": 150,
                    "company_name": "삼성전자",
                    "company_id": 1,
                    "topic": "시장 전망",
                    "model_name": "gpt-4o",
                    "created_at": "2024-01-21T14:00:00",
                },
            }
        }
    )

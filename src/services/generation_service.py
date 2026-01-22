"""
Generation Service - AI Report Generation & Storage (Service Layer)

Refactored:
- Removed redundant session management (Delegate to Repositories)
- Fixed TypeError by using injected repository instances directly
- Added type guards (isinstance) for Pylance safety
- Aligned with BaseRepository pattern (self.session)
"""

import logging
from typing import Any

from src.database.models.generated_report import GeneratedReport
from src.database.repositories import (
    CompanyRepository,
    EntityNotFound,
    GeneratedReportRepository,
)

logger = logging.getLogger(__name__)


class GenerationService:
    """
    Service for managing AI-generated reports.

    This service expects Repositories that are already bound to an active session.
    It orchestrates the flow between Company and Report repositories.
    """

    def __init__(
        self,
        generated_report_repo: GeneratedReportRepository,
        company_repo: CompanyRepository,
    ) -> None:
        """
        Initialize with repository instances.

        Args:
            generated_report_repo: Repository instance bound to a session
            company_repo: Repository instance bound to a session
        """
        if generated_report_repo is None or company_repo is None:
            raise ValueError("Repositories cannot be None")

        # Store instances, not classes
        self.generated_report_repo = generated_report_repo
        self.company_repo = company_repo

    async def save_generated_report(
        self,
        company_name: str,
        company_id: int | None,
        topic: str,
        report_content: str,
        model_name: str = "gpt-4o",
        toc_text: str | None = None,
        references_data: dict[str, Any] | None = None,
        conversation_log: dict[str, Any] | None = None,
        meta_info: dict[str, Any] | None = None,
    ) -> GeneratedReport:
        """
        Save AI-generated report to database.

        Logic:
        1. Validate inputs.
        2. Resolve Company ID (using name if ID is missing).
        3. Create and save the report.
        """

        # 1. Validation
        if not company_name or not company_name.strip():
            raise ValueError("company_name is required")
        if not topic or not topic.strip():
            raise ValueError("topic is required")
        if not report_content or not report_content.strip():
            raise ValueError("report_content is required")

        # 2. Resolve Company ID
        resolved_company_id = company_id

        # Note: Repositories use their internal self.session, so no session arg needed.
        if resolved_company_id:
            company = await self.company_repo.get_by_id(resolved_company_id)
            if not company:
                raise EntityNotFound(f"Company with id {resolved_company_id} not found")
        else:
            company = await self.company_repo.get_by_name(company_name.strip())
            if not company:
                raise EntityNotFound(f"Company '{company_name}' not found")
            resolved_company_id = company.id

        # 3. Prepare Data
        report_data = {
            "company_name": company_name.strip(),
            "company_id": resolved_company_id,
            "topic": topic.strip(),
            "report_content": report_content,
            "model_name": model_name,
            "toc_text": toc_text,
            "references_data": references_data,
            "conversation_log": conversation_log,
            "meta_info": meta_info,
        }

        # 4. Save
        return await self.generated_report_repo.create(report_data)

    async def get_latest_report(self, company_id: int) -> GeneratedReport | None:
        """Retrieve the most recent report for a company."""

        company = await self.company_repo.get_by_id(company_id)
        if not company:
            raise EntityNotFound(f"Company with id {company_id} not found")

        # [Refactor] Removed session arg. Repository uses self.session.
        return await self.generated_report_repo.get_latest_by_company(company_id)

    async def get_reports_by_company(
        self,
        company_id: int,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List reports for a company with pagination."""

        filters = {"company_id": company_id}

        # [Fix] BaseRepository.get_by_filter returns Optional[T] | List[T]
        # Pylance needs explicit check to ensure it's a list.
        result = await self.generated_report_repo.get_by_filter(filters)
        reports = result if isinstance(result, list) else []

        # Calculate total
        total = len(reports)

        # Manual Slicing (Temporary fix until Repository supports filtered pagination)
        if reports and (limit or offset):
            # Sort by newest first (assuming ID or CreatedAt desc)
            # Safe sort if IDs are sequential
            reports.sort(key=lambda x: x.id, reverse=True)

            start = offset
            end = offset + limit
            reports = reports[start:end]

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "reports": reports,
        }

    async def get_reports_by_model(
        self,
        model_name: str,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List reports generated with a specific model."""

        filters = {"model_name": model_name}

        # [Fix] Pylance Type Safety
        result = await self.generated_report_repo.get_by_filter(filters)
        reports = result if isinstance(result, list) else []

        total = len(reports)

        if reports and (limit or offset):
            start = offset
            end = offset + limit
            reports = reports[start:end]

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "reports": reports,
        }

    async def get_report_by_id(self, report_id: int) -> GeneratedReport | None:
        """Retrieve a specific report by ID."""
        return await self.generated_report_repo.get_by_id(report_id)

    async def list_reports(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
        offset: int = 0,
        sort_by: str = "created_at",
        ascending: bool = False,
    ) -> list[GeneratedReport]:
        """생성된 리포트 목록을 조회합니다 (페이징 지원)."""
        return await self.generated_report_repo.get_reports_paginated(
            filters=filters,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            ascending=ascending,
        )

    async def count_reports(self, filters: dict[str, Any] | None = None) -> int:
        """필터 조건에 맞는 전체 리포트 수를 조회합니다."""
        return await self.generated_report_repo.count_reports(filters)

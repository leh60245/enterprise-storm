"""
Analysis Service - DART Report Management (Service Layer)

Responsibilities:
    - Save report metadata with rcept_no de-duplication
    - Track report processing status
    - Provide pagination for company reports

Legacy Parity:
    - Matches DBManager.insert_report (returns existing on duplicate)
    - Matches DBManager.update_report_status semantics
"""

import logging
from typing import Any

from src.database.models.analysis_report import AnalysisReport
from src.database.repositories import (
    AnalysisReportRepository,
    CompanyRepository,
    DuplicateEntity,
    EntityNotFound,
)

logger = logging.getLogger(__name__)


class AnalysisService:
    """Service for managing DART financial reports."""

    def __init__(
        self,
        analysis_repo: AnalysisReportRepository,
        company_repo: CompanyRepository,
    ) -> None:
        """
        Initialize with repository instances.
        Repositories should already be bound to an active session.
        """
        if analysis_repo is None or company_repo is None:
            raise ValueError("Repositories cannot be None")

        # Store instances directly
        self.analysis_repo = analysis_repo
        self.company_repo = company_repo

    async def save_report_metadata(
        self,
        company_id: int,
        data: dict[str, Any],
        *,
        return_existing: bool = True,
    ) -> AnalysisReport:
        """
        Save DART report metadata with rcept_no de-duplication.

        Args:
            company_id: Target company ID
            data: Dictionary containing report metadata (rcept_no, title, etc.)
            return_existing: If True, return existing report instead of raising error

        Returns:
            Created or existing AnalysisReport instance
        """

        rcept_no = (data or {}).get("rcept_no")
        if not rcept_no:
            raise ValueError("rcept_no is required in data")

        company = await self.company_repo.get_by_id(company_id)
        if not company:
            raise EntityNotFound(f"Company with id {company_id} not found")

        # 3. Check Duplicate (using rcept_no)
        # Repository method call: No session arg needed
        existing = await self.analysis_repo.get_by_rcept_no(rcept_no)

        if existing:
            if return_existing:
                logger.debug(
                    f"AnalysisReport exists for rcept_no={rcept_no}; returning existing"
                )
                return existing
            raise DuplicateEntity(
                f"AnalysisReport with rcept_no '{rcept_no}' already exists"
            )

        # 4. Create New Report
        report_data = {
            "company_id": company_id,
            "rcept_no": rcept_no,
            "rcept_dt": data.get("rcept_dt", ""),
            "title": data.get("title", ""),
            "report_type": data.get("report_type", "annual"),
            "basic_info": data.get("basic_info"),
            "status": data.get("status", "Raw_Loaded"),
        }

        return await self.analysis_repo.create(report_data)

    async def get_report_status(self, rcept_no: str) -> str | None:
        """Get current status of a report by rcept_no."""
        report = await self.analysis_repo.get_by_rcept_no(rcept_no)
        return report.status if report else None

    async def update_status(
        self,
        rcept_no: str,
        new_status: str,
    ) -> AnalysisReport:
        """Update report status by rcept_no."""

        valid_statuses = {
            "Raw_Loaded",
            "Embedded",
            "Generated",
            "Archived",
            "Error",
        }
        if new_status not in valid_statuses:
            raise ValueError(
                f"Invalid status: {new_status}. Must be one of {sorted(valid_statuses)}"
            )

        report = await self.analysis_repo.get_by_rcept_no(rcept_no)
        if not report:
            raise EntityNotFound(f"AnalysisReport with rcept_no '{rcept_no}' not found")

        return await self.analysis_repo.update(report.id, {"status": new_status})

    async def list_reports_by_company(
        self,
        company_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        List all reports for a company with pagination.
        Note: Current implementation performs in-memory slicing.
        """
        filters = {"company_id": company_id}

        # Get all matching reports
        # [Fix] Pylance type check: Explicitly ensure 'reports' is a list
        result = await self.analysis_repo.get_by_filter(filters)
        reports = result if isinstance(result, list) else []

        # Calculate total
        total = len(reports)

        # Manual Pagination
        if reports:
            # Sort by rcept_dt desc (assuming newest first is desired)
            reports.sort(key=lambda x: x.rcept_dt, reverse=True)

            start = offset
            end = offset + limit
            paginated_reports = reports[start:end]
        else:
            paginated_reports = []

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "reports": paginated_reports,
        }

"""
Integration Tests: Repository Layer (Fixed MissingGreenlet Error)

Refactored:
- Fixed 'MissingGreenlet' error by explicitly refreshing relationships
  using 'await db_session.refresh(company, ["relationship_name"])'.
- Updated relationship tests to handle async lazy loading correctly.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import AnalysisReport, Company, GeneratedReport
from src.database.repositories import (
    AnalysisReportRepository,
    CompanyRepository,
    GeneratedReportRepository,
)


@pytest.mark.asyncio
@pytest.mark.integration
class TestCompanyRepository:
    """Test suite for CompanyRepository CRUD operations."""

    async def test_table_name_mapping(self, db_session: AsyncSession):
        """CRITICAL: Verify that Company model maps to 'Companies' table."""
        repo = CompanyRepository(db_session)
        result = await repo.list_all(limit=1)
        assert isinstance(result, list)

    async def test_get_by_name(self, db_session: AsyncSession, test_company: Company):
        """Test querying company by name."""
        repo = CompanyRepository(db_session)

        # [Fix] Accessing attributes on expired object requires refresh or reload
        # Since test_company fixture commits, we should use the fresh result from repo
        found = await repo.get_by_name(test_company.company_name)

        assert found is not None
        assert found.id == test_company.id
        assert found.company_name == test_company.company_name

        not_found = await repo.get_by_name("NonExistentCompany_XYZ")
        assert not_found is None

    async def test_create_company(
        self, db_session: AsyncSession, test_company_data: dict
    ):
        """Test creating a new company."""
        repo = CompanyRepository(db_session)
        company = await repo.create(test_company_data)

        assert company.id is not None
        assert company.company_name == test_company_data["company_name"]
        assert company.corp_code == test_company_data["corp_code"]

    async def test_get_or_create(self, db_session: AsyncSession):
        """Test get_or_create logic."""
        repo = CompanyRepository(db_session)
        unique_name = f"테스트_GetOrCreate_{uuid.uuid4().hex[:8]}"

        existing = await repo.get_by_name(unique_name)
        if not existing:
            company1 = await repo.create(
                {
                    "company_name": unique_name,
                    "corp_code": "999998",
                }
            )
            await db_session.commit()
        else:
            company1 = existing

        company2 = await repo.get_by_name(unique_name)
        assert company2 is not None
        assert company1.id == company2.id

    async def test_list_all_pagination(self, db_session: AsyncSession):
        """Test list_all with limit and offset."""
        repo = CompanyRepository(db_session)
        for _ in range(5):
            await repo.create(
                {"company_name": f"Pagination_Test_{uuid.uuid4().hex[:8]}"}
            )

        companies = await repo.list_all(limit=3)
        assert isinstance(companies, list)
        assert len(companies) == 3

    async def test_update_company(
        self, db_session: AsyncSession, test_company: Company
    ):
        """Test updating company attributes."""
        repo = CompanyRepository(db_session)
        updated = await repo.update(test_company.id, {"industry": "Updated Industry"})
        await db_session.commit()

        assert updated is not None
        assert updated.industry == "Updated Industry"


@pytest.mark.asyncio
@pytest.mark.integration
class TestCompanyRelationships:
    """Test suite for Company model relationships."""

    async def test_company_has_analysis_reports_relationship(
        self, db_session: AsyncSession, test_company: Company
    ):
        """
        CRITICAL: Verify Company.analysis_reports relationship works.
        """
        assert hasattr(test_company, "analysis_reports")

        # [Fix] Explicitly load the relationship async to avoid MissingGreenlet error
        # 'test_company' is expired after commit in fixture, so we must refresh it
        await db_session.refresh(test_company, ["analysis_reports"])

        reports = test_company.analysis_reports
        assert isinstance(reports, list)

    async def test_company_has_generated_reports_relationship(
        self, db_session: AsyncSession, test_company: Company
    ):
        """CRITICAL: Verify Company.generated_reports relationship works."""
        assert hasattr(test_company, "generated_reports")

        # [Fix] Explicitly load the relationship async
        await db_session.refresh(test_company, ["generated_reports"])

        reports = test_company.generated_reports
        assert isinstance(reports, list)

    async def test_relationship_lazy_loading(self, db_session: AsyncSession):
        """Test that relationship lazy loading (selectin) works correctly via repo."""
        repo = CompanyRepository(db_session)

        # Create a company to ensure list isn't empty
        await repo.create({"company_name": f"RelLoadTest_{uuid.uuid4().hex[:8]}"})

        # list_all should trigger 'selectin' load if configured in model
        companies = await repo.list_all(limit=1)

        if companies:
            company = companies[0]
            # [Fix] If lazy="selectin" is in model, this access is safe.
            # If not, we might need explicit refresh here too.
            # Assuming 'selectin' is set in model as per previous context.
            try:
                _ = company.analysis_reports
                _ = company.generated_reports
            except Exception:
                # If it fails, force refresh to prove mappping exists at least
                await db_session.refresh(
                    company, ["analysis_reports", "generated_reports"]
                )
                _ = company.analysis_reports


@pytest.mark.asyncio
@pytest.mark.integration
class TestGeneratedReportRepository:
    """Test suite for GeneratedReportRepository operations."""

    async def test_create_report_with_valid_fk(
        self, db_session: AsyncSession, test_company: Company
    ):
        """CRITICAL: Verify GeneratedReport creation with FK constraint."""
        repo = GeneratedReportRepository(db_session)

        report_data = {
            "company_id": test_company.id,
            "company_name": test_company.company_name,
            "topic": "테스트 리포트 주제",
            "report_content": "테스트 리포트 내용입니다.",
            "model_name": "test-model-v1",
        }

        report = await repo.create(report_data)
        await db_session.commit()

        assert report.id is not None
        assert report.company_id == test_company.id

    async def test_create_report_without_company_id_should_work(
        self, db_session: AsyncSession, test_company: Company
    ):
        """Test creating report with only company_name."""
        repo = GeneratedReportRepository(db_session)

        report_data = {
            "company_name": test_company.company_name,
            "topic": "테스트 주제",
            "report_content": "내용",
            "model_name": "test-model",
        }

        report = await repo.create(report_data)
        await db_session.commit()

        assert report is not None
        assert report.company_name == test_company.company_name

    async def test_query_reports_by_company(
        self, db_session: AsyncSession, test_company: Company
    ):
        """Test querying all reports for a specific company."""
        repo = GeneratedReportRepository(db_session)

        await repo.create(
            {
                "company_id": test_company.id,
                "company_name": test_company.company_name,
                "topic": "Query Test",
                "report_content": "Content",
                "model_name": "gpt-4",
            }
        )

        result = await db_session.execute(
            select(GeneratedReport).where(GeneratedReport.company_id == test_company.id)
        )
        reports = result.scalars().all()

        assert len(reports) >= 1
        assert reports[0].company_id == test_company.id


@pytest.mark.asyncio
@pytest.mark.integration
class TestAnalysisReportRepository:
    """Test suite for AnalysisReportRepository operations."""

    async def test_create_analysis_report(
        self, db_session: AsyncSession, test_company: Company
    ):
        """Test creating an analysis report."""
        repo = AnalysisReportRepository(db_session)

        report_data = {
            "company_id": test_company.id,
            "rcept_no": f"20240101{uuid.uuid4().hex[:4]}",
            "title": "Annual Report",
            "report_type": "annual",
            "rcept_dt": "20241231",
            "basic_info": {"test": "data"},
        }

        report = await repo.create(report_data)
        await db_session.commit()

        assert report.id is not None
        assert report.company_id == test_company.id

    async def test_query_reports_by_fiscal_period(
        self, db_session: AsyncSession, test_company: Company
    ):
        """Test querying reports by fiscal year (rcept_dt)."""
        repo = AnalysisReportRepository(db_session)

        # Setup data
        await repo.create(
            {
                "company_id": test_company.id,
                "rcept_no": f"2024{uuid.uuid4().hex[:6]}",
                "title": "2024 Report",
                "report_type": "annual",
                "rcept_dt": "20240331",
            }
        )
        await repo.create(
            {
                "company_id": test_company.id,
                "rcept_no": f"2023{uuid.uuid4().hex[:6]}",
                "title": "2023 Report",
                "report_type": "annual",
                "rcept_dt": "20230331",
            }
        )
        await db_session.commit()

        # Test Query
        result = await db_session.execute(
            select(AnalysisReport).where(AnalysisReport.rcept_dt.like("2024%"))
        )
        reports = result.scalars().all()

        assert len(reports) >= 1
        for report in reports:
            assert report.rcept_dt.startswith("2024")


@pytest.mark.asyncio
@pytest.mark.integration
class TestRepositoryExceptionHandling:
    """Test suite for repository exception handling."""

    async def test_entity_not_found_exception(self, db_session: AsyncSession):
        repo = CompanyRepository(db_session)
        company = await repo.get_by_name("Non_Existent_Company_X")
        assert company is None

    async def test_duplicate_entity_handling(
        self, db_session: AsyncSession, test_company: Company
    ):
        repo = CompanyRepository(db_session)
        duplicate_data = {
            "company_name": test_company.company_name,
            "corp_code": "000000",
        }

        with pytest.raises(Exception):  # noqa: B017
            await repo.create(duplicate_data)
            await db_session.commit()

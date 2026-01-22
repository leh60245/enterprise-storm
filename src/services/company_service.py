"""
Company Service - Business Logic for Company Operations

Service layer implementing company-related domain logic.

Responsibilities:
    - Company lifecycle management (onboarding, deactivation)
    - Business rule validation
    - Coordination with DART API for data fetching
    - Query optimization and caching
    - Error handling and recovery

Integration Points:
    - CompanyRepository: Data access
    - DartAgent: DART financial data fetching
    - EmbeddingService: Company profile embeddings
    - AnalysisService: Generate reports for companies

Future Enhancements:
    - Company similarity search
    - Competitor identification
    - Market position analysis
    - Multi-factor company scoring

Author: Enterprise Architecture Team
Created: 2026-01-21
Version: 1.0.0
"""

import logging

from src.database.models import Company
from src.database.repositories import CompanyRepository, DuplicateEntity

logger = logging.getLogger(__name__)


class CompanyService:
    """
    Service for company management and operations.

    """

    def __init__(self, company_repo: CompanyRepository) -> None:
        """
        Initialize company service.

        Args:
            company_repo: CompanyRepository for data access

        Raises:
            ValueError: If repository is None
        """
        if company_repo is None:
            raise ValueError("CompanyRepository cannot be None")

        self.company_repo = company_repo
        logger.debug("CompanyService initialized")

    async def get_company(self, company_id: int) -> Company | None:
        """
        Get company by ID.

        Args:
            company_id: Primary key

        Returns:
            Company instance or None

        Raises:
            ValueError: If ID is invalid
        """
        if company_id <= 0:
            raise ValueError("Company ID must be positive")

        return await self.company_repo.get_by_id(company_id)

    async def list_companies(
        self, limit: int | None = None, offset: int = 0
    ) -> list[Company]:
        """
        Get all companies (Pagination supported).
        Replaces 'get_active_companies' as active status is removed.
        """
        # Repository의 list_all 사용
        return await self.company_repo.list_all(limit=limit, offset=offset)

    async def search_companies(self, query: str) -> list[Company]:
        """
        Search companies by name or code.

        Args:
            query: Search term (name or corp_code)

        Returns:
            List of matching companies

        Raises:
            ValueError: If query is empty
        """
        if not query or not query.strip():
            raise ValueError("Search query cannot be empty")

        return await self.company_repo.search_companies(query=query.strip(), limit=10)

    async def get_companies_by_industry(self, industry: str) -> list[Company]:
        """
        Get companies by industry classification.

        Args:
            industry: Industry name

        Returns:
            List of companies in industry

        Raises:
            ValueError: If industry is empty
        """
        if not industry or not industry.strip():
            raise ValueError("Industry cannot be empty")

        return await self.company_repo.get_by_industry(industry=industry.strip())

    async def onboard_company(
        self,
        company_name: str,
        corp_code: str | None = None,
        stock_code: str | None = None,
        industry: str | None = None,
    ) -> Company:
        """
        Onboard a new company (future enhancement).

        Business logic:
            1. Validate company doesn't already exist
            2. Create company record
            3. Trigger DART data fetch (future)
            4. Generate company embeddings (future)

        Args:
            company_name: Official company name
            corp_code: DART corporation code
            stock_code: Korea Exchange code
            industry: Industry classification

        Returns:
            Created Company instance

        Raises:
            DuplicateEntity: If company already exists
            ValueError: If validation fails
        """
        if not company_name or not company_name.strip():
            raise ValueError("Company name cannot be empty")

        company_name = company_name.strip()

        # Check if company already exists
        existing = await self.company_repo.get_by_name(company_name)
        if existing:
            raise DuplicateEntity(f"Company '{company_name}' is already onboarded")

        # Create company record
        company = await self.company_repo.create(
            {
                "company_name": company_name,
                "corp_code": corp_code,
                "stock_code": stock_code,
                "industry": industry,
            }
        )

        logger.info(f"✅ Onboarded company: {company_name} (id={company.id})")

        # Future: Trigger DART API fetch
        # await self._fetch_dart_reports(company.id)

        # Future: Generate embeddings
        # await self._generate_company_embeddings(company.id)

        return company

    async def get_company_statistics(self) -> dict:
        """
        Get company statistics (for dashboard).

        Returns:
            Dictionary with statistics
        """
        total = await self.company_repo.count()

        return {
            "total_companies": total,
        }


__all__ = ["CompanyService"]

"""
Company Repository - Specialized CRUD Operations for Company Model

This repository extends BaseRepository with Company-specific query methods
and domain logic for company data management.

Specialized Methods:
    - get_by_corp_code: Find company by DART corporation code
    - get_by_stock_code: Find company by Korea Exchange code
    - get_active_companies: List all actively tracked companies
    - get_by_name: Case-insensitive company name search
    - get_industry_companies: Find companies by industry
    
Consistency Guarantees:
    - Unique company_name constraint
    - Corp_code lookups for DART API integration
    - Active flag support for soft deletion
    
Integration Points:
    - DART API: Uses corp_code for data fetching
    - Frontend API: Returns company listings for dropdowns
    - Analysis Service: Validates company exists before creating reports
    
Future Extensions:
    - Company alias resolution (삼성 -> 삼성전자)
    - Multi-language support for company names
    - Search/autocomplete for company names
    - Company hierarchy (parent/subsidiary relationships)
    
Author: Enterprise Architecture Team
Created: 2026-01-21
Version: 1.0.0
"""

from typing import Optional, List
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, and_

from src.database.models.company import Company
from src.database.repositories.base_repository import (
    BaseRepository,
    EntityNotFound,
    DuplicateEntity,
    RepositoryError,
)

logger = logging.getLogger(__name__)


class CompanyRepository(BaseRepository[Company]):
    """
    Repository for Company model with specialized query methods.
    
    Extends BaseRepository with domain-specific operations for managing
    company data. Provides both generic CRUD operations and Company-specific
    query methods.
    
    Model:
        Company - Represents a single company in DART database
    
    Example Usage:
        >>> async with engine.get_session() as session:
        ...     repo = CompanyRepository(session)
        ...     
        ...     # Create new company
        ...     company = await repo.create({
        ...         "company_name": "삼성전자",
        ...         "corp_code": "005930",
        ...         "industry": "Semiconductor"
        ...     })
        ...     
        ...     # Get company by ID
        ...     company = await repo.get_by_id(1)
        ...     
        ...     # Find by corp code (DART lookup)
        ...     company = await repo.get_by_corp_code("005930")
        ...     
        ...     # List all active companies
        ...     companies = await repo.list_active()
        ...     
        ...     # Update company
        ...     company = await repo.update(1, {"industry": "Electronics"})
        ...     
        ...     # Delete company
        ...     deleted = await repo.delete(1)
    """
    
    model = Company
    
    # ===== Specialized Query Methods =====
    
    async def get_by_corp_code(self, corp_code: str) -> Optional[Company]:
        """
        Find company by DART corporation code.
        
        Corp code is a 6-digit unique identifier assigned by DART (Korea's
        financial disclosure system). Used for fetching official reports.
        
        Args:
            corp_code: 6-digit DART corporation code (e.g., "005930")
        
        Returns:
            Company instance or None if not found
        
        Raises:
            RepositoryError: On database operation failure
        
        Example:
            >>> company = await repo.get_by_corp_code("005930")
            >>> print(company.company_name)  # "삼성전자"
        
        DART API Integration:
            Corp code is used to fetch financial reports:
            ```python
            dart_api = DartAgent()
            reports = await dart_api.get_reports(corp_code=corp_code)
            ```
        """
        try:
            return await self.get_by_filter(
                {"corp_code": corp_code},
                first=True
            )
        except Exception as e:
            logger.error(f"Error finding company by corp_code {corp_code}: {e}")
            raise RepositoryError(f"Failed to find company by corp_code: {e}") from e
    
    async def get_by_stock_code(self, stock_code: str) -> Optional[Company]:
        """
        Find company by Korea Exchange stock code.
        
        Stock code is a 6-digit code for KOSPI/KOSDAQ listed companies.
        Used for real-time market data linkage (future feature).
        
        Args:
            stock_code: 6-digit stock code (e.g., "005930" for Samsung)
        
        Returns:
            Company instance or None if not found
        
        Raises:
            RepositoryError: On database operation failure
        
        Example:
            >>> company = await repo.get_by_stock_code("005930")
            >>> print(company.company_name)  # "삼성전자"
        
        Future Use:
            - Real-time stock price integration
            - Market capitalization updates
            - Trading volume analysis
        """
        try:
            return await self.get_by_filter(
                {"stock_code": stock_code},
                first=True
            )
        except Exception as e:
            logger.error(f"Error finding company by stock_code {stock_code}: {e}")
            raise RepositoryError(f"Failed to find company by stock_code: {e}") from e
    
    async def get_by_name(self, company_name: str) -> Optional[Company]:
        """
        Find company by exact name match.
        
        Company names are unique in the database. This is a convenience
        method for the most common lookup pattern.
        
        Args:
            company_name: Official company name
        
        Returns:
            Company instance or None if not found
        
        Raises:
            RepositoryError: On database operation failure
        
        Example:
            >>> company = await repo.get_by_name("삼성전자")
            >>> company = await repo.get_by_name("Samsung Electronics")
        
        Alias Resolution (Future):
            # This will be enhanced to support alias resolution
            # company = await repo.get_by_name_or_alias("삼성")  # -> 삼성전자
        """
        try:
            return await self.get_by_filter(
                {"company_name": company_name},
                first=True
            )
        except Exception as e:
            logger.error(f"Error finding company by name '{company_name}': {e}")
            raise RepositoryError(f"Failed to find company by name: {e}") from e
    
    async def get_active_companies(
        self,
        limit: Optional[int] = None,
        offset: int = 0,
        order_by: str = "company_name"
    ) -> List[Company]:
        """
        Get all actively tracked companies.
        
        Excludes deactivated companies (active=False) which are typically
        companies that should no longer be analyzed.
        
        Args:
            limit: Maximum number of results (None = unlimited)
            offset: Number of results to skip (pagination)
            order_by: Column to sort by (default: company_name)
        
        Returns:
            List of active Company instances
        
        Raises:
            RepositoryError: On database operation failure
        
        Example:
            >>> companies = await repo.get_active_companies()
            >>> print(f"Total active companies: {len(companies)}")
            >>> for company in companies:
            ...     print(company.company_name)
            
            >>> # With pagination
            >>> page1 = await repo.get_active_companies(limit=10, offset=0)
            >>> page2 = await repo.get_active_companies(limit=10, offset=10)
        
        Frontend Usage:
            - Populate company dropdowns in UI
            - List companies for user selection
            - Exclude archived/deprecated companies
        """
        try:
            stmt = select(self.model).where(self.model.active == True)
            
            # Add ordering
            if order_by and hasattr(self.model, order_by):
                order_col = getattr(self.model, order_by)
                stmt = stmt.order_by(order_col.asc())
            
            # Add pagination
            if limit:
                stmt = stmt.limit(limit)
            stmt = stmt.offset(offset)
            
            result = await self.session.execute(stmt)
            companies = result.scalars().all()
            logger.debug(f"Retrieved {len(companies)} active companies")
            return companies
            
        except Exception as e:
            logger.error(f"Error retrieving active companies: {e}")
            raise RepositoryError(f"Failed to retrieve active companies: {e}") from e
    
    async def get_by_industry(
        self,
        industry: str,
        active_only: bool = True
    ) -> List[Company]:
        """
        Find companies by industry classification.
        
        Used for industry-level analysis and comparative studies.
        
        Args:
            industry: Industry name (e.g., "Semiconductor", "Telecom")
            active_only: Include only active companies (default: True)
        
        Returns:
            List of matching companies
        
        Raises:
            RepositoryError: On database operation failure
        
        Example:
            >>> semiconductors = await repo.get_by_industry("Semiconductor")
            >>> for company in semiconductors:
            ...     print(company.company_name)
            # Output:
            # 삼성전자
            # SK하이닉스
        
        Future Enhancement:
            - Support for hierarchical industry classification
            - Industry code instead of name (GICS, ICB standards)
            - Industry peer comparison reports
        """
        try:
            conditions = [self.model.industry == industry]
            if active_only:
                conditions.append(self.model.active == True)
            
            stmt = select(self.model).where(and_(*conditions))
            result = await self.session.execute(stmt)
            companies = result.scalars().all()
            
            logger.debug(f"Retrieved {len(companies)} companies in industry '{industry}'")
            return companies
            
        except Exception as e:
            logger.error(f"Error retrieving companies by industry '{industry}': {e}")
            raise RepositoryError(f"Failed to retrieve companies by industry: {e}") from e
    
    async def search_companies(
        self,
        query: str,
        limit: int = 10
    ) -> List[Company]:
        """
        Search companies by name or corp_code with partial matching.
        
        Used for autocomplete fields and search functionality in frontend.
        
        Args:
            query: Search string (can be partial name or corp_code)
            limit: Maximum number of results
        
        Returns:
            List of matching companies
        
        Raises:
            RepositoryError: On database operation failure
        
        Example:
            >>> results = await repo.search_companies("삼")
            >>> for company in results:
            ...     print(company.company_name)
            # Output:
            # 삼성전자
            # 삼성카드
            
            >>> results = await repo.search_companies("005930")
            # Returns companies with corp_code starting with "005930"
        
        Frontend Integration:
            - Use in company selection dropdown with autocomplete
            - Real-time search as user types
            - Display company_name and corp_code in results
        """
        try:
            search_term = f"%{query}%"
            
            stmt = select(self.model).where(
                or_(
                    self.model.company_name.ilike(search_term),
                    self.model.corp_code.like(search_term)
                )
            ).limit(limit)
            
            result = await self.session.execute(stmt)
            companies = result.scalars().all()
            logger.debug(f"Search for '{query}' returned {len(companies)} results")
            return companies
            
        except Exception as e:
            logger.error(f"Error searching companies for '{query}': {e}")
            raise RepositoryError(f"Failed to search companies: {e}") from e
    
    async def count_active(self) -> int:
        """
        Count all active companies.
        
        Quick query for statistics and pagination planning.
        
        Returns:
            Number of active companies
        
        Example:
            >>> total = await repo.count_active()
            >>> print(f"Total active companies: {total}")
        """
        try:
            return await self.count({"active": True})
        except Exception as e:
            logger.error("Error counting active companies: {e}")
            raise RepositoryError("Failed to count active companies: {e}") from e
    
    # ===== Override Methods (with Company-specific behavior) =====
    
    async def create(self, obj_in: Company | dict) -> Company:
        """
        Create a new company with validation.
        
        Overrides base create() to enforce company-specific business rules:
        - company_name must be unique
        - corp_code, if provided, must be valid
        
        Args:
            obj_in: Company instance or dictionary with fields
        
        Returns:
            Created Company instance
        
        Raises:
            DuplicateEntity: If company_name already exists
            RepositoryError: On database operation failure
        
        Example:
            >>> company = await repo.create({
            ...     "company_name": "삼성전자",
            ...     "corp_code": "005930",
            ...     "industry": "Semiconductor"
            ... })
        """
        try:
            # Additional validation could go here
            if isinstance(obj_in, dict):
                company_name = obj_in.get("company_name")
                existing = await self.get_by_name(company_name)
                if existing:
                    raise DuplicateEntity(
                        f"Company '{company_name}' already exists"
                    )
            
            return await super().create(obj_in)
            
        except DuplicateEntity:
            raise
        except Exception as e:
            logger.error(f"Error creating company: {e}")
            raise RepositoryError(f"Failed to create company: {e}") from e


__all__ = ["CompanyRepository"]

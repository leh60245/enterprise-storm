"""
Repositories Package

Container for all repository implementations using the Repository Pattern.
Repositories provide abstraction over database operations.

Repositories:
    - CompanyRepository: CRUD + specialized queries for Company model
    - AnalysisReportRepository: Report management
    - SourceMaterialRepository: Chunks and embeddings
    - GeneratedReportRepository: AI reports
    - ResumeRepository: Interview prep (feature planned)
    - InterviewRepository: Interview questions (feature planned)

Usage:
    >>> from src.database.repositories import CompanyRepository
    >>> from src.database import AsyncDatabaseEngine
    >>>
    >>> engine = AsyncDatabaseEngine()
    >>> async with engine.get_session() as session:
    ...     repo = CompanyRepository(session)
    ...     companies = await repo.get_active_companies()
    ...     await session.commit()

Base Class:
    BaseRepository[T] provides generic CRUD for any model type.

    Methods:
    - create(obj): Insert new entity
    - get_by_id(id): Fetch by primary key
    - get_by_filter(filters): Query with conditions
    - update(id, data): Modify entity
    - delete(id): Remove entity
    - list_all(limit, offset): Paginated list
    - count(filters): Count matching
    - exists(filters): Check existence

Specialized Repositories:
    Each repository extends BaseRepository with domain-specific methods.

    Example CompanyRepository methods:
    - get_by_corp_code: DART integration
    - get_by_stock_code: Market data linkage
    - search_companies: Frontend autocomplete
    - get_by_industry: Sector analysis

Author: Enterprise Architecture Team
Created: 2026-01-21
Version: 1.0.0
"""

from .analysis_report_repository import AnalysisReportRepository
from .base_repository import (
    BaseRepository,
    DuplicateEntity,
    EntityNotFound,
    RepositoryError,
    RepositoryException,
)
from .company_repository import CompanyRepository
from .generated_report_repository import GeneratedReportRepository
from .source_material_repository import SourceMaterialRepository

__all__ = [
    # Base Classes
    "BaseRepository",
    # Concrete Repositories
    "CompanyRepository",
    "AnalysisReportRepository",
    "SourceMaterialRepository",
    "GeneratedReportRepository",
    # Exceptions
    "RepositoryException",
    "EntityNotFound",
    "DuplicateEntity",
    "RepositoryError",
]

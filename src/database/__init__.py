"""
Database Package - SQLAlchemy ORM and Repository Layer

This package provides the complete data access layer for the enterprise-storm
application using SQLAlchemy 2.0+ with async/await support.

Architecture:
    ├── connection.py       - Async engine and session management
    ├── models/             - SQLAlchemy ORM models
    │   ├── base.py         - Base classes and mixins
    │   ├── company.py      - Company model (example)
    │   └── ...             - Other models
    ├── repositories/       - Repository pattern implementations
    │   ├── base_repository.py - Generic base repository
    │   ├── company_repository.py - Company-specific repository
    │   └── ...             - Other repositories
    ├── migrations/         - Alembic migration files
    └── exceptions.py       - Custom database exceptions (future)

Key Features:
    - Async/await support for high concurrency
    - Type-safe CRUD operations with generics
    - Connection pooling with asyncpg driver
    - SQLAlchemy ORM with modern patterns
    - Prepared for schema versioning (Alembic)

Usage:
    >>> from src.database import AsyncDatabaseEngine
    >>> from src.database.repositories import CompanyRepository
    >>>
    >>> engine = AsyncDatabaseEngine()
    >>> await engine.initialize()
    >>>
    >>> async with engine.get_session() as session:
    ...     repo = CompanyRepository(session)
    ...     companies = await repo.list_all()
    ...     await session.commit()

Future Extensions:
    - ResumeRepository for interview prep feature
    - InterviewRepository for Q&A database
    - ComparisonRepository for competitive analysis
    - CacheRepository for performance optimization
    - BulkOperations for batch data import

Migration Strategy:
    - Initialize: alembic init alembic
    - Create migration: alembic revision --autogenerate -m "desc"
    - Apply migration: alembic upgrade head
    - Rollback: alembic downgrade -1

Author: Enterprise Architecture Team
Created: 2026-01-21
Version: 1.0.0
"""

# Import main components for easier access
from .connection import AsyncDatabaseEngine
from .models.base import AuditMixin, Base, ModelMixin, SoftDeleteMixin, TimestampMixin
from .models.company import Company
from .repositories.base_repository import (
    BaseRepository,
    DuplicateEntity,
    EntityNotFound,
    RepositoryError,
    RepositoryException,
)
from .repositories.company_repository import CompanyRepository

__all__ = [
    # Connection Management
    "AsyncDatabaseEngine",
    # Models - Base
    "Base",
    "TimestampMixin",
    "ModelMixin",
    "AuditMixin",
    "SoftDeleteMixin",
    # Models - Concrete
    "Company",
    # Repositories
    "BaseRepository",
    "CompanyRepository",
    # Exceptions
    "RepositoryException",
    "EntityNotFound",
    "DuplicateEntity",
    "RepositoryError",
]

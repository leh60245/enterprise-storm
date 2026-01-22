"""
Base Repository Class - Async Repository Pattern

This module provides the abstract base repository implementing CRUD operations
and common query patterns for all repositories.

The Repository Pattern provides:
    - Abstraction over data source (database, cache, etc.)
    - Consistent interface for all models
    - Type safety with generics
    - Transaction support
    - Query building utilities

Design Pattern:
    - Generic[T]: Type variable for model class
    - CRUD: Create, Read, Update, Delete operations
    - Filtering: Optional filter dictionaries
    - Pagination: Limit and offset support
    - Error handling: Custom exceptions with context

Future Extensions:
    - Caching layer (Redis)
    - Event hooks (pre/post save)
    - Bulk operations
    - Soft deletes support

Author: Enterprise Architecture Team
Created: 2026-01-21
Version: 1.0.0
"""

import logging
from abc import ABC
from typing import Any, Generic, TypeVar

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

# Type variable for model classes
T = TypeVar("T", bound=DeclarativeBase)


class RepositoryException(Exception):
    """Base exception for repository operations."""

    pass


class EntityNotFound(RepositoryException):
    """Raised when entity is not found."""

    pass


class DuplicateEntity(RepositoryException):
    """Raised when duplicate entity creation is attempted."""

    pass


class RepositoryError(RepositoryException):
    """Generic repository operation error."""

    pass


class BaseRepository(ABC, Generic[T]):
    """
    Abstract base repository implementing async CRUD operations.

    Generic[T] allows type-safe operations on any model type.
    All concrete repositories inherit from this to provide consistent interface.

    Features:
        - Type-safe CRUD operations (Create, Read, Update, Delete)
        - Pagination support (limit, offset)
        - Filtering with dynamic WHERE clauses
        - Count operations
        - Batch operations (future)
        - Transaction support via AsyncSession
        - Custom error handling

    Attributes:
        session: SQLAlchemy AsyncSession for database operations
        model: SQLAlchemy ORM model class

    Example:
        >>> class CompanyRepository(BaseRepository[Company]):
        ...     model = Company
        ...
        ...     def __init__(self, session: AsyncSession):
        ...         super().__init__(session)
        >>>
        >>> async with engine.get_session() as session:
        ...     repo = CompanyRepository(session)
        ...     company = await repo.get_by_id(1)
        ...     companies = await repo.list_all()
    """

    # Must be set in concrete class
    model: type[T]

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize repository with async session.

        Args:
            session: SQLAlchemy AsyncSession for database operations

        Raises:
            ValueError: If session is None or not AsyncSession type

        Example:
            >>> async with engine.get_session() as session:
            ...     repo = CompanyRepository(session)
        """
        if session is None:
            raise ValueError("AsyncSession cannot be None")

        self.session: AsyncSession = session

        if self.model is None:
            raise NotImplementedError(
                f"{self.__class__.__name__} must define 'model' class attribute"
            )

        logger.debug(
            f"Initialized {self.__class__.__name__} for model {self.model.__name__}"
        )

    # ===== CRUD Operations =====

    async def create(self, obj_in: T | dict) -> T:
        """
        Create and persist a new entity.

        Args:
            obj_in: Model instance or dictionary with field values

        Returns:
            Created model instance with auto-generated id

        Raises:
            DuplicateEntity: If unique constraint violation occurs
            RepositoryError: On database operation failure

        Example:
            >>> company_data = {"company_name": "Samsung", "corp_code": "005930"}
            >>> company = await repo.create(company_data)
            >>> print(company.id)  # Auto-generated
            1
        """
        try:
            if isinstance(obj_in, dict):
                db_obj = self.model.from_dict(obj_in)
            else:
                db_obj = obj_in

            self.session.add(db_obj)
            await self.session.flush()  # Flush to get auto-generated id

            logger.debug(f"Created {self.model.__name__} with id {db_obj.id}")
            return db_obj

        except IntegrityError as e:
            await self.session.rollback()
            if "unique" in str(e).lower():
                logger.error(f"Duplicate entity: {e}")
                raise DuplicateEntity(f"Entity already exists: {e}") from e
            raise RepositoryError(f"Database integrity error: {e}") from e
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating {self.model.__name__}: {e}")
            raise RepositoryError(f"Failed to create entity: {e}") from e

    async def get_by_id(self, id: Any) -> T | None:
        """
        Retrieve entity by primary key.

        Args:
            id: Primary key value

        Returns:
            Model instance or None if not found

        Raises:
            RepositoryError: On database operation failure

        Example:
            >>> company = await repo.get_by_id(1)
            >>> if company:
            ...     print(company.company_name)
        """
        try:
            obj = await self.session.get(self.model, id)
            logger.debug(f"Retrieved {self.model.__name__} with id {id}")
            return obj
        except Exception as e:
            logger.error(f"Error retrieving {self.model.__name__} by id {id}: {e}")
            raise RepositoryError(f"Failed to retrieve entity: {e}") from e

    async def get_by_filter(
        self, filter_dict: dict[str, Any], first: bool = False
    ) -> T | None | list[T]:
        """
        Retrieve entities matching filter criteria.

        Builds dynamic WHERE clause from filter dictionary.

        Args:
            filter_dict: Dictionary of {column_name: value} pairs
            first: Return first result only (vs all matches)

        Returns:
            Single model instance if first=True
            List of model instances if first=False
            None if no matches found

        Raises:
            RepositoryError: On database operation failure

        Example:
            >>> # Get all companies with specific industry
            >>> companies = await repo.get_by_filter(
            ...     {"industry": "Semiconductor", "active": True}
            ... )
            >>>
            >>> # Get first match
            >>> company = await repo.get_by_filter(
            ...     {"corp_code": "005930"},
            ...     first=True
            ... )
        """
        try:
            conditions = [
                getattr(self.model, k) == v
                for k, v in filter_dict.items()
                if hasattr(self.model, k)
            ]

            stmt = select(self.model)
            if conditions:
                stmt = stmt.where(and_(*conditions))

            result = await self.session.execute(stmt)

            if first:
                obj = result.scalar_one_or_none()
                logger.debug(
                    f"Retrieved single {self.model.__name__} by filter: {filter_dict}"
                )
                return obj
            else:
                objs = result.scalars().all()
                logger.debug(
                    f"Retrieved {len(objs)} {self.model.__name__} entities by filter"
                )
                return objs

        except Exception as e:
            logger.error(f"Error filtering {self.model.__name__}: {e}")
            raise RepositoryError(f"Failed to filter entities: {e}") from e

    async def update(self, id: Any, obj_in: dict | T) -> T:
        """
        Update an existing entity.

        Args:
            id: Primary key of entity to update
            obj_in: Dictionary of fields to update or model instance

        Returns:
            Updated model instance

        Raises:
            EntityNotFound: If entity with id not found
            RepositoryError: On database operation failure

        Example:
            >>> company = await repo.update(1, {"industry": "Tech"})
            >>> # Or with model instance
            >>> company.industry = "Technology"
            >>> updated = await repo.update(1, company)
        """
        try:
            db_obj = await self.session.get(self.model, id)
            if db_obj is None:
                raise EntityNotFound(f"{self.model.__name__} with id {id} not found")

            if isinstance(obj_in, dict):
                for key, value in obj_in.items():
                    if hasattr(db_obj, key):
                        setattr(db_obj, key, value)
            else:
                for column in self.model.__table__.columns:
                    if hasattr(obj_in, column.name):
                        setattr(db_obj, column.name, getattr(obj_in, column.name))

            await self.session.flush()
            logger.debug(f"Updated {self.model.__name__} with id {id}")
            return db_obj

        except EntityNotFound:
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating {self.model.__name__} with id {id}: {e}")
            raise RepositoryError(f"Failed to update entity: {e}") from e

    async def delete(self, id: Any) -> bool:
        """
        Delete an entity by primary key.

        Hard delete (permanent removal). For soft deletes, use update() to set
        is_deleted=True or deleted_at timestamp.

        Args:
            id: Primary key of entity to delete

        Returns:
            True if entity was deleted, False if not found

        Raises:
            RepositoryError: On database operation failure

        Example:
            >>> deleted = await repo.delete(1)
            >>> if deleted:
            ...     print("Company deleted")
            >>> else:
            ...     print("Company not found")
        """
        try:
            db_obj = await self.session.get(self.model, id)
            if db_obj is None:
                logger.debug(
                    f"{self.model.__name__} with id {id} not found for deletion"
                )
                return False

            await self.session.delete(db_obj)
            await self.session.flush()
            logger.debug(f"Deleted {self.model.__name__} with id {id}")
            return True

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error deleting {self.model.__name__} with id {id}: {e}")
            raise RepositoryError(f"Failed to delete entity: {e}") from e

    # ===== Query Operations =====

    async def list_all(
        self,
        limit: int | None = None,
        offset: int = 0,
        order_by: str | None = None,
        ascending: bool = True,
    ) -> list[T]:
        """
        Retrieve all entities with optional pagination and sorting.

        Args:
            limit: Maximum number of results (None = unlimited)
            offset: Number of results to skip (for pagination)
            order_by: Column name to sort by
            ascending: Sort direction (True = ASC, False = DESC)

        Returns:
            List of model instances

        Raises:
            RepositoryError: On database operation failure

        Example:
            >>> # Get first 10 companies
            >>> companies = await repo.list_all(limit=10, offset=0)
            >>>
            >>> # Get all companies sorted by name
            >>> companies = await repo.list_all(order_by="company_name")
            >>>
            >>> # Get active companies, sorted by creation date (newest first)
            >>> active = await repo.list_all(
            ...     order_by="created_at",
            ...     ascending=False
            ... )
        """
        try:
            stmt = select(self.model)

            # Add ordering if specified
            if order_by and hasattr(self.model, order_by):
                order_col = getattr(self.model, order_by)
                if ascending:
                    stmt = stmt.order_by(order_col.asc())
                else:
                    stmt = stmt.order_by(order_col.desc())

            # Add pagination
            if limit:
                stmt = stmt.limit(limit)
            stmt = stmt.offset(offset)

            result = await self.session.execute(stmt)
            objs = result.scalars().all()
            logger.debug(
                f"Retrieved {len(objs)} {self.model.__name__} entities "
                f"(limit={limit}, offset={offset})"
            )
            return objs

        except Exception as e:
            logger.error(f"Error listing {self.model.__name__}: {e}")
            raise RepositoryError(f"Failed to list entities: {e}") from e

    async def count(self, filter_dict: dict[str, Any] | None = None) -> int:
        """
        Count entities matching optional filter criteria.

        Args:
            filter_dict: Optional dictionary of filter conditions

        Returns:
            Number of matching entities

        Raises:
            RepositoryError: On database operation failure

        Example:
            >>> total = await repo.count()
            >>> active_count = await repo.count({"active": True})
        """
        try:
            stmt = select(func.count(self.model.id))

            if filter_dict:
                conditions = [
                    getattr(self.model, k) == v
                    for k, v in filter_dict.items()
                    if hasattr(self.model, k)
                ]
                if conditions:
                    stmt = stmt.where(and_(*conditions))

            result = await self.session.execute(stmt)
            count = result.scalar()
            logger.debug(f"Counted {count} {self.model.__name__} entities")
            return count

        except Exception as e:
            logger.error(f"Error counting {self.model.__name__}: {e}")
            raise RepositoryError(f"Failed to count entities: {e}") from e

    async def exists(self, filter_dict: dict[str, Any]) -> bool:
        """
        Check if entity matching filter exists.

        Args:
            filter_dict: Dictionary of filter conditions

        Returns:
            True if at least one matching entity exists

        Example:
            >>> exists = await repo.exists({"company_name": "Samsung"})
        """
        try:
            count = await self.count(filter_dict)
            return count > 0
        except Exception as e:
            logger.error(f"Error checking existence: {e}")
            raise RepositoryError(f"Failed to check entity existence: {e}") from e


__all__ = [
    "BaseRepository",
    "RepositoryException",
    "EntityNotFound",
    "DuplicateEntity",
    "RepositoryError",
]

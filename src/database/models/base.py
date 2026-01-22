"""
SQLAlchemy Base Configuration and Mixins

Refactored:
- Fixed Pylance type errors using explicit casting to `Mapper`.
- Fixed `__table__` access errors using `sqlalchemy.inspect`.

Declarative Registry:
    - Base: SQLAlchemy declarative base for all models
    - Provides __tablename__ auto-generation
    - Supports custom type annotations

Mixins:
    - TimestampMixin: Automatic created_at, updated_at timestamps
    - AuditMixin: Track creation/update by user (future enhancement)
    - ModelMixin: Common methods (to_dict, from_dict)

Author: Enterprise Architecture Team
Created: 2026-01-21
Version: 1.0.2 (Fix Pylance types)
"""

from datetime import datetime
from typing import Any, TypeVar, cast

from sqlalchemy import DateTime, func, inspect
from sqlalchemy.orm import DeclarativeBase, Mapper, mapped_column

T = TypeVar("T", bound="ModelMixin")


class Base(DeclarativeBase):
    """
    SQLAlchemy Declarative Base for all ORM models.

    Modern SQLAlchemy 2.0 pattern using DeclarativeBase.
    All models inherit from this base to register with the registry.

    Features:
        - Automatic table name generation (snake_case from class name)
        - Type-annotated columns with IDE support
        - Integration with migration tools (Alembic)
    """

    type_annotation_map = {}


class TimestampMixin:
    """
    Mixin for automatic timestamp management.

    Adds created_at and updated_at columns with automatic server-side
    timestamp generation and update tracking.
    """

    created_at = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    """UTC timestamp when record was created (server-side)"""

    updated_at = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False
    )
    """UTC timestamp when record was last modified"""


class ModelMixin:
    """
    Mixin providing common model utility methods.

    Methods:
        - to_dict(): Convert model instance to dictionary
        - to_dict_exclude(): Convert with field exclusions
        - from_dict(): Create/update from dictionary
        - get_columns(): Get all mapped column names
    """

    def to_dict(self, exclude: set[str] | None = None) -> dict[str, Any]:
        """
        Convert model instance to dictionary representation.
        """
        exclude = exclude or set()
        result = {}

        mapper = cast(Mapper, inspect(self.__class__))

        for column in mapper.columns:
            col_name = column.key
            if col_name not in exclude:
                value = getattr(self, col_name, None)
                # Handle datetime serialization
                if isinstance(value, datetime):
                    result[col_name] = value.isoformat()
                else:
                    result[col_name] = value

        return result

    def to_dict_exclude(self, *exclude_fields: str) -> dict[str, Any]:
        """Convenience method to convert to dict with excluded fields."""
        return self.to_dict(exclude=set(exclude_fields))

    @classmethod
    def from_dict(cls: type[T], data: dict[str, Any]) -> T:
        """
        Create model instance from dictionary.
        Only sets mapped column values, ignores unknown keys.
        """
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data)}")

        mapper = cast(Mapper, inspect(cls))
        valid_columns = {col.key for col in mapper.columns}

        # Filter data to only include valid columns
        filtered_data = {k: v for k, v in data.items() if k in valid_columns}

        return cls(**filtered_data)

    @classmethod
    def get_columns(cls) -> list[str]:
        """Get all mapped column names for this model."""

        mapper = cast(Mapper, inspect(cls))
        return [col.key for col in mapper.columns]


class AuditMixin:
    """Mixin for audit trail tracking (future enhancement)."""

    pass


class SoftDeleteMixin:
    """Mixin for soft delete support (future enhancement)."""

    pass


# Re-export for convenience
__all__ = [
    "Base",
    "TimestampMixin",
    "ModelMixin",
    "AuditMixin",
    "SoftDeleteMixin",
]

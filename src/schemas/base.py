"""
Base Schemas - Common request/response patterns

Provides reusable schemas for pagination, error handling, and common patterns
used across all API endpoints.

Author: Enterprise Architecture Team
Created: 2026-01-21
Version: 1.0.0
"""

from datetime import UTC, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PagedResponse(BaseModel, Generic[T]):
    """
    Generic paginated response wrapper.

    Used for all list endpoints that support pagination.

    Example:
        ```json
        {
            "total": 150,
            "page": 1,
            "limit": 10,
            "offset": 0,
            "data": [...]
        }
        ```
    """

    total: int = Field(..., description="Total number of items in database")
    page: int = Field(..., ge=1, description="Current page number (1-indexed)")
    limit: int = Field(..., ge=1, le=100, description="Items per page")
    offset: int = Field(..., ge=0, description="Number of items skipped")
    data: list[T] = Field(default_factory=list, description="Page data items")

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        return (self.total + self.limit - 1) // self.limit

    class Config:
        json_schema_extra = {
            "example": {
                "total": 150,
                "page": 1,
                "limit": 10,
                "offset": 0,
                "data": [
                    {"id": 1, "name": "Company 1"},
                    {"id": 2, "name": "Company 2"},
                ],
            }
        }


class ErrorResponse(BaseModel):
    """
    Standard error response format.

    Used for all API error responses.

    Example:
        ```json
        {
            "error": "Validation Error",
            "message": "Invalid company name",
            "status_code": 400,
            "timestamp": "2026-01-21T10:30:00Z"
        }
        ```
    """

    error: str = Field(..., description="Error type/category")
    message: str = Field(..., description="Human-readable error message")
    status_code: int = Field(..., ge=400, le=599, description="HTTP status code")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Error occurrence time"
    )
    details: dict | None = Field(None, description="Additional error context")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "EntityNotFound",
                "message": "Company with id 999 not found",
                "status_code": 404,
                "timestamp": "2026-01-21T10:30:00Z",
            }
        }


__all__ = ["PagedResponse", "ErrorResponse"]

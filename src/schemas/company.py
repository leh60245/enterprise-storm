"""
Company Schemas - Request/Response Models for Company API

Pydantic models for validating company-related API requests and responses.

Refactored:
- Removed 'active' field to sync with Phase 3 DB schema changes.
- Removed 'description' field as requested.
- Updated examples to reflect current schema.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CompanyCreate(BaseModel):
    """
    Request schema for creating a new company.

    POST /api/companies
    """

    company_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Official company name (required)",
    )

    corp_code: str | None = Field(
        None, max_length=20, description="6-digit DART corporation code"
    )

    stock_code: str | None = Field(
        None, max_length=20, description="6-digit Korea Exchange stock code"
    )

    industry: str | None = Field(
        None, max_length=100, description="Industry classification"
    )

    @field_validator("company_name")
    @classmethod
    def validate_company_name(cls, v: str) -> str:
        """Ensure company name is not empty after strip."""
        v = v.strip()
        if not v:
            raise ValueError("Company name cannot be empty")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "company_name": "삼성전자",
                "corp_code": "005930",
                "stock_code": "005930",
                "industry": "Semiconductor",
            }
        }


class CompanyUpdate(BaseModel):
    """
    Request schema for updating a company.

    PATCH /api/companies/{id}
    """

    company_name: str | None = Field(
        None, min_length=1, max_length=255, description="Official company name"
    )

    corp_code: str | None = Field(
        None, max_length=20, description="DART corporation code"
    )

    stock_code: str | None = Field(
        None, max_length=20, description="Korea Exchange stock code"
    )

    industry: str | None = Field(
        None, max_length=100, description="Industry classification"
    )

    class Config:
        json_schema_extra = {"example": {"industry": "Electronics"}}


class CompanyResponse(BaseModel):
    """
    Response schema for company API endpoints.
    """

    id: int = Field(..., description="Unique company ID")

    company_name: str = Field(..., description="Official company name")

    corp_code: str | None = Field(None, description="DART corporation code")

    stock_code: str | None = Field(None, description="Korea Exchange stock code")

    industry: str | None = Field(None, description="Industry classification")

    created_at: datetime = Field(..., description="Creation timestamp")
    """UTC timestamp of record creation"""

    updated_at: datetime = Field(..., description="Last update timestamp")
    """UTC timestamp of last modification"""

    class Config:
        from_attributes = True  # Pydantic V2: Allow ORM mode for SQLAlchemy models
        json_encoders = {datetime: lambda v: v.isoformat() if v else None}
        json_schema_extra = {
            "example": {
                "id": 1,
                "company_name": "삼성전자",
                "corp_code": "005930",
                "stock_code": "005930",
                "industry": "Semiconductor",
                "created_at": "2026-01-15T08:30:00+00:00",
                "updated_at": "2026-01-21T10:45:30+00:00",
            }
        }


__all__ = [
    "CompanyCreate",
    "CompanyUpdate",
    "CompanyResponse",
]
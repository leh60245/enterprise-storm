"""
Source Material Pydantic Schemas

API request/response validation schemas for SourceMaterial model.

Author: Enterprise Architecture Team
Created: 2026-01-21
Version: 1.0.0
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SourceMaterialBase(BaseModel):
    """Base schema for SourceMaterial (shared fields)"""

    chunk_type: str = Field(default="text", max_length=20, description="Chunk type")
    section_path: str = Field(..., description="Hierarchical section reference")
    sequence_order: int = Field(..., description="Position in document")
    raw_content: str = Field(..., description="Actual text content")
    table_metadata: dict[str, Any] | None = Field(
        None, description="Table-specific info"
    )
    meta_info: dict[str, Any] | None = Field(None, description="Additional metadata")


class SourceMaterialCreate(SourceMaterialBase):
    """Schema for creating a new SourceMaterial (POST request)"""

    report_id: int = Field(..., description="Foreign key to Analysis_Reports")
    embedding: list[float] | None = Field(None, description="Vector embedding")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "report_id": 1,
                "chunk_type": "text",
                "section_path": "1.1.2",
                "sequence_order": 10,
                "raw_content": "삼성전자는 반도체, 디스플레이, IT & 모바일 사업을 영위하고 있습니다.",
                "embedding": [0.1, 0.2, 0.3],  # Truncated for example
                "meta_info": {"language": "ko", "confidence": 0.95},
            }
        }
    )


class SourceMaterialUpdate(BaseModel):
    """Schema for updating a SourceMaterial (PATCH request)"""

    chunk_type: str | None = Field(None, max_length=20)
    raw_content: str | None = None
    embedding: list[float] | None = None
    table_metadata: dict[str, Any] | None = None
    meta_info: dict[str, Any] | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "embedding": [0.1, 0.2, 0.3]  # Update embedding only
            }
        }
    )


class SourceMaterialResponse(SourceMaterialBase):
    """Schema for SourceMaterial response (GET response)"""

    id: int
    report_id: int
    embedding: list[float] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "report_id": 1,
                "chunk_type": "text",
                "section_path": "1.1.2",
                "sequence_order": 10,
                "raw_content": "삼성전자는 반도체, 디스플레이, IT & 모바일 사업을 영위하고 있습니다.",
                "embedding": None,  # Large array, omitted for brevity
                "table_metadata": None,
                "meta_info": {"language": "ko", "confidence": 0.95},
                "created_at": "2024-01-15T10:30:00",
                "updated_at": "2024-01-15T12:00:00",
            }
        },
    )


class SourceMaterialListItem(BaseModel):
    """Schema for SourceMaterial list item (compact view, no embedding)"""

    id: int
    report_id: int
    chunk_type: str
    section_path: str
    sequence_order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VectorSearchRequest(BaseModel):
    """Schema for vector similarity search request"""

    query_embedding: list[float] = Field(..., description="Query vector")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results")
    report_id: int | None = Field(None, description="Filter by report ID")
    chunk_type: str | None = Field(None, description="Filter by chunk type")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query_embedding": [0.1, 0.2, 0.3],  # Truncated
                "top_k": 10,
                "report_id": 1,
                "chunk_type": "text",
            }
        }
    )


class VectorSearchResult(BaseModel):
    """Schema for vector search result item"""

    id: int
    report_id: int
    section_path: str
    raw_content: str
    distance: float = Field(..., description="L2 distance (lower is better)")

    model_config = ConfigDict(from_attributes=True)

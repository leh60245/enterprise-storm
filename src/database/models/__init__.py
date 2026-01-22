"""
Database Models Package

Container for all SQLAlchemy ORM model definitions.
Each model represents a table in the PostgreSQL database.

Models:
    - Company: Companies tracked in DART database
    - AnalysisReport: Financial reports from DART API
    - SourceMaterial: Chunked report content for embeddings
    - GeneratedReport: AI-generated analysis reports
    - Resume: Interview prep resumes (Phase 2)
    - InterviewQuestion: Interview question database (Phase 2)

Import Pattern:
    >>> from src.database.models import Company, AnalysisReport
    >>> # Use models with repositories
    >>> repo = CompanyRepository(session)

Author: Enterprise Architecture Team
Created: 2026-01-21
Version: 1.0.0
"""

from .analysis_report import AnalysisReport
from .base import AuditMixin, Base, ModelMixin, SoftDeleteMixin, TimestampMixin
from .company import Company
from .generated_report import GeneratedReport
from .source_material import SourceMaterial

__all__ = [
    "Base",
    "TimestampMixin",
    "ModelMixin",
    "AuditMixin",
    "SoftDeleteMixin",
    "Company",
    "AnalysisReport",
    "SourceMaterial",
    "GeneratedReport",
]

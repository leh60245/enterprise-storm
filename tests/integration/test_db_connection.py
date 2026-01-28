"""
Integration Tests: Database Connection (Fixed)

Tests basic database connectivity, table existence, and schema mapping.

Refactored:
- Removed 'active' field usage (Column deleted from DB).
- Used UUID for company names to prevent duplicate errors.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncDatabaseEngine
from src.database.models import Company


@pytest.mark.asyncio
@pytest.mark.integration
class TestDatabaseConnection:
    """Test suite for database connectivity and basic operations."""

    async def test_engine_initialization(self, db_engine: AsyncDatabaseEngine):
        """Test that database engine initializes correctly."""
        assert db_engine is not None, "Database engine should be initialized"
        assert db_engine._initialized is True, "Engine should be marked as initialized"
        assert db_engine.engine is not None, "SQLAlchemy engine should exist"
        assert db_engine.session_factory is not None, "Session factory should exist"

    async def test_database_health_check(self, db_session: AsyncSession):
        """Test basic database connectivity with a simple query."""
        result = await db_session.execute(text("SELECT 1 as health_check"))
        row = result.fetchone()

        assert row is not None, "Health check query should return a result"
        assert row[0] == 1, "Health check should return 1"

    async def test_table_existence(self, db_session: AsyncSession):
        """Test that all expected tables exist in the database."""
        result = await db_session.execute(
            text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        )

        existing_tables = {row[0] for row in result.fetchall()}

        expected_tables = {
            "Companies",
            "Analysis_Reports",
            "Generated_Reports",
            "Source_Materials",
        }

        for table_name in expected_tables:
            assert table_name in existing_tables, (
                f"Table '{table_name}' not found. Available: {sorted(existing_tables)}"
            )

    async def test_company_table_schema(self, db_session: AsyncSession):
        """Test that the Companies table has the expected columns."""
        result = await db_session.execute(
            text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'Companies'
            ORDER BY ordinal_position
        """)
        )

        columns = {
            row[0]: {"type": row[1], "nullable": row[2]} for row in result.fetchall()
        }

        required_columns = ["id", "company_name", "corp_code"]
        for col in required_columns:
            assert col in columns, (
                f"Required column '{col}' missing from Companies table"
            )

        assert columns["id"]["nullable"] == "NO", "Primary key 'id' should be NOT NULL"

    async def test_basic_select_query(self, db_session: AsyncSession):
        """Test that we can query the Companies table using SQLAlchemy ORM."""
        from sqlalchemy import select

        result = await db_session.execute(select(Company).limit(5))
        companies = result.scalars().all()

        assert isinstance(companies, list), "Query should return a list"

        if companies:
            first_company = companies[0]
            assert hasattr(first_company, "id")
            assert hasattr(first_company, "company_name")

    async def test_session_commit_rollback(self, db_session: AsyncSession):
        """
        Test that session transactions work correctly.
        """
        from src.database.repositories import CompanyRepository

        repo = CompanyRepository(db_session)

        # [Fix] Use UUID and remove 'active' field
        unique_name = f"Tx_Test_{uuid.uuid4().hex[:8]}"
        test_data = {
            "company_name": unique_name,
            "corp_code": "999999",
            # "active": True  <-- Removed
        }

        # Insert company
        company = await repo.create(test_data)
        assert company.id is not None

        # Verify it exists in session
        result = await repo.get_by_name(unique_name)
        assert result is not None

        # Cleanup handled by fixture rollback

    async def test_connection_error_handling(self, db_session: AsyncSession):
        """Test that invalid queries raise appropriate exceptions."""
        with pytest.raises(Exception) as exc_info:
            await db_session.execute(text("SELECT * FROM NonExistentTable"))

        assert exc_info.value is not None

    async def test_concurrent_sessions(self, db_engine: AsyncDatabaseEngine):
        """Test that multiple concurrent sessions work correctly."""
        from sqlalchemy import select

        async with db_engine.get_session() as session1, db_engine.get_session() as session2:
            result1 = await session1.execute(select(Company).limit(1))
            result2 = await session2.execute(select(Company).limit(1))

            assert result1 is not None
            assert result2 is not None

    async def test_database_version(self, db_session: AsyncSession):
        """Test that we're connected to the correct PostgreSQL version."""
        result = await db_session.execute(text("SELECT version()"))
        version_string = result.scalar()

        assert "PostgreSQL" in version_string
        print(f"\nDatabase version: {version_string}")

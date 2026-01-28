"""
Pytest Configuration and Shared Fixtures

Refactored:
- Added UUID to test_company_data to prevent 'DuplicateEntity' errors.
- Ensures each test run creates a unique company name.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncDatabaseEngine
from src.database.models import Company

# Configure logging for tests
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ===== Pytest Configuration =====

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test (requires database)"
    )
    config.addinivalue_line(
        "markers",
        "unit: mark test as unit test (no external dependencies)"
    )


# ===== Event Loop Fixture =====

@pytest.fixture(scope="function")
def event_loop():
    """Create a FUNCTION-SCOPED event loop for each async test."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    try:
        loop.close()
    except Exception:
        pass


# ===== Database Engine Fixture =====

@pytest.fixture(scope="function")
async def db_engine():
    """Create a FUNCTION-SCOPED database engine with singleton reset."""
    AsyncDatabaseEngine._instance = None

    logger.info("Initializing test database engine (singleton reset)...")
    engine = AsyncDatabaseEngine()
    await engine.initialize(echo=False)

    yield engine

    logger.info("Disposing test database engine...")
    await engine.dispose()
    AsyncDatabaseEngine._instance = None


# ===== Database Session Fixture =====

@pytest.fixture
async def db_session(db_engine: AsyncDatabaseEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create a function-scoped database session with automatic rollback."""
    async with db_engine.get_session() as session:
        yield session
        await session.rollback()


# ===== Test Data Fixtures (FIXED) =====

@pytest.fixture
def test_company_data() -> dict:
    """
    Provide sample company data with UNIQUE name.
    
    Prevents 'DuplicateEntity' errors during repeated tests.
    """
    # [FIX] Generate random suffix
    unique_id = uuid.uuid4().hex[:8]
    return {
        "company_name": f"테스트_삼성전자_{unique_id}",
        "corp_code": "005930",
        "stock_code": "005930",
        "industry": "Semiconductor",
    }


@pytest.fixture
async def test_company(db_session: AsyncSession, test_company_data: dict) -> Company:
    """Create a test company in the database."""
    from src.database.repositories import CompanyRepository

    repo = CompanyRepository(db_session)

    # Check if company already exists (should happen rarely with UUID)
    existing = await repo.get_by_name(test_company_data["company_name"])
    if existing:
        return existing

    company = await repo.create(test_company_data)
    await db_session.commit()

    return company


# ===== Utility Fixtures =====

@pytest.fixture
def cleanup_test_data():
    """Fixture for manual data cleanup if needed."""
    async def _cleanup(session: AsyncSession, model, **filters):
        from sqlalchemy import delete
        stmt = delete(model).where(
            *[getattr(model, k).like(v) if "%" in str(v) or "*" in str(v)
              else getattr(model, k) == v
              for k, v in filters.items()]
        )
        await session.execute(stmt)
        await session.commit()

    return _cleanup

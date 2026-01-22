"""
Async Database Connection Management (SQLAlchemy 2.0+ with asyncpg)

Refactored for Phase 3.5:
- Robust Singleton Lifecycle: dispose() now correctly resets the singleton instance.
- centralized Configuration: Pool settings are loaded from DB_CONFIG if available.
- Type Safety: Improved type hinting and SQLAlchemy 2.0 compliance.

Usage:
    engine = AsyncDatabaseEngine()
    await engine.initialize()
    async with engine.get_session() as session:
        ...
    await engine.dispose()
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# QueuePool is the default for create_engine, but explicit import is good for clarity
from src.common.config import DB_CONFIG

logger = logging.getLogger(__name__)


class AsyncDatabaseEngine:
    """
    Async Database Engine Manager (Singleton Pattern)

    Features:
        - Connection pooling with configurable limits
        - Automatic singleton reset on disposal (Crucial for tests)
        - Context manager for session handling
    """

    _instance: Optional["AsyncDatabaseEngine"] = None
    _initialized: bool = False

    def __new__(cls) -> "AsyncDatabaseEngine":
        """Implement singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize attributes (idempotent)."""
        if self._initialized:
            return

        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker | None = None
        self._initialized = True

    async def initialize(
        self, db_config: dict[str, Any] | None = None, echo: bool = False, **kwargs
    ) -> None:
        """
        Initialize the async engine with connection pooling.

        Args:
            db_config: Database configuration. Defaults to src.common.config.DB_CONFIG.
            echo: Enable SQL query logging.
            **kwargs: Override pool settings (pool_size, max_overflow, etc.)
        """
        if self.engine is not None:
            logger.warning("Engine already initialized, skipping re-initialization")
            return

        # 1. Configuration Merging
        config = db_config or DB_CONFIG

        # Validate required keys
        required_keys = {"host", "port", "user", "password", "database"}
        if not required_keys.issubset(config.keys()):
            missing = required_keys - set(config.keys())
            raise ValueError(f"Missing DB config keys: {missing}")

        # 2. Connection Pool Settings
        # Priority: kwargs > DB_CONFIG > Defaults
        pool_size = kwargs.get("pool_size", config.get("pool_size", 20))
        max_overflow = kwargs.get("max_overflow", config.get("max_overflow", 10))
        pool_timeout = kwargs.get("pool_timeout", config.get("pool_timeout", 30))
        pool_recycle = kwargs.get("pool_recycle", config.get("pool_recycle", 3600))

        # 3. Build URL
        url = (
            f"postgresql+asyncpg://"
            f"{config['user']}:{config['password']}"
            f"@{config['host']}:{config['port']}"
            f"/{config['database']}"
        )

        logger.info(
            f"Initializing AsyncEngine: {config['host']}:{config['port']}/{config['database']}"
        )
        logger.info(
            f"Pool Config: size={pool_size}, overflow={max_overflow}, recycle={pool_recycle}"
        )

        try:
            self.engine = create_async_engine(
                url,
                echo=echo,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=pool_timeout,
                pool_recycle=pool_recycle,
                pool_pre_ping=True,  # Check connection liveness before checkout
                connect_args={
                    "server_settings": {
                        "application_name": "enterprise-storm",
                        "jit": "off",  # Optimize for OLTP
                    },
                    "command_timeout": 60,
                },
            )

            self.session_factory = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
                autocommit=False,
            )

            # Verify connection
            await self.health_check()
            logger.info("✅ AsyncEngine initialized successfully")

        except Exception as e:
            logger.error(f"❌ Failed to initialize AsyncEngine: {e}")
            # Ensure cleanup on failure
            await self.dispose()
            raise RuntimeError(f"Database initialization failed: {e}") from e

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Transactional Session Context Manager.

        Usage:
            async with engine.get_session() as session:
                await session.execute(...)
                # Auto-commit on exit
        """
        if self.session_factory is None:
            raise RuntimeError(
                "Engine not initialized. Call await engine.initialize() first."
            )

        session: AsyncSession = self.session_factory()

        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Session transaction rolled back: {e}")
            raise
        finally:
            await session.close()

    async def health_check(self) -> bool:
        """Verify database connectivity."""
        if self.engine is None:
            raise RuntimeError("Engine not initialized")

        try:
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise

    async def dispose(self) -> None:
        """
        Dispose the engine and RESET the singleton instance.

        This is critical for testing environments to ensure isolation.
        """
        if self.engine:
            logger.info("Disposing AsyncEngine...")
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None

        # CRITICAL: Reset singleton state
        AsyncDatabaseEngine._instance = None
        self._initialized = False
        logger.debug("AsyncDatabaseEngine singleton reset")


# Global Accessor (Optional, but useful)
async def get_db_engine() -> AsyncDatabaseEngine:
    return AsyncDatabaseEngine()


if __name__ == "__main__":
    import asyncio

    async def main():
        engine = AsyncDatabaseEngine()
        try:
            await engine.initialize(echo=True)
            async with engine.get_session() as session:
                result = await session.execute(text("SELECT 1"))
                print(f"✅ Connection Test: {result.scalar()}")
        finally:
            await engine.dispose()

    asyncio.run(main())

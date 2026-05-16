"""Async database engine og session factory."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pss.config import settings
from pss.db.models import Base

_connect_args: dict[str, object] = {"ssl": settings.asyncpg_ssl}

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-style dependency; kan også bruges manuelt."""
    async with AsyncSessionLocal() as session:
        yield session


__all__ = ["AsyncSessionLocal", "Base", "engine", "get_async_session"]

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

def _asyncpg_connect_args(database_url: str) -> dict[str, object]:
    """asyncpg bruger ssl=True/False — ikke sslmode i URL."""
    if "localhost" in database_url or "127.0.0.1" in database_url:
        return {"ssl": False}
    return {"ssl": True}


_connect_args = _asyncpg_connect_args(settings.database_url)

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

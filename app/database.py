"""Database engine, session factory, and the FastAPI session dependency."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

settings = get_settings()

# A single engine is created per process. It owns the connection pool, so it
# must never be created per-request.
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.echo_sql,
    # Validates a pooled connection before handing it out, which avoids
    # "server closed the connection unexpectedly" errors after an idle period.
    pool_pre_ping=True,
)

SessionFactory = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,  # keep attributes readable after commit()
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session scoped to a single request.

    The session is always closed when the request finishes, and rolled back if
    the handler raised before committing.
    """
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

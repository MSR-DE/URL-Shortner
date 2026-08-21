"""Shared pytest fixtures.

The suite runs against a real PostgreSQL database rather than SQLite, so that
what is tested is what actually ships: the UNIQUE constraint, the server-side
`now()` defaults, and the atomic `visit_count = visit_count + 1` update all
behave differently (or not at all) on other engines.
"""

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_session
from app.main import app
from app.models import Base

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/urlshortener_test",
)


@pytest.fixture
async def engine() -> AsyncIterator:
    """A test-scoped engine with a freshly created schema."""
    test_engine = create_async_engine(TEST_DATABASE_URL)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    """A session for tests that want to inspect the database directly."""
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as db_session:
        yield db_session


@pytest.fixture
async def client(engine) -> AsyncIterator[AsyncClient]:
    """An HTTP client wired to the app, with the test database injected.

    `follow_redirects=False` keeps the 307 visible so redirect behaviour can be
    asserted instead of silently followed to an external site.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with factory() as db_session:
            yield db_session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver", follow_redirects=False
    ) as http_client:
        yield http_client
    app.dependency_overrides.clear()

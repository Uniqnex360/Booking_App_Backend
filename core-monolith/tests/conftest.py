"""
Global pytest fixtures for core-monolith (Postgres async driver).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
    AsyncEngine,
)

from dotenv import load_dotenv
load_dotenv()

from app.core.database import Base

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://booking_user:booking_pass123@localhost:5433/core_db_test",
)


async def _drop_all_cascade(engine):
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f'DROP TABLE IF EXISTS "{table.name}" CASCADE'))
        result = await conn.execute(
            text(
                "SELECT typname FROM pg_type t "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = 'public' AND t.typtype = 'e'"
            )
        )
        for row in result:
            await conn.execute(text(f'DROP TYPE IF EXISTS "{row[0]}" CASCADE'))
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


async def _create_all(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest_asyncio.fixture(scope="function")
async def engine():
    """Shared engine for all tests in a function."""
    eng = create_async_engine(TEST_DB_URL, echo=False, pool_size=20, max_overflow=0)
    await _drop_all_cascade(eng)
    await _create_all(eng)
    yield eng
    await _drop_all_cascade(eng)
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    """Single session for non-concurrent tests."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess

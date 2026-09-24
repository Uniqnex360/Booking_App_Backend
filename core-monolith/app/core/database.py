from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator
from app.core.config import settings
DATABASE_URL = str(settings.DATABASE_URL).replace(
    "postgresql://", "postgresql+asyncpg://"
)
_needs_ssl = "sslmode=require" in DATABASE_URL
for _suffix in ("?sslmode=require", "&sslmode=require",
                "?sslmode=prefer",  "&sslmode=prefer"):
    DATABASE_URL = DATABASE_URL.replace(_suffix, "")

_connect_args = {"ssl": True} if _needs_ssl else {}

engine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args=_connect_args,
    echo=False,
)
AsyncSessionLocal=async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False, 
    autocommit=False,
    autoflush=False
)
Base=declarative_base()
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
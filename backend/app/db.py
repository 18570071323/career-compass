"""数据库引擎与会话（SQLAlchemy 2.0 async）。

本地联调可用 SQLite（DATABASE_URL=sqlite+aiosqlite:///./data/resume.db），
生产使用 PostgreSQL（JSONB 自动生效，见 models.JSONType）。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings


def _ensure_sqlite_dir(url: str) -> None:
    if url.startswith("sqlite"):
        # sqlite+aiosqlite:///./data/resume.db → ./data 目录必须存在
        path = url.split(":///", 1)[-1]
        parent = Path(path).parent
        parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir(get_settings().database_url)
engine = create_async_engine(get_settings().database_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：请求级会话。"""
    async with SessionLocal() as session:
        yield session

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.ext.asyncio import (
    create_async_engine as sqlalchemy_create_async_engine,
)

SessionFactory = async_sessionmaker[AsyncSession]
SessionFactoryBuilder = Callable[[AsyncEngine], SessionFactory]


def create_engine(database_url: str) -> AsyncEngine:
    """创建可注入的异步数据库引擎。"""

    return sqlalchemy_create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    """基于传入引擎创建异步 Session 工厂。"""

    return async_sessionmaker(bind=engine, expire_on_commit=False)


def to_sync_database_url(database_url: str) -> str:
    """将异步 URL 转为 Alembic 可用的同步 psycopg URL。"""

    url = make_url(database_url)
    if url.drivername == "postgresql+asyncpg":
        url = url.set(drivername="postgresql+psycopg")
    elif url.drivername == "postgresql+psycopg_async":
        url = url.set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)

"""数据库测试夹具与隔离约定。"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from app.core.db import to_sync_database_url

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://bid_agent:bid_agent_test@localhost:55432/bid_agent_test",
)
PSYCOPG_TEST_DATABASE_URL = to_sync_database_url(TEST_DATABASE_URL).replace("+psycopg", "")
BACKEND_DIR = Path(__file__).resolve().parents[1]
TRUNCATE_SQL = """
TRUNCATE TABLE
    audit.audit_event,
    project.project_member,
    project.bid_package,
    project.bid_project,
    iam.idempotency_record,
    iam.user_session,
    iam."user",
    iam.organization
RESTART IDENTITY CASCADE
"""
DISABLE_TRUNCATE_TRIGGER_SQL = (
    "ALTER TABLE audit.audit_event DISABLE TRIGGER audit_event_no_truncate"
)
ENABLE_TRUNCATE_TRIGGER_SQL = "ALTER TABLE audit.audit_event ENABLE TRIGGER audit_event_no_truncate"
RESET_PROJECT_CODE_SEQ_SQL = "ALTER SEQUENCE project.project_code_seq RESTART WITH 1"


def _alembic_env() -> dict[str, str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = TEST_DATABASE_URL
    env["APP_ENV"] = "test"
    return env


def run_alembic(*args: str) -> None:
    result = subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=BACKEND_DIR,
        env=_alembic_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)


def reset_database() -> None:
    with psycopg.connect(PSYCOPG_TEST_DATABASE_URL, autocommit=True) as connection:
        with connection.cursor() as cursor:
            # 这是测试夹具的特权操作：临时关闭 TRUNCATE 阻断触发器以清理共享测试库。
            # 生产应用不得拥有 ALTER TABLE 权限，也不得关闭 append-only 保护。
            cursor.execute(DISABLE_TRUNCATE_TRIGGER_SQL)
            try:
                cursor.execute(TRUNCATE_SQL)
                cursor.execute(RESET_PROJECT_CODE_SEQ_SQL)
            finally:
                cursor.execute(ENABLE_TRUNCATE_TRIGGER_SQL)


@pytest.fixture(scope="session")
def migrated_database() -> str:
    run_alembic("downgrade", "base")
    run_alembic("upgrade", "head")
    return TEST_DATABASE_URL


@pytest.fixture()
def clean_database(migrated_database: str) -> Iterator[None]:
    reset_database()
    yield
    reset_database()


@pytest.fixture()
def db_connection(migrated_database: str) -> Iterator[psycopg.Connection]:
    reset_database()
    with psycopg.connect(PSYCOPG_TEST_DATABASE_URL) as connection:
        yield connection
    reset_database()

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from app.core.db import to_sync_database_url

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://bid_agent:bid_agent_test@localhost:55432/bid_agent_test",
)
PSYCOPG_DATABASE_URL = to_sync_database_url(DATABASE_URL).replace("+psycopg", "")
EXPECTED_TABLES = {
    ("iam", "organization"),
    ("iam", "user"),
    ("iam", "user_session"),
    ("iam", "idempotency_record"),
    ("project", "bid_project"),
    ("project", "bid_package"),
    ("project", "project_member"),
    ("audit", "audit_event"),
    ("document", "procurement_document"),
    ("document", "document_version"),
    ("document", "document_parse"),
    ("document", "document_page"),
    ("document", "document_segment"),
    ("workflow", "task_run"),
}


@pytest.fixture
def alembic_env() -> Iterator[dict[str, str]]:
    env = os.environ.copy()
    env["DATABASE_URL"] = DATABASE_URL
    env["APP_ENV"] = "test"
    yield env


def _run_alembic(alembic_env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=BACKEND_DIR,
        env=alembic_env,
        capture_output=True,
        text=True,
        check=False,
    )


def _fetch_tables() -> set[tuple[str, str]]:
    with psycopg.connect(PSYCOPG_DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_schema IN ('iam', 'project', 'document', 'audit', 'workflow')
                ORDER BY table_schema, table_name
                """
            )
            return set(cursor.fetchall())


def _schema_exists(schema_name: str) -> bool:
    with psycopg.connect(PSYCOPG_DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = %s)",
                (schema_name,),
            )
            row = cursor.fetchone()
            assert row is not None
            return bool(row[0])


def _fetch_user_constraints() -> set[str]:
    with psycopg.connect(PSYCOPG_DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'iam."user"'::regclass
                ORDER BY conname
                """
            )
            return {row[0] for row in cursor.fetchall()}


def _fetch_user_indexes() -> set[str]:
    with psycopg.connect(PSYCOPG_DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'iam' AND tablename = 'user'
                ORDER BY indexname
                """
            )
            return {row[0] for row in cursor.fetchall()}


def test_alembic_downgrade_and_upgrade_cycle(alembic_env: dict[str, str]) -> None:
    try:
        downgrade_base_result = _run_alembic(alembic_env, "downgrade", "base")
        assert downgrade_base_result.returncode == 0, (
            downgrade_base_result.stderr or downgrade_base_result.stdout
        )

        first_upgrade_result = _run_alembic(alembic_env, "upgrade", "head")
        assert first_upgrade_result.returncode == 0, (
            first_upgrade_result.stderr or first_upgrade_result.stdout
        )
        assert EXPECTED_TABLES <= _fetch_tables()
        assert "ck_user_login_name_normalized" in _fetch_user_constraints()
        assert "uq_user_organization_login_name_normalized" in _fetch_user_indexes()

        second_downgrade_result = _run_alembic(alembic_env, "downgrade", "base")
        assert second_downgrade_result.returncode == 0, (
            second_downgrade_result.stderr or second_downgrade_result.stdout
        )

        second_upgrade_result = _run_alembic(alembic_env, "upgrade", "head")
        assert second_upgrade_result.returncode == 0, (
            second_upgrade_result.stderr or second_upgrade_result.stdout
        )
        assert EXPECTED_TABLES <= _fetch_tables()
        assert "ck_user_login_name_normalized" in _fetch_user_constraints()
        assert "uq_user_organization_login_name_normalized" in _fetch_user_indexes()
    finally:
        _run_alembic(alembic_env, "upgrade", "head")


def test_document_migration_rejects_preexisting_schema(
    alembic_env: dict[str, str],
) -> None:
    try:
        downgrade_base_result = _run_alembic(alembic_env, "downgrade", "base")
        assert downgrade_base_result.returncode == 0, (
            downgrade_base_result.stderr or downgrade_base_result.stdout
        )

        with psycopg.connect(PSYCOPG_DATABASE_URL, autocommit=True) as connection:
            connection.execute("CREATE SCHEMA document")

        upgrade_result = _run_alembic(alembic_env, "upgrade", "head")

        assert upgrade_result.returncode != 0
        assert (
            "document schema already exists"
            in (upgrade_result.stderr + upgrade_result.stdout).lower()
        )
        assert _schema_exists("document")
    finally:
        restore_downgrade_result = _run_alembic(alembic_env, "downgrade", "base")
        assert restore_downgrade_result.returncode == 0, (
            restore_downgrade_result.stderr or restore_downgrade_result.stdout
        )
        with psycopg.connect(PSYCOPG_DATABASE_URL, autocommit=True) as connection:
            connection.execute("DROP SCHEMA IF EXISTS document CASCADE")
        restore_result = _run_alembic(alembic_env, "upgrade", "head")
        assert restore_result.returncode == 0, restore_result.stderr or restore_result.stdout

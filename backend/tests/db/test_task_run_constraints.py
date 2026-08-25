from __future__ import annotations

import uuid
from datetime import UTC, datetime

import psycopg
import pytest
from psycopg import IntegrityError
from psycopg.types.json import Jsonb

from tests.db.test_constraints import (
    assert_constraint_name,
    insert_document_version,
    insert_organization,
    insert_procurement_document,
    insert_project,
)


def _insert_task_run(
    connection: psycopg.Connection,
    project_id: uuid.UUID,
    document_version_id: uuid.UUID,
    *,
    task_id: uuid.UUID | None = None,
    task_type: str = "DOCUMENT_PARSE",
    task_status: str = "QUEUED",
    progress_percent: int | None = 0,
) -> uuid.UUID:
    task_id = task_id or uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO workflow.task_run (
                id, project_id, document_version_id, task_type, task_status,
                idempotency_key, payload_refs, progress_percent, retry_count, max_retries,
                queued_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                task_id,
                project_id,
                document_version_id,
                task_type,
                task_status,
                f"idem-{task_id}",
                Jsonb({"document_version_id": str(document_version_id)}),
                progress_percent,
                0,
                3,
                datetime.now(UTC),
            ),
        )
    return task_id


def test_document_parse_task_is_unique_for_same_version(
    db_connection: psycopg.Connection,
) -> None:
    organization_id = insert_organization(db_connection, tenant_key="task-unique")
    project_id = insert_project(db_connection, organization_id, project_code="TASK-UNIQUE")
    document_id = insert_procurement_document(db_connection, project_id)
    document_version_id = insert_document_version(db_connection, document_id)
    _insert_task_run(db_connection, project_id, document_version_id)

    with pytest.raises(IntegrityError) as exc_info:
        _insert_task_run(db_connection, project_id, document_version_id)

    assert_constraint_name(exc_info, "uq_task_run_active_document_parse_version")
    db_connection.rollback()


def test_document_parse_task_allows_terminal_retry_for_same_version(
    db_connection: psycopg.Connection,
) -> None:
    organization_id = insert_organization(db_connection, tenant_key="task-retry")
    project_id = insert_project(db_connection, organization_id, project_code="TASK-RETRY")
    document_id = insert_procurement_document(db_connection, project_id)
    document_version_id = insert_document_version(db_connection, document_id)
    _insert_task_run(db_connection, project_id, document_version_id, task_status="FAILED")
    _insert_task_run(db_connection, project_id, document_version_id, task_id=uuid.uuid4())


def test_task_run_rejects_progress_outside_zero_to_one_hundred(
    db_connection: psycopg.Connection,
) -> None:
    organization_id = insert_organization(db_connection, tenant_key="task-progress")
    project_id = insert_project(db_connection, organization_id, project_code="TASK-PROGRESS")
    document_id = insert_procurement_document(db_connection, project_id)
    document_version_id = insert_document_version(db_connection, document_id)

    with pytest.raises(IntegrityError) as exc_info:
        _insert_task_run(db_connection, project_id, document_version_id, progress_percent=101)

    assert_constraint_name(exc_info, "ck_task_run_progress_percent")
    db_connection.rollback()

    with pytest.raises(IntegrityError) as exc_info:
        _insert_task_run(db_connection, project_id, document_version_id, progress_percent=-1)

    assert_constraint_name(exc_info, "ck_task_run_progress_percent")
    db_connection.rollback()

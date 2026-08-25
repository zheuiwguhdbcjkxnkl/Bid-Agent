from __future__ import annotations

import uuid

import psycopg
import pytest
from psycopg import IntegrityError

from tests.db.test_constraints import (
    assert_constraint_name,
    insert_document_version,
    insert_organization,
    insert_procurement_document,
    insert_project,
)


def test_document_parse_tables_exist(db_connection: psycopg.Connection) -> None:
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE (table_schema, table_name) IN (
                ('workflow', 'task_run'),
                ('document', 'document_parse'),
                ('document', 'document_page'),
                ('document', 'document_segment')
            )
            """
        )
        assert set(cursor.fetchall()) == {
            ("workflow", "task_run"),
            ("document", "document_parse"),
            ("document", "document_page"),
            ("document", "document_segment"),
        }


def test_document_version_accepts_all_parse_lifecycle_statuses(
    db_connection: psycopg.Connection,
) -> None:
    organization_id = insert_organization(db_connection, tenant_key="parse-status")
    project_id = insert_project(db_connection, organization_id, project_code="PARSE-STATUS")
    document_id = insert_procurement_document(db_connection, project_id)

    with db_connection.cursor() as cursor:
        for version_no, parse_status in enumerate(
            ("PENDING", "PARSING", "PARSED", "PARSE_FAILED"), start=1
        ):
            cursor.execute(
                """
                INSERT INTO document.document_version (
                    id, document_id, version_no, file_name, content_type,
                    file_size, content_hash, storage_uri, parse_status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    uuid.uuid4(),
                    document_id,
                    f"v{version_no}",
                    "bid.pdf",
                    "application/pdf",
                    1,
                    f"status-hash-{version_no}",
                    f"memory://bid-{version_no}.pdf",
                    parse_status,
                ),
            )


def test_document_version_rejects_unknown_parse_status(
    db_connection: psycopg.Connection,
) -> None:
    organization_id = insert_organization(db_connection, tenant_key="parse-status-invalid")
    project_id = insert_project(db_connection, organization_id, project_code="PARSE-INVALID")
    document_id = insert_procurement_document(db_connection, project_id)

    with pytest.raises(IntegrityError) as exc_info:
        insert_document_version(
            db_connection,
            document_id,
            content_hash="invalid-status-hash",
        )
        with db_connection.cursor() as cursor:
            cursor.execute(
                "UPDATE document.document_version "
                "SET parse_status = 'UNKNOWN' WHERE document_id = %s",
                (document_id,),
            )

    assert_constraint_name(exc_info, "ck_document_version_parse_status")
    db_connection.rollback()

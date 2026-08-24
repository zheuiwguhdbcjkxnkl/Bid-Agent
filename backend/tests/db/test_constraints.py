from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg import IntegrityError


def assert_constraint_name(exc_info: pytest.ExceptionInfo[IntegrityError], expected: str) -> None:
    """断言数据库返回的约束名，避免仅匹配宽泛的 IntegrityError。"""

    original_error = getattr(exc_info.value, "orig", exc_info.value)
    constraint_name = original_error.diag.constraint_name
    assert constraint_name == expected


def now_utc() -> datetime:
    return datetime.now(UTC)


def insert_organization(connection: psycopg.Connection, tenant_key: str = "tenant-a") -> uuid.UUID:
    organization_id = uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO iam.organization (
                id, name, organization_type, tenant_key, data_classification
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (organization_id, "测试组织", "CLIENT", tenant_key, "INTERNAL"),
        )
    return organization_id


def insert_user(
    connection: psycopg.Connection,
    organization_id: uuid.UUID,
    login_name: str = "alice",
) -> uuid.UUID:
    user_id = uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO iam."user" (
                id, organization_id, login_name, display_name, account_status,
                system_role, password_hash, must_change_password
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                organization_id,
                login_name,
                "测试用户",
                "ACTIVE",
                "ADMIN",
                "argon2id$fake",
                False,
            ),
        )
    return user_id


def insert_session(
    connection: psycopg.Connection,
    user_id: uuid.UUID,
    token_hash: str = "token-hash-1",
) -> uuid.UUID:
    session_id = uuid.uuid4()
    current_time = now_utc()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO iam.user_session (
                id, user_id, token_hash, last_seen_at, idle_expires_at, absolute_expires_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                session_id,
                user_id,
                token_hash,
                current_time,
                current_time + timedelta(minutes=30),
                current_time + timedelta(hours=8),
            ),
        )
    return session_id


def insert_idempotency_record(
    connection: psycopg.Connection,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    idempotency_key: str = "idem-1",
    processing_status: str = "PROCESSING",
    include_succeeded_payload: bool = True,
) -> uuid.UUID:
    record_id = uuid.uuid4()
    current_time = now_utc()
    response_status = (
        201 if processing_status == "SUCCEEDED" and include_succeeded_payload else None
    )
    response_body = (
        {"ok": True} if processing_status == "SUCCEEDED" and include_succeeded_payload else None
    )
    completed_at = (
        current_time if processing_status == "SUCCEEDED" and include_succeeded_payload else None
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO iam.idempotency_record (
                id, organization_id, actor_user_id, http_method, route_template,
                idempotency_key, request_hash, processing_status, response_status,
                response_body, resource_type, resource_id, completed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record_id,
                organization_id,
                user_id,
                "POST",
                "/api/v1/projects",
                idempotency_key,
                f"hash-{idempotency_key}",
                processing_status,
                response_status,
                response_body,
                "bid_project",
                uuid.uuid4(),
                completed_at,
            ),
        )
    return record_id


def insert_project(
    connection: psycopg.Connection,
    organization_id: uuid.UUID,
    project_code: str = "P-001",
) -> uuid.UUID:
    project_id = uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO project.bid_project (
                id, organization_id, project_code, project_name,
                procurement_method, regime_type, project_status, external_ai_policy
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                project_id,
                organization_id,
                project_code,
                "测试项目",
                "PUBLIC_TENDER",
                "GOVERNMENT_PROCUREMENT",
                "DRAFT",
                "PUBLIC_ONLY",
            ),
        )
    return project_id


def insert_procurement_document(
    connection: psycopg.Connection,
    project_id: uuid.UUID,
    document_type: str = "PROCUREMENT_FILE",
    display_name: str = "采购文件",
) -> uuid.UUID:
    document_id = uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO document.procurement_document (
                id, project_id, document_type, display_name
            )
            VALUES (%s, %s, %s, %s)
            """,
            (document_id, project_id, document_type, display_name),
        )
    return document_id


def insert_document_version(
    connection: psycopg.Connection,
    document_id: uuid.UUID,
    version_no: str = "1",
    content_hash: str = "hash-1",
) -> uuid.UUID:
    version_id = uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO document.document_version (
                id, document_id, version_no, file_name, content_type,
                file_size, content_hash, storage_uri
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                version_id,
                document_id,
                version_no,
                "采购文件.pdf",
                "application/pdf",
                1024,
                content_hash,
                "s3://test-bucket/document.pdf",
            ),
        )
    return version_id


def insert_package(
    connection: psycopg.Connection,
    project_id: uuid.UUID,
    package_code: str = "PKG-001",
    is_v1_primary: bool = False,
) -> uuid.UUID:
    package_id = uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO project.bid_package (
                id, project_id, package_code, package_name, package_status, is_v1_primary
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (package_id, project_id, package_code, "主标包", "ACTIVE", is_v1_primary),
        )
    return package_id


def insert_project_member(
    connection: psycopg.Connection,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    project_role: str = "BID_MANAGER",
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO project.project_member (
                project_id, user_id, project_role, assignment_status
            )
            VALUES (%s, %s, %s, %s)
            """,
            (project_id, user_id, project_role, "ACTIVE"),
        )


def insert_audit_event(
    connection: psycopg.Connection,
    organization_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> uuid.UUID:
    audit_id = uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO audit.audit_event (
                id, organization_id, project_id, event_type, object_type,
                object_id, actor_user_id, actor_type, request_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                audit_id,
                organization_id,
                project_id,
                "PROJECT_CREATED",
                "bid_project",
                project_id,
                actor_user_id,
                "USER",
                f"req-{audit_id}",
            ),
        )
    return audit_id


def test_document_version_rejects_duplicate_document_hash(
    db_connection: psycopg.Connection,
) -> None:
    organization_id = insert_organization(db_connection, tenant_key="document-tenant")
    project_id = insert_project(db_connection, organization_id, project_code="DOC-001")
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO document.procurement_document (
                id, project_id, document_type, display_name, document_status, created_at
            )
            VALUES (gen_random_uuid(), %s, 'PROCUREMENT_FILE', '招标文件', 'ACTIVE', now())
            RETURNING id
            """,
            (project_id,),
        )
        row = cursor.fetchone()
        assert row is not None
        document_id = row[0]
        cursor.execute(
            """
            INSERT INTO document.document_version (
                id, document_id, version_no, file_name, content_type, file_size,
                content_hash, storage_uri, parse_status, uploaded_at
            )
            VALUES (
                gen_random_uuid(), %s, 'v1', 'bid.pdf', 'application/pdf', 3,
                'hash-1', 'memory://bid.pdf', 'PENDING', now()
            )
            """,
            (document_id,),
        )
        with pytest.raises(IntegrityError) as exc_info:
            cursor.execute(
                """
                INSERT INTO document.document_version (
                    id, document_id, version_no, file_name, content_type, file_size,
                    content_hash, storage_uri, parse_status, uploaded_at
                )
                VALUES (
                    gen_random_uuid(), %s, 'v2', 'bid-copy.pdf', 'application/pdf', 3,
                    'hash-1', 'memory://bid-copy.pdf', 'PENDING', now()
                )
                """,
                (document_id,),
            )
    assert_constraint_name(exc_info, "uq_document_version_hash")
    db_connection.rollback()


def test_document_constraints_reject_invalid_values(db_connection: psycopg.Connection) -> None:
    organization_id = insert_organization(db_connection, tenant_key="document-constraints")
    project_id = insert_project(db_connection, organization_id, project_code="DOC-002")
    db_connection.commit()
    with db_connection.cursor() as cursor:
        with pytest.raises(IntegrityError) as exc_info:
            cursor.execute(
                """
                INSERT INTO document.procurement_document (
                    id, project_id, document_type, display_name, document_status
                )
                VALUES (gen_random_uuid(), %s, 'UNSUPPORTED', '文件', 'ACTIVE')
                """,
                (project_id,),
            )
    assert_constraint_name(exc_info, "ck_procurement_document_type")
    db_connection.rollback()

    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO document.procurement_document (
                id, project_id, document_type, display_name, document_status
            )
            VALUES (gen_random_uuid(), %s, 'PROCUREMENT_FILE', '招标文件', 'ACTIVE')
            RETURNING id
            """,
            (project_id,),
        )
        row = cursor.fetchone()
        assert row is not None
        document_id = row[0]
        with pytest.raises(IntegrityError) as exc_info:
            cursor.execute(
                """
                INSERT INTO document.document_version (
                    id, document_id, version_no, file_name, content_type, file_size,
                    content_hash, storage_uri, parse_status
                )
                VALUES (
                    gen_random_uuid(), %s, 'v1', 'bid.pdf', 'application/pdf', -1,
                    'hash-invalid-size', 'memory://bid.pdf', 'PENDING'
                )
                """,
                (document_id,),
            )
    assert_constraint_name(exc_info, "ck_document_version_file_size_non_negative")
    db_connection.rollback()

    with db_connection.cursor() as cursor:
        with pytest.raises(IntegrityError) as exc_info:
            cursor.execute(
                """
                INSERT INTO document.document_version (
                    id, document_id, version_no, file_name, content_type, file_size,
                    content_hash, storage_uri, parse_status
                )
                VALUES (
                    gen_random_uuid(), %s, 'v1', 'bid.pdf', 'application/pdf', 1,
                    'hash-invalid-status', 'memory://bid.pdf', 'PARSED'
                )
                """,
                (document_id,),
            )
    assert_constraint_name(exc_info, "ck_document_version_parse_status")
    db_connection.rollback()


def test_document_status_must_be_active(db_connection: psycopg.Connection) -> None:
    organization_id = insert_organization(db_connection, tenant_key="document-status")
    project_id = insert_project(db_connection, organization_id, project_code="DOC-003")
    with db_connection.cursor() as cursor:
        with pytest.raises(IntegrityError) as exc_info:
            cursor.execute(
                """
                INSERT INTO document.procurement_document (
                    id, project_id, document_type, display_name, document_status
                )
                VALUES (gen_random_uuid(), %s, 'PROCUREMENT_FILE', '文件', 'ARCHIVED')
                """,
                (project_id,),
            )
    assert_constraint_name(exc_info, "ck_procurement_document_status")
    db_connection.rollback()


def test_procurement_document_rejects_missing_project_id(
    db_connection: psycopg.Connection,
) -> None:
    with pytest.raises(IntegrityError) as exc_info:
        insert_procurement_document(db_connection, uuid.uuid4())
    original_error = getattr(exc_info.value, "orig", exc_info.value)
    assert original_error.sqlstate == "23503"
    assert original_error.diag.table_name == "procurement_document"
    db_connection.rollback()


def test_document_version_rejects_missing_document_id(
    db_connection: psycopg.Connection,
) -> None:
    with pytest.raises(IntegrityError) as exc_info:
        insert_document_version(db_connection, uuid.uuid4())
    original_error = getattr(exc_info.value, "orig", exc_info.value)
    assert original_error.sqlstate == "23503"
    assert original_error.diag.table_name == "document_version"
    db_connection.rollback()


def test_document_version_must_have_unique_version_no_per_document(
    db_connection: psycopg.Connection,
) -> None:
    organization_id = insert_organization(db_connection)
    project_id = insert_project(db_connection, organization_id)
    document_id = insert_procurement_document(db_connection, project_id)
    insert_document_version(db_connection, document_id, version_no="1", content_hash="hash-1")

    with pytest.raises(IntegrityError) as exc_info:
        insert_document_version(db_connection, document_id, version_no="1", content_hash="hash-2")
    assert_constraint_name(exc_info, "uq_document_version_no")
    db_connection.rollback()


def test_normalized_user_login_name_must_be_unique_within_organization(
    db_connection: psycopg.Connection,
) -> None:
    organization_id = insert_organization(db_connection)
    insert_user(db_connection, organization_id, login_name="admin")

    with pytest.raises(IntegrityError) as exc_info:
        insert_user(db_connection, organization_id, login_name="admin")
    assert_constraint_name(exc_info, "uq_user_organization_login_name_normalized")
    db_connection.rollback()


def test_user_login_name_must_be_normalized_before_insert(
    db_connection: psycopg.Connection,
) -> None:
    organization_id = insert_organization(db_connection)

    with pytest.raises(IntegrityError) as exc_info:
        insert_user(db_connection, organization_id, login_name=" Admin ")
    assert_constraint_name(exc_info, "ck_user_login_name_normalized")
    db_connection.rollback()


def test_user_login_name_may_repeat_across_organizations_when_normalized_equal(
    db_connection: psycopg.Connection,
) -> None:
    first_organization_id = insert_organization(db_connection, tenant_key="tenant-a")
    second_organization_id = insert_organization(db_connection, tenant_key="tenant-b")

    insert_user(db_connection, first_organization_id, login_name="admin")
    insert_user(db_connection, second_organization_id, login_name="admin")

    db_connection.commit()
    db_connection.rollback()


def test_session_token_hash_must_be_unique(db_connection: psycopg.Connection) -> None:
    organization_id = insert_organization(db_connection)
    user_id = insert_user(db_connection, organization_id)
    insert_session(db_connection, user_id, token_hash="same-token")

    with pytest.raises(IntegrityError) as exc_info:
        insert_session(db_connection, user_id, token_hash="same-token")
    assert_constraint_name(exc_info, "uq_user_session_token_hash")
    db_connection.rollback()


def test_idempotency_scope_must_be_unique(db_connection: psycopg.Connection) -> None:
    organization_id = insert_organization(db_connection)
    user_id = insert_user(db_connection, organization_id)
    insert_idempotency_record(db_connection, organization_id, user_id, idempotency_key="same-key")

    with pytest.raises(IntegrityError) as exc_info:
        insert_idempotency_record(
            db_connection, organization_id, user_id, idempotency_key="same-key"
        )
    assert_constraint_name(exc_info, "uq_idempotency_record_scope")
    db_connection.rollback()


def test_project_code_must_be_unique_within_organization(db_connection: psycopg.Connection) -> None:
    organization_id = insert_organization(db_connection)
    insert_project(db_connection, organization_id, project_code="PRJ-001")

    with pytest.raises(IntegrityError) as exc_info:
        insert_project(db_connection, organization_id, project_code="PRJ-001")
    assert_constraint_name(exc_info, "uq_bid_project_organization_project_code")
    db_connection.rollback()


def test_package_code_must_be_unique_within_project(db_connection: psycopg.Connection) -> None:
    organization_id = insert_organization(db_connection)
    project_id = insert_project(db_connection, organization_id)
    insert_package(db_connection, project_id, package_code="PKG-001")

    with pytest.raises(IntegrityError) as exc_info:
        insert_package(db_connection, project_id, package_code="PKG-001")
    assert_constraint_name(exc_info, "uq_bid_package_project_package_code")
    db_connection.rollback()


def test_project_can_only_have_one_primary_package(db_connection: psycopg.Connection) -> None:
    organization_id = insert_organization(db_connection)
    project_id = insert_project(db_connection, organization_id)
    insert_package(db_connection, project_id, package_code="PKG-001", is_v1_primary=True)

    with pytest.raises(IntegrityError) as exc_info:
        insert_package(db_connection, project_id, package_code="PKG-002", is_v1_primary=True)
    assert_constraint_name(exc_info, "uq_bid_package_single_primary")
    db_connection.rollback()


def test_project_member_must_be_unique(db_connection: psycopg.Connection) -> None:
    organization_id = insert_organization(db_connection)
    user_id = insert_user(db_connection, organization_id)
    project_id = insert_project(db_connection, organization_id)
    insert_project_member(db_connection, project_id, user_id)

    with pytest.raises(IntegrityError) as exc_info:
        insert_project_member(db_connection, project_id, user_id)
    assert_constraint_name(exc_info, "pk_project_member")
    db_connection.rollback()


def test_audit_event_requires_organization_id(db_connection: psycopg.Connection) -> None:
    with pytest.raises(IntegrityError) as exc_info:
        insert_audit_event(db_connection, None, None, None)
    original_error = getattr(exc_info.value, "orig", exc_info.value)
    assert original_error.sqlstate == "23502"
    assert original_error.diag.column_name == "organization_id"
    db_connection.rollback()


def test_audit_event_rejects_update(db_connection: psycopg.Connection) -> None:
    organization_id = insert_organization(db_connection)
    user_id = insert_user(db_connection, organization_id)
    project_id = insert_project(db_connection, organization_id)
    audit_id = insert_audit_event(db_connection, organization_id, project_id, user_id)

    with pytest.raises(psycopg.Error, match="audit_event is append-only"):
        with db_connection.cursor() as cursor:
            cursor.execute(
                "UPDATE audit.audit_event SET reason = %s WHERE id = %s",
                ("不允许修改", audit_id),
            )
    db_connection.rollback()


def test_audit_event_rejects_delete(db_connection: psycopg.Connection) -> None:
    organization_id = insert_organization(db_connection)
    user_id = insert_user(db_connection, organization_id)
    project_id = insert_project(db_connection, organization_id)
    audit_id = insert_audit_event(db_connection, organization_id, project_id, user_id)

    with pytest.raises(psycopg.Error, match="audit_event is append-only"):
        with db_connection.cursor() as cursor:
            cursor.execute("DELETE FROM audit.audit_event WHERE id = %s", (audit_id,))
    db_connection.rollback()


def test_audit_event_rejects_truncate(db_connection: psycopg.Connection) -> None:
    organization_id = insert_organization(db_connection)
    user_id = insert_user(db_connection, organization_id)
    project_id = insert_project(db_connection, organization_id)
    insert_audit_event(db_connection, organization_id, project_id, user_id)

    with pytest.raises(psycopg.Error, match="audit_event is append-only"):
        with db_connection.cursor() as cursor:
            cursor.execute("TRUNCATE audit.audit_event")
    db_connection.rollback()


def test_succeeded_idempotency_record_requires_response_fields(
    db_connection: psycopg.Connection,
) -> None:
    organization_id = insert_organization(db_connection)
    user_id = insert_user(db_connection, organization_id)

    with pytest.raises(IntegrityError) as exc_info:
        insert_idempotency_record(
            db_connection,
            organization_id,
            user_id,
            idempotency_key="succeeded-missing-response",
            processing_status="SUCCEEDED",
            include_succeeded_payload=False,
        )
    assert_constraint_name(exc_info, "ck_idempotency_record_succeeded_fields")
    db_connection.rollback()

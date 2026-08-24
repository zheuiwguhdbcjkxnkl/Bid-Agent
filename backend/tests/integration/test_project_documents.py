from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.auth.dependencies import get_db_session, require_business_access
from app.auth.service import AuthenticatedContext
from app.core.config import Settings
from app.core.errors import DomainError
from app.db.models.audit import AuditEvent
from app.db.models.document import DocumentVersion, ProcurementDocument
from app.db.models.iam import IdempotencyRecord, Organization, User
from app.db.models.project import BidProject, ProjectMember
from app.main import create_app
from app.projects.documents import repository
from app.projects.documents import service as document_service_module
from app.projects.documents.queries import list_documents
from app.projects.documents.schemas import DocumentItem, DocumentType
from app.projects.documents.service import DocumentService
from app.projects.documents.storage import MemoryObjectStorage
from tests.factories import MutableClock, create_organization, create_user

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
_PDF_CONTENT = b"pdf-content"


@dataclass(slots=True)
class UploadScenario:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    organization: Organization
    actor: User
    project: BidProject
    context: AuthenticatedContext


class TrackingStorage(MemoryObjectStorage):
    def __init__(self) -> None:
        super().__init__()
        self.put_count = 0
        self.delete_count = 0

    async def put(self, *, object_key: str, content: bytes) -> str:
        self.put_count += 1
        return await super().put(object_key=object_key, content=content)

    async def delete(self, storage_uri: str) -> None:
        self.delete_count += 1
        await super().delete(storage_uri)


class FailingStorage(TrackingStorage):
    async def put(self, *, object_key: str, content: bytes) -> str:
        self.put_count += 1
        raise RuntimeError("对象存储不可用")


async def _create_upload_scenario(
    database_url: str,
    *,
    project_role: str = "BID_MANAGER",
    assignment_status: str = "ACTIVE",
) -> UploadScenario:
    from app.core.db import create_engine, create_session_factory

    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    organization = create_organization(tenant_key=f"documents-{uuid4()}")
    actor = create_user(
        organization_id=organization.id,
        login_name=f"document-user-{uuid4()}",
    )
    project = BidProject(
        id=uuid4(),
        organization_id=organization.id,
        project_code=f"BID-{uuid4()}",
        project_name="文件上传测试项目",
        procurement_method="PUBLIC_TENDER",
        regime_type="GOVERNMENT_PROCUREMENT",
        project_status="DRAFT",
        deadline_at=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
    )
    member = ProjectMember(
        project_id=project.id,
        user_id=actor.id,
        project_role=project_role,
        assignment_status=assignment_status,
    )
    async with session_factory() as session:
        session.add_all([organization, actor, project])
        await session.flush()
        session.add(member)
        await session.commit()
    return UploadScenario(
        engine=engine,
        session_factory=session_factory,
        organization=organization,
        actor=actor,
        project=project,
        context=AuthenticatedContext(
            session_id=uuid4(),
            user_id=actor.id,
            organization_id=organization.id,
            system_role=actor.system_role,
            must_change_password=False,
        ),
    )


async def _upload(
    scenario: UploadScenario,
    storage: TrackingStorage,
    *,
    key: str = "upload-1",
    content: bytes = _PDF_CONTENT,
    display_name: str = "招标文件",
    file_name: str = "bid.pdf",
    content_type: str = "application/pdf",
) -> tuple[int, DocumentItem]:
    service = DocumentService(storage=storage, now_provider=MutableClock(_NOW).now)
    async with scenario.session_factory() as session:
        return await service.upload_document(
            session,
            context=scenario.context,
            project_id=scenario.project.id,
            document_type=DocumentType.PROCUREMENT_FILE,
            display_name=display_name,
            file_name=file_name,
            content_type=content_type,
            content=content,
            idempotency_key=key,
            request_id="req-document-upload",
        )


async def test_upload_document_success_persists_version_audit_and_no_task_run(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario = await _create_upload_scenario(migrated_database)
    storage = TrackingStorage()
    try:
        status_code, item = await _upload(scenario, storage)
        assert status_code == 201
        assert item.current_version_id == item.versions[0].id
        assert item.versions[0].version_no == "v1"
        assert item.versions[0].parse_status == "PENDING"
        assert item.versions[0].file_size == len(_PDF_CONTENT)
        assert item.versions[0].storage_uri.startswith("memory://projects/")

        async with scenario.session_factory() as session:
            assert await session.scalar(select(func.count(ProcurementDocument.id))) == 1
            assert await session.scalar(select(func.count(DocumentVersion.id))) == 1
            audit = await session.scalar(
                select(AuditEvent).where(AuditEvent.event_type == "DOCUMENT_UPLOADED")
            )
            assert audit is not None
            assert audit.object_id == item.id
            task_run_table = await session.scalar(text("SELECT to_regclass('workflow.task_run')"))
            if task_run_table is not None:
                assert await session.scalar(text("SELECT count(*) FROM workflow.task_run")) == 0
    finally:
        await scenario.engine.dispose()


async def test_upload_document_same_key_replays_without_second_object_write(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario = await _create_upload_scenario(migrated_database)
    storage = TrackingStorage()
    try:
        first = await _upload(scenario, storage, key="same-key")
        second = await _upload(scenario, storage, key="same-key")
        assert second[0] == first[0] == 201
        assert second[1] == first[1]
        assert storage.put_count == 1
        async with scenario.session_factory() as session:
            assert await session.scalar(select(func.count(ProcurementDocument.id))) == 1
            assert await session.scalar(select(func.count(DocumentVersion.id))) == 1
            assert await session.scalar(select(func.count(AuditEvent.id))) == 1
            assert await session.scalar(select(func.count(IdempotencyRecord.id))) == 1
    finally:
        await scenario.engine.dispose()


async def test_upload_document_same_key_different_request_conflicts_before_put(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario = await _create_upload_scenario(migrated_database)
    storage = TrackingStorage()
    try:
        await _upload(scenario, storage, key="conflict-key")
        with pytest.raises(DomainError) as error:
            await _upload(
                scenario,
                storage,
                key="conflict-key",
                display_name="另一份文件",
            )
        assert error.value.status_code == 409
        assert error.value.code == "IDEMPOTENCY_CONFLICT"
        assert storage.put_count == 1
    finally:
        await scenario.engine.dispose()


async def test_upload_document_same_key_different_file_name_conflicts_before_put(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario = await _create_upload_scenario(migrated_database)
    storage = TrackingStorage()
    try:
        await _upload(scenario, storage, key="file-name-conflict")
        with pytest.raises(DomainError) as error:
            await _upload(
                scenario,
                storage,
                key="file-name-conflict",
                file_name="renamed.pdf",
            )
        assert error.value.status_code == 409
        assert error.value.code == "IDEMPOTENCY_CONFLICT"
        assert storage.put_count == 1
    finally:
        await scenario.engine.dispose()


async def test_upload_document_non_manager_rejected_before_put(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario = await _create_upload_scenario(
        migrated_database,
        project_role="BID_WRITER",
    )
    storage = TrackingStorage()
    try:
        with pytest.raises(DomainError) as error:
            await _upload(scenario, storage)
        assert error.value.status_code == 403
        assert error.value.code == "FORBIDDEN"
        assert storage.put_count == 0
    finally:
        await scenario.engine.dispose()


async def test_upload_document_duplicate_content_rejected_before_second_put(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario = await _create_upload_scenario(migrated_database)
    storage = TrackingStorage()
    try:
        await _upload(scenario, storage, key="first-content")
        with pytest.raises(DomainError) as error:
            await _upload(scenario, storage, key="second-content")
        assert error.value.status_code == 409
        assert error.value.code == "DOCUMENT_VERSION_EXISTS"
        assert storage.put_count == 1
    finally:
        await scenario.engine.dispose()


async def test_upload_document_storage_failure_writes_no_database_rows(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario = await _create_upload_scenario(migrated_database)
    storage = FailingStorage()
    try:
        with pytest.raises(RuntimeError, match="对象存储不可用"):
            await _upload(scenario, storage)
        async with scenario.session_factory() as session:
            assert await session.scalar(select(func.count(ProcurementDocument.id))) == 0
            assert await session.scalar(select(func.count(IdempotencyRecord.id))) == 0
    finally:
        await scenario.engine.dispose()


async def test_upload_document_database_failure_deletes_object(
    clean_database: None,
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = await _create_upload_scenario(migrated_database)
    storage = TrackingStorage()

    async def fail_create(*args: object, **kwargs: object) -> object:
        raise RuntimeError("数据库写入失败")

    monkeypatch.setattr(repository, "create_document_with_version", fail_create)
    try:
        with pytest.raises(RuntimeError, match="数据库写入失败"):
            await _upload(scenario, storage)
        assert storage.put_count == 1
        assert storage.delete_count == 1
        assert storage.objects == {}
        async with scenario.session_factory() as session:
            assert await session.scalar(select(func.count(ProcurementDocument.id))) == 0
            assert await session.scalar(select(func.count(IdempotencyRecord.id))) == 0
    finally:
        await scenario.engine.dispose()


async def test_upload_document_audit_failure_rolls_back_rows_and_deletes_object(
    clean_database: None,
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = await _create_upload_scenario(migrated_database)
    storage = TrackingStorage()

    async def fail_audit(*args: object, **kwargs: object) -> None:
        raise RuntimeError("审计写入失败")

    monkeypatch.setattr(document_service_module, "append_audit_event", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="审计写入失败"):
            await _upload(scenario, storage)
        assert storage.put_count == 1
        assert storage.delete_count == 1
        assert storage.objects == {}
        async with scenario.session_factory() as session:
            assert await session.scalar(select(func.count(ProcurementDocument.id))) == 0
            assert await session.scalar(select(func.count(DocumentVersion.id))) == 0
            assert await session.scalar(select(func.count(AuditEvent.id))) == 0
            assert await session.scalar(select(func.count(IdempotencyRecord.id))) == 0
    finally:
        await scenario.engine.dispose()


async def test_upload_document_api_success_and_list_returns_item(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario = await _create_upload_scenario(migrated_database)
    storage = TrackingStorage()
    settings = Settings(
        app_env="test",
        database_url=migrated_database,
        allowed_origins=["http://frontend.localhost"],
        session_cookie_secure=False,
    )
    app = create_app(
        settings=settings,
        now_provider=MutableClock(_NOW).now,
        document_storage=storage,
    )

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with scenario.session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[require_business_access] = lambda: scenario.context
    try:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                client.cookies.set("bid_csrf", "csrf-token")
                response = await client.post(
                    f"/api/v1/projects/{scenario.project.id}/documents",
                    headers={
                        "Origin": "http://frontend.localhost",
                        "X-CSRF-Token": "csrf-token",
                        "Idempotency-Key": "api-upload-1",
                    },
                    files={"file": ("bid.pdf", _PDF_CONTENT, "application/pdf")},
                    data={"document_type": "PROCUREMENT_FILE", "display_name": "招标文件"},
                )
                assert response.status_code == 201, response.text
                listed = await client.get(
                    f"/api/v1/projects/{scenario.project.id}/documents",
                    headers={"Origin": "http://frontend.localhost"},
                )
                assert listed.status_code == 200, listed.text
                assert listed.json()["items"][0]["id"] == response.json()["id"]
    finally:
        await scenario.engine.dispose()


async def test_list_documents_rejects_active_cross_organization_membership(
    clean_database: None,
    migrated_database: str,
) -> None:
    scenario = await _create_upload_scenario(migrated_database)
    actor_organization = create_organization(tenant_key="cross-org-actor")
    actor = create_user(
        organization_id=actor_organization.id,
        login_name="cross-org-actor",
    )
    try:
        async with scenario.session_factory() as session:
            session.add_all([actor_organization, actor])
            await session.flush()
            session.add(
                ProjectMember(
                    project_id=scenario.project.id,
                    user_id=actor.id,
                    project_role="BID_WRITER",
                    assignment_status="ACTIVE",
                )
            )
            await session.commit()
            with pytest.raises(DomainError, match="无项目访问权限") as error:
                await list_documents(
                    session,
                    project_id=scenario.project.id,
                    actor_user_id=actor.id,
                )
        assert error.value.status_code == 403
        assert error.value.code == "FORBIDDEN"
    finally:
        await scenario.engine.dispose()

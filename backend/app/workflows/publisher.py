from __future__ import annotations

from uuid import UUID

from celery import Celery  # type: ignore[import-untyped]

from app.workflows.celery_app import DOCUMENT_PARSE_TASK_NAME


class CeleryTaskPublisher:
    def __init__(self, app: Celery) -> None:
        self._app = app

    def publish_document_parse(self, task_run_id: UUID) -> str:
        message_id = str(task_run_id)
        result = self._app.send_task(
            DOCUMENT_PARSE_TASK_NAME,
            args=[message_id],
            task_id=message_id,
        )
        return str(result.id)

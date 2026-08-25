from __future__ import annotations

from celery import Celery  # type: ignore[import-untyped]

DOCUMENT_PARSE_TASK_NAME = "app.workflows.tasks.run_document_parse"
DOCUMENT_PARSE_REDELIVERY_TASK_NAME = "app.workflows.tasks.redeliver_document_parse"


def create_celery_app(redis_url: str) -> Celery:
    app = Celery(
        "bid_agent_ai",
        broker=redis_url,
        include=["app.workflows.tasks"],
    )
    app.conf.update(
        accept_content=["json"],
        task_serializer="json",
        result_backend=None,
        task_ignore_result=True,
        timezone="UTC",
        enable_utc=True,
        beat_schedule={
            "redeliver-document-parse": {
                "task": DOCUMENT_PARSE_REDELIVERY_TASK_NAME,
                "schedule": 60.0,
            }
        },
    )
    return app

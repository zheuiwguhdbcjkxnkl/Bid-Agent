from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import DocumentPage, DocumentParse, DocumentSegment, DocumentVersion
from app.db.models.workflow import TaskRun
from app.documents.ir import DocumentIR


async def persist_success(
    session: AsyncSession,
    *,
    task: TaskRun,
    version: DocumentVersion,
    document_parse: DocumentParse,
    ir: DocumentIR,
    finished_at: datetime,
) -> None:
    pages_by_number: dict[int, UUID] = {}
    for page in ir.pages:
        page_id = uuid4()
        pages_by_number[page.page_no] = page_id
        session.add(
            DocumentPage(
                id=page_id,
                document_parse_id=document_parse.id,
                page_no=page.page_no,
                width=page.width,
                height=page.height,
                metadata_json=page.metadata_json,
                created_at=finished_at,
            )
        )
    for segment in ir.segments:
        session.add(
            DocumentSegment(
                id=uuid4(),
                document_version_id=version.id,
                document_parse_id=document_parse.id,
                page_id=pages_by_number.get(segment.page_no) if segment.page_no else None,
                segment_type=segment.segment_type,
                page_no=segment.page_no,
                section_path=segment.section_path,
                content_text=segment.content_text,
                source_bbox=segment.source_bbox,
                source_hash=segment.source_hash,
                metadata_json=segment.metadata_json,
                confidence=segment.confidence,
                segment_status="DRAFT",
                created_at=finished_at,
            )
        )

    document_parse.parser_name = ir.parser_name
    document_parse.parser_version = ir.parser_version
    document_parse.model_version = ir.model_version
    document_parse.backend_mode = ir.backend_mode
    document_parse.parse_status = "SUCCEEDED"
    document_parse.started_at = task.started_at or finished_at
    document_parse.quality_summary = {
        "page_count": len(ir.pages),
        "segment_count": len(ir.segments),
    }
    document_parse.completed_at = finished_at
    version.parse_status = "PARSED"
    task.task_status = "SUCCEEDED"
    task.current_step = "COMPLETED"
    task.progress_percent = 100
    task.result_refs = {
        "document_parse_id": str(document_parse.id),
        "segment_count": len(ir.segments),
    }
    task.finished_at = finished_at
    task.heartbeat_at = finished_at
    await session.flush()


async def persist_failure(
    session: AsyncSession,
    *,
    task: TaskRun,
    version: DocumentVersion,
    document_parse: DocumentParse,
    error_code: str,
    error_message: str,
    finished_at: datetime,
) -> None:
    document_parse.parse_status = "FAILED"
    document_parse.started_at = task.started_at or finished_at
    document_parse.error_code = error_code
    document_parse.error_message = error_message
    document_parse.completed_at = finished_at
    version.parse_status = "PARSE_FAILED"
    task.task_status = "FAILED"
    task.current_step = "FAILED"
    task.last_error_code = error_code
    task.last_error_message = error_message
    task.finished_at = finished_at
    task.heartbeat_at = finished_at
    await session.flush()

from __future__ import annotations

from app.projects.schemas import _StrictModel
from app.workflows.schemas import TaskRunItem


class StartDocumentParseResponse(_StrictModel):
    task_run: TaskRunItem

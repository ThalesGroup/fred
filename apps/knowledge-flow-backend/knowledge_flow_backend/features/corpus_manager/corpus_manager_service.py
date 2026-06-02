from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

TaskStatus = Literal["queued", "running", "succeeded", "failed", "canceled"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TaskRefV1(BaseModel):
    """
    Minimal async handle returned by long-running corpus tools.
    This is MOCKED here; later it maps to Temporal workflow_id, etc.
    """

    model_config = ConfigDict(extra="forbid")

    version: Literal["v1"] = "v1"
    task_id: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime

    operation: str

    # Correlation (agentic-backend can provide it)
    thread_id: Optional[str] = None
    exchange_id: Optional[str] = None

    # Agent/UI hints
    poll_interval_s: int = Field(default=5, ge=1, le=3600)
    message: str = ""
    links: Dict[str, str] = Field(default_factory=dict)

    # Optional lightweight progress (mock)
    progress_percent: Optional[int] = Field(default=None, ge=0, le=100)


class TaskResultV1(BaseModel):
    """
    Task terminal result (MOCK).
    In real impl this references artifacts (document_uid, etc.).
    """

    model_config = ConfigDict(extra="forbid")

    version: Literal["v1"] = "v1"
    task_id: str
    status: TaskStatus
    completed_at: datetime

    # "Business" result payload is operation-specific; keep it flexible.
    result: Dict[str, Any] = Field(default_factory=dict)


class CorpusScopeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # At least one must be provided:
    library_id: Optional[str] = None
    project_id: Optional[str] = None
    tag_ids: List[str] = Field(default_factory=list)
    document_uids: List[str] = Field(default_factory=list)

    source_tag: Optional[str] = None

    @model_validator(mode="after")
    def _validate_non_empty(self) -> "CorpusScopeV1":
        if not (self.library_id or self.project_id or self.tag_ids or self.document_uids):
            raise ValueError("CorpusScopeV1 requires library_id, project_id, tag_ids or document_uids.")
        return self


class TocBuildOptionsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_depth: int = Field(default=3, ge=1, le=6)
    max_sections: int = Field(default=40, ge=5, le=200)
    include_gaps: bool = True
    gap_sensitivity: Literal["low", "medium", "high"] = "medium"

    output_format: Literal["markdown", "json", "both"] = "both"
    language: Optional[str] = Field(default=None, description="e.g. 'fr', 'en'")


class BuildCorpusTocRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["v1"] = "v1"
    scope: CorpusScopeV1
    options: TocBuildOptionsV1 = Field(default_factory=TocBuildOptionsV1)

    title: Optional[str] = Field(default=None, max_length=120)

    # Optional correlation (agentic-backend can provide it)
    thread_id: Optional[str] = None
    exchange_id: Optional[str] = None


class RevectorizeOptionsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["full", "incremental"] = "incremental"
    force: bool = False
    embedding_model: Optional[str] = None


class RevectorizeCorpusRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["v1"] = "v1"
    scope: CorpusScopeV1
    options: RevectorizeOptionsV1 = Field(default_factory=RevectorizeOptionsV1)

    thread_id: Optional[str] = None
    exchange_id: Optional[str] = None


class PurgeVectorsOptionsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purge_scope: Literal["vectors_only", "vectors_and_chunks"] = "vectors_only"
    dry_run: bool = True


class PurgeVectorsRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["v1"] = "v1"
    scope: CorpusScopeV1
    options: PurgeVectorsOptionsV1 = Field(default_factory=PurgeVectorsOptionsV1)

    thread_id: Optional[str] = None
    exchange_id: Optional[str] = None


class TaskGetRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str


class TaskResultRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str


class TaskListRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: Optional[str] = None
    exchange_id: Optional[str] = None
    operation: Optional[str] = None
    status: Optional[TaskStatus] = None
    limit: int = Field(default=20, ge=1, le=200)


class ToolSpecV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    summary: str
    request_schema: Dict[str, Any]
    async_task: bool = True


class CorpusCapabilitiesV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["v1"] = "v1"
    tools: List[ToolSpecV1]


class CorpusManagerService:
    """
    Mock corpus manager business layer.
    Replace in future with Temporal / real persistence.
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, TaskRefV1] = {}
        self._results: Dict[str, TaskResultV1] = {}

    def capabilities(self) -> CorpusCapabilitiesV1:
        return CorpusCapabilitiesV1(
            tools=[
                ToolSpecV1(
                    name="build_corpus_toc",
                    summary="Start an improved TOC build for a corpus (themes, pivot docs, gaps). Returns task handle.",
                    request_schema=BuildCorpusTocRequestV1.model_json_schema(),
                ),
                ToolSpecV1(
                    name="revectorize_corpus",
                    summary="Start revectorization for a corpus (incremental/full). Returns task handle.",
                    request_schema=RevectorizeCorpusRequestV1.model_json_schema(),
                ),
                ToolSpecV1(
                    name="purge_vectors",
                    summary="Start purge of vectors (and optionally chunks). Supports dry-run. Returns task handle.",
                    request_schema=PurgeVectorsRequestV1.model_json_schema(),
                ),
                ToolSpecV1(
                    name="tasks_get",
                    summary="Get current status for a task_id. Use to support long-running UX (come back later).",
                    request_schema=TaskGetRequestV1.model_json_schema(),
                ),
                ToolSpecV1(
                    name="tasks_result",
                    summary="Get terminal result for a task_id (succeeds/failed/canceled). If still running, returns status.",
                    request_schema=TaskResultRequestV1.model_json_schema(),
                ),
                ToolSpecV1(
                    name="tasks_list",
                    summary="List tasks (optional filters: thread_id, exchange_id, operation, status).",
                    request_schema=TaskListRequestV1.model_json_schema(),
                ),
            ]
        )

    def _mk_links(self, task_id: str) -> Dict[str, str]:
        return {
            "get": f"tasks/get?task_id={task_id}",
            "result": f"tasks/result?task_id={task_id}",
        }

    def _create_task(self, operation: str, thread_id: Optional[str], exchange_id: Optional[str]) -> TaskRefV1:
        tid = str(uuid.uuid4())
        t = TaskRefV1(
            task_id=tid,
            status="queued",
            created_at=_now(),
            updated_at=_now(),
            operation=operation,
            thread_id=thread_id,
            exchange_id=exchange_id,
            poll_interval_s=5,
            message=f"Task '{operation}' created. It may take time; poll tasks/get.",
            links=self._mk_links(tid),
            progress_percent=0,
        )
        self._tasks[tid] = t
        return t

    def _advance_mock(self, task_id: str) -> None:
        t = self._tasks[task_id]
        if t.status == "queued":
            t.status = "running"
            t.progress_percent = 10
            t.message = "Task is now running."
        elif t.status == "running":
            t.status = "succeeded"
            t.progress_percent = 100
            t.message = "Task completed successfully."
            self._results[task_id] = TaskResultV1(
                task_id=task_id,
                status="succeeded",
                completed_at=_now(),
                result={
                    "note": "MOCK result payload",
                    "operation": t.operation,
                    "artifact": {"type": "toc_report", "document_uid": "mock-uid-123"},
                },
            )
        t.updated_at = _now()
        self._tasks[task_id] = t

    # ---- Business methods ----

    def build_corpus_toc(self, req: BuildCorpusTocRequestV1) -> TaskRefV1:
        return self._create_task("build_corpus_toc", req.thread_id, req.exchange_id)

    def revectorize_corpus(self, req: RevectorizeCorpusRequestV1) -> TaskRefV1:
        return self._create_task("revectorize_corpus", req.thread_id, req.exchange_id)

    def purge_vectors(self, req: PurgeVectorsRequestV1) -> TaskRefV1:
        return self._create_task("purge_vectors", req.thread_id, req.exchange_id)

    def tasks_get(self, req: TaskGetRequestV1) -> TaskRefV1:
        if req.task_id not in self._tasks:
            return TaskRefV1(
                task_id=req.task_id,
                status="failed",
                created_at=_now(),
                updated_at=_now(),
                operation="unknown",
                message="Unknown task_id (mock store).",
                poll_interval_s=5,
                links={},
            )
        self._advance_mock(req.task_id)
        return self._tasks[req.task_id]

    def tasks_result(self, req: TaskResultRequestV1) -> dict:
        if req.task_id not in self._tasks:
            return {
                "version": "v1",
                "task_id": req.task_id,
                "status": "failed",
                "message": "Unknown task_id (mock store).",
                "result": {},
            }
        self._advance_mock(req.task_id)
        t = self._tasks[req.task_id]
        if t.status in ("succeeded", "failed", "canceled"):
            return self._results.get(
                req.task_id,
                TaskResultV1(
                    task_id=req.task_id,
                    status=t.status,
                    completed_at=_now(),
                    result={},
                ),
            ).model_dump()
        return {
            "version": "v1",
            "task_id": req.task_id,
            "status": t.status,
            "message": "Task not finished yet. Use tasks_get to poll later.",
            "poll_interval_s": t.poll_interval_s,
        }

    def tasks_list(self, req: TaskListRequestV1) -> dict:
        items = list(self._tasks.values())
        if req.thread_id:
            items = [t for t in items if t.thread_id == req.thread_id]
        if req.exchange_id:
            items = [t for t in items if t.exchange_id == req.exchange_id]
        if req.operation:
            items = [t for t in items if t.operation == req.operation]
        if req.status:
            items = [t for t in items if t.status == req.status]
        items.sort(key=lambda t: t.updated_at, reverse=True)
        return {
            "version": "v1",
            "count": len(items[: req.limit]),
            "items": [t.model_dump() for t in items[: req.limit]],
        }

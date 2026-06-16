import pathlib
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fred_core import KeycloakUser, TagPermission
from fred_core.scheduler import SchedulerBackend

from knowledge_flow_backend.common.document_structures import ProcessingStage, ProcessingStatus
from knowledge_flow_backend.common.structures import IngestionProcessingProfile, Status
from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController
from knowledge_flow_backend.features.ingestion.ingestion_service import IngestionService
from knowledge_flow_backend.features.scheduler.workflow_status import (
    WORKFLOW_STATUS_COMPLETED,
    WORKFLOW_STATUS_CONTINUED_AS_NEW,
    WORKFLOW_STATUS_FAILED,
    WORKFLOW_STATUS_RUNNING,
    WORKFLOW_STATUS_TIMED_OUT,
)

USER = KeycloakUser(
    uid="user-1",
    username="user1",
    email="user1@localhost",
    roles=["admin"],
    groups=["admins"],
)


# ---------------------------------------------------------------------------
# Controller-level tests for /schedule-documents (fire-and-forget submission)
# ---------------------------------------------------------------------------


def _meta(uid: str, file_type: str = "csv"):
    """A lightweight metadata stand-in with a mutable processing.workflow_id."""
    return SimpleNamespace(document_uid=uid, file_type=file_type, processing=SimpleNamespace(workflow_id=None))


class _FakeService:
    """Minimal ingestion service stub for the controller path."""

    def __init__(self, fail_for: set[str] | None = None) -> None:
        self.fail_for = fail_for or set()
        # Each entry: (document_uid, workflow_id_at_save_time)
        self.saved: list[tuple[str, str | None]] = []
        self.failed_uids: list[str] = []

    async def extract_metadata(self, user, file_path: pathlib.Path, tags, source_tag, profile):
        if file_path.name in self.fail_for:
            raise RuntimeError("boom while extracting")
        return _meta(f"doc-{file_path.stem}", file_path.suffix.lstrip("."))

    def save_input(self, user, metadata, input_dir: pathlib.Path) -> None:
        assert input_dir.exists()

    async def save_metadata(self, user, metadata) -> None:
        self.saved.append((metadata.document_uid, metadata.processing.workflow_id))

    def mark_processing_failed(self, metadata, msg: str) -> None:
        self.failed_uids.append(metadata.document_uid)


class _FakeSchedulerService:
    """Stub scheduler that records the submitted batch + workflow id."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.submitted_files = None
        self.submitted_workflow_id: str | None = None

    async def submit_documents(self, *, user, pipeline_name, files, background_tasks=None, workflow_id=None):
        if self.fail:
            raise RuntimeError("temporal unreachable")
        self.submitted_files = list(files)
        self.submitted_workflow_id = workflow_id
        # Echo the caller-provided workflow id, as the real backend does.
        return SimpleNamespace(name=pipeline_name), SimpleNamespace(workflow_id=workflow_id)


def _make_workdir(tmp_path: pathlib.Path, name: str) -> pathlib.Path:
    workdir = tmp_path / f"workdir-{name}"
    input_dir = workdir / "input"
    input_dir.mkdir(parents=True)
    input_file = input_dir / name
    input_file.write_text("city,amount\nParis,10\n", encoding="utf-8")
    return input_file


def _controller(service: _FakeService, scheduler: _FakeSchedulerService | None, backend: SchedulerBackend) -> IngestionController:
    controller = IngestionController.__new__(IngestionController)
    controller.service = cast(Any, service)
    controller.scheduler_task_service = cast(Any, scheduler)
    controller._scheduler_backend = lambda: backend
    return controller


@pytest.mark.asyncio
async def test_schedule_documents_persists_workflow_id_before_submit(tmp_path):
    """Scheduler mode: each doc is stamped with the workflow id and saved BEFORE submit."""
    service = _FakeService()
    scheduler = _FakeSchedulerService()
    controller = _controller(service, scheduler, SchedulerBackend.TEMPORAL)

    f1 = _make_workdir(tmp_path, "a.csv")
    f2 = _make_workdir(tmp_path, "b.csv")

    response = await controller._schedule_documents(
        preloaded_files=[("a.csv", f1), ("b.csv", f2)],
        user=USER,
        tags=["lib-1"],
        source_tag="fred",
        profile=IngestionProcessingProfile.MEDIUM,
        background_tasks=None,
    )

    wid = response.workflow_id
    assert wid and wid.startswith("wf-")
    # The id passed to submit is the same one that was persisted on the docs.
    assert scheduler.submitted_workflow_id == wid
    assert service.saved == [("doc-a", wid), ("doc-b", wid)]
    assert [d.status for d in response.documents] == [Status.SUCCESS, Status.SUCCESS]
    assert scheduler.submitted_files is not None and len(scheduler.submitted_files) == 2
    assert not f1.parent.parent.exists() and not f2.parent.parent.exists()


@pytest.mark.asyncio
async def test_schedule_documents_isolates_per_file_failure(tmp_path):
    service = _FakeService(fail_for={"bad.csv"})
    scheduler = _FakeSchedulerService()
    controller = _controller(service, scheduler, SchedulerBackend.TEMPORAL)

    good = _make_workdir(tmp_path, "good.csv")
    bad = _make_workdir(tmp_path, "bad.csv")

    response = await controller._schedule_documents(
        preloaded_files=[("good.csv", good), ("bad.csv", bad)],
        user=USER,
        tags=[],
        source_tag="fred",
        profile=IngestionProcessingProfile.MEDIUM,
        background_tasks=None,
    )

    by_name = {d.filename: d for d in response.documents}
    assert by_name["good.csv"].status == Status.SUCCESS
    assert by_name["bad.csv"].status == Status.FAILED
    assert by_name["bad.csv"].error
    assert scheduler.submitted_files is not None and len(scheduler.submitted_files) == 1


@pytest.mark.asyncio
async def test_schedule_documents_marks_files_failed_when_submission_fails(tmp_path):
    """Scenario A: workflow never created -> docs durably marked FAILED, not left pending."""
    service = _FakeService()
    scheduler = _FakeSchedulerService(fail=True)
    controller = _controller(service, scheduler, SchedulerBackend.TEMPORAL)

    f1 = _make_workdir(tmp_path, "a.csv")

    response = await controller._schedule_documents(
        preloaded_files=[("a.csv", f1)],
        user=USER,
        tags=[],
        source_tag="fred",
        profile=IngestionProcessingProfile.MEDIUM,
        background_tasks=None,
    )

    assert response.workflow_id is None
    assert response.documents[0].status == Status.FAILED
    assert "Scheduling failed" in (response.documents[0].error or "")
    # Durably marked failed AND persisted (saved once before submit, once after marking).
    assert service.failed_uids == ["doc-a"]
    assert service.saved.count(("doc-a", service.saved[0][1])) >= 1
    assert len([s for s in service.saved if s[0] == "doc-a"]) == 2


@pytest.mark.asyncio
async def test_schedule_documents_memory_mode_processes_inline(tmp_path, monkeypatch):
    service = _FakeService()
    controller = _controller(service, None, SchedulerBackend.MEMORY)

    async def _fake_push_input_process(*args, **kwargs):
        return kwargs["metadata"]

    async def _fake_output_process(*args, **kwargs):
        return kwargs["metadata"]

    monkeypatch.setattr(
        "knowledge_flow_backend.features.ingestion.ingestion_controller.push_input_process",
        _fake_push_input_process,
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.features.ingestion.ingestion_controller.output_process",
        _fake_output_process,
    )

    f1 = _make_workdir(tmp_path, "a.csv")

    response = await controller._schedule_documents(
        preloaded_files=[("a.csv", f1)],
        user=USER,
        tags=[],
        source_tag="fred",
        profile=IngestionProcessingProfile.MEDIUM,
        background_tasks=None,
    )

    assert response.workflow_id is None
    assert response.scheduler_backend == SchedulerBackend.MEMORY.value
    assert response.documents[0].status == Status.SUCCESS
    assert response.documents[0].document_uid == "doc-a"
    # Memory mode does not call save_metadata (inline activities persist it).
    assert service.saved == []
    assert not f1.parent.parent.exists()


# ---------------------------------------------------------------------------
# Service-level tests for the reconciliation decision logic (auth-free units)
# ---------------------------------------------------------------------------


def _bare_service(tabular_suffixes: tuple[str, ...] = (".csv",)) -> IngestionService:
    svc = IngestionService.__new__(IngestionService)
    svc.context = cast(Any, SimpleNamespace(is_tabular_file=lambda name: str(name).endswith(tabular_suffixes)))
    return svc


def test_failure_stage_picks_output_stage_by_file_kind():
    svc = _bare_service()
    assert svc._failure_stage(cast(Any, SimpleNamespace(document_name="a.csv"))) == ProcessingStage.SQL_INDEXED
    assert svc._failure_stage(cast(Any, SimpleNamespace(document_name="a.pdf"))) == ProcessingStage.VECTORIZED


def test_mark_processing_failed_flags_the_output_stage():
    svc = _bare_service()
    recorded: list[tuple[ProcessingStage, str]] = []
    meta = SimpleNamespace(document_name="a.pdf", mark_stage_error=lambda stage, msg: recorded.append((stage, msg)))
    svc.mark_processing_failed(cast(Any, meta), "kaboom")
    assert recorded == [(ProcessingStage.VECTORIZED, "kaboom")]


@pytest.mark.parametrize(
    "stages,expected",
    [
        ({ProcessingStage.VECTORIZED: ProcessingStatus.DONE}, True),
        ({ProcessingStage.SQL_INDEXED: ProcessingStatus.DONE}, True),
        ({ProcessingStage.PREVIEW_READY: ProcessingStatus.FAILED}, True),
        ({ProcessingStage.RAW_AVAILABLE: ProcessingStatus.DONE}, False),
        ({ProcessingStage.PREVIEW_READY: ProcessingStatus.IN_PROGRESS}, False),
        ({}, False),
    ],
)
def test_is_processing_terminal(stages, expected):
    meta = SimpleNamespace(processing=SimpleNamespace(stages=stages))
    assert IngestionService._is_processing_terminal(cast(Any, meta)) is expected


@pytest.mark.parametrize(
    "status,last_error,expected",
    [
        (None, None, None),  # Temporal unreachable -> never false-fail
        (WORKFLOW_STATUS_RUNNING, None, None),  # still running
        (WORKFLOW_STATUS_CONTINUED_AS_NEW, None, None),  # non-terminal
        (WORKFLOW_STATUS_FAILED, "disk full", "disk full"),  # detailed error preferred
        (WORKFLOW_STATUS_FAILED, None, "Processing workflow FAILED"),
        (WORKFLOW_STATUS_FAILED, "   ", "Processing workflow FAILED"),  # blank error ignored
        (WORKFLOW_STATUS_TIMED_OUT, None, "Processing workflow TIMED_OUT"),
        (WORKFLOW_STATUS_COMPLETED, None, "Processing workflow finished but the document was not fully processed"),
    ],
)
def test_reconciled_failure_message(status, last_error, expected):
    assert IngestionService._reconciled_failure_message(status, last_error) == expected


# ---------------------------------------------------------------------------
# Fail-fast tag authorization for /schedule-documents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_can_write_tags_checks_update_permission_on_each_tag():
    svc = _bare_service()
    calls: list[tuple] = []

    async def _check(user, permission, tag_id):
        calls.append((permission, tag_id))

    svc.metadata_service = cast(Any, SimpleNamespace(rebac=SimpleNamespace(check_user_permission_or_raise=_check)))
    await svc.ensure_can_write_tags(USER, ["t1", "t2"])
    assert calls == [(TagPermission.UPDATE, "t1"), (TagPermission.UPDATE, "t2")]


@pytest.mark.asyncio
async def test_ensure_can_write_tags_propagates_denial():
    svc = _bare_service()

    async def _deny(user, permission, tag_id):
        raise PermissionError("forbidden")

    svc.metadata_service = cast(Any, SimpleNamespace(rebac=SimpleNamespace(check_user_permission_or_raise=_deny)))
    with pytest.raises(PermissionError):
        await svc.ensure_can_write_tags(USER, ["t1"])


# ---------------------------------------------------------------------------
# Reconciliation glue (_reconcile_documents) with stubbed Temporal + persistence
# ---------------------------------------------------------------------------


def _recon_doc(uid: str, workflow_id: str | None, stages: dict, name: str = "f.pdf"):
    """A metadata stand-in supporting the reconciliation glue (mark + read)."""
    processing = SimpleNamespace(stages=stages, workflow_id=workflow_id)

    def mark_stage_error(stage, msg):
        processing.stages[stage] = ProcessingStatus.FAILED
        processing.errors = {stage: msg}

    return SimpleNamespace(document_uid=uid, document_name=name, processing=processing, mark_stage_error=mark_stage_error)


class _ReconScheduler:
    def __init__(self, status_by_workflow: dict[str, str | None], last_error: str | None = None) -> None:
        self.status_by_workflow = status_by_workflow
        self.last_error = last_error
        self.described: list[str] = []

    async def get_workflow_status(self, *, workflow_id):
        self.described.append(workflow_id)
        return self.status_by_workflow.get(workflow_id)

    async def get_workflow_last_error(self, *, workflow_id):
        return self.last_error


@pytest.mark.asyncio
async def test_reconcile_documents_fails_pending_doc_when_workflow_failed():
    """Scenario D: worker gone, workflow terminal-failed -> doc marked failed + persisted."""
    svc = _bare_service()
    saved: list[str] = []

    async def _save(user, metadata):
        saved.append(metadata.document_uid)

    svc.save_metadata = _save  # type: ignore[method-assign]

    doc = _recon_doc("doc-1", "wf-1", {ProcessingStage.RAW_AVAILABLE: ProcessingStatus.DONE})
    scheduler = _ReconScheduler({"wf-1": WORKFLOW_STATUS_TIMED_OUT})

    await svc._reconcile_documents(USER, cast(Any, scheduler), [cast(Any, doc)])

    assert doc.processing.stages[ProcessingStage.VECTORIZED] == ProcessingStatus.FAILED
    assert saved == ["doc-1"]


@pytest.mark.asyncio
async def test_reconcile_documents_leaves_running_and_unreachable_untouched():
    """Running or unreachable (None) workflows must never be marked failed."""
    svc = _bare_service()
    saved: list[str] = []

    async def _save(user, metadata):
        saved.append(metadata.document_uid)

    svc.save_metadata = _save  # type: ignore[method-assign]

    running = _recon_doc("doc-run", "wf-run", {ProcessingStage.PREVIEW_READY: ProcessingStatus.IN_PROGRESS})
    unknown = _recon_doc("doc-unk", "wf-unk", {ProcessingStage.RAW_AVAILABLE: ProcessingStatus.DONE})
    scheduler = _ReconScheduler({"wf-run": WORKFLOW_STATUS_RUNNING, "wf-unk": None})

    await svc._reconcile_documents(USER, cast(Any, scheduler), [cast(Any, running), cast(Any, unknown)])

    assert ProcessingStatus.FAILED not in running.processing.stages.values()
    assert ProcessingStatus.FAILED not in unknown.processing.stages.values()
    assert saved == []


@pytest.mark.asyncio
async def test_reconcile_documents_skips_terminal_and_linkless_docs():
    """Already-ready/failed docs and docs without a workflow_id are never described."""
    svc = _bare_service()
    svc.save_metadata = lambda user, metadata: None  # type: ignore[method-assign,assignment]

    ready = _recon_doc("doc-ready", "wf-x", {ProcessingStage.VECTORIZED: ProcessingStatus.DONE})
    linkless = _recon_doc("doc-nolink", None, {ProcessingStage.RAW_AVAILABLE: ProcessingStatus.DONE})
    scheduler = _ReconScheduler({"wf-x": WORKFLOW_STATUS_FAILED})

    await svc._reconcile_documents(USER, cast(Any, scheduler), [cast(Any, ready), cast(Any, linkless)])

    # Neither doc should have triggered a Temporal describe.
    assert scheduler.described == []

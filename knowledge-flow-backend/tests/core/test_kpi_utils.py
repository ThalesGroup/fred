from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from knowledge_flow_backend.features.scheduler import kpi_utils


def test_emit_temporal_activity_queue_wait_kpi_returns_none_outside_activity(monkeypatch):
    monkeypatch.setattr(kpi_utils.activity, "in_activity", lambda: False)
    assert kpi_utils.emit_temporal_activity_queue_wait_kpi(phase="metadata") is None


def test_emit_temporal_activity_queue_wait_kpi_emits_timer_metric(monkeypatch):
    class _FakeWriter:
        def __init__(self) -> None:
            self.calls = []

        def emit(self, **kwargs):
            self.calls.append(kwargs)

    fake_writer = _FakeWriter()

    class _FakeAppContext:
        def get_kpi_writer(self):
            return fake_writer

    started_time = datetime.now(timezone.utc)
    scheduled_time = started_time - timedelta(milliseconds=350)
    fake_info = SimpleNamespace(
        activity_type="get_push_file_metadata",
        task_queue="ingestion",
        workflow_type="ProcessPushFile",
        attempt=1,
        started_time=started_time,
        scheduled_time=scheduled_time,
    )

    monkeypatch.setattr(kpi_utils.activity, "in_activity", lambda: True)
    monkeypatch.setattr(kpi_utils.activity, "info", lambda: fake_info)

    import knowledge_flow_backend.application_context as app_context_module

    monkeypatch.setattr(
        app_context_module.ApplicationContext,
        "get_instance",
        staticmethod(lambda: _FakeAppContext()),
    )

    wait_ms = kpi_utils.emit_temporal_activity_queue_wait_kpi(
        phase="metadata",
    )

    assert wait_ms is not None
    assert wait_ms >= 300
    assert len(fake_writer.calls) == 1
    call = fake_writer.calls[0]
    assert call["name"] == "temporal.system.activity_queue_wait_ms"
    assert call["type"] == "timer"
    assert call["unit"] == "ms"
    assert call["dims"]["phase"] == "metadata"
    assert call["dims"]["activity_type"] == "get_push_file_metadata"


def test_emit_temporal_activity_result_kpis_emits_duration_and_counter(monkeypatch):
    class _FakeWriter:
        def __init__(self) -> None:
            self.emit_calls = []
            self.count_calls = []

        def emit(self, **kwargs):
            self.emit_calls.append(kwargs)

        def count(self, *args, **kwargs):
            self.count_calls.append((args, kwargs))

    fake_writer = _FakeWriter()

    class _FakeAppContext:
        def get_kpi_writer(self):
            return fake_writer

    fake_info = SimpleNamespace(
        activity_type="pull_input_process",
        task_queue="ingestion",
        workflow_type="ProcessPullFile",
        attempt=2,
    )

    monkeypatch.setattr(kpi_utils.activity, "in_activity", lambda: True)
    monkeypatch.setattr(kpi_utils.activity, "info", lambda: fake_info)
    monkeypatch.setattr(kpi_utils.time, "perf_counter", lambda: 0.25)

    import knowledge_flow_backend.application_context as app_context_module

    monkeypatch.setattr(
        app_context_module.ApplicationContext,
        "get_instance",
        staticmethod(lambda: _FakeAppContext()),
    )

    metadata = SimpleNamespace(
        file=SimpleNamespace(file_type=SimpleNamespace(value="pdf")),
        source_type=SimpleNamespace(value="pull"),
        source_tag="sharepoint",
    )

    duration_ms = kpi_utils.emit_temporal_activity_result_kpis(
        phase="input",
        started_at_monotonic=0.0,
        metadata=metadata,
        file=None,
        status="success",
    )

    assert duration_ms is not None
    assert len(fake_writer.emit_calls) == 1
    assert len(fake_writer.count_calls) == 1
    emit_call = fake_writer.emit_calls[0]
    assert emit_call["name"] == "temporal.system.activity_duration_ms"
    assert emit_call["type"] == "timer"
    assert emit_call["unit"] == "ms"
    assert emit_call["value"] == 250.0
    assert emit_call["dims"]["phase"] == "input"
    assert emit_call["dims"]["status"] == "success"
    assert emit_call["dims"]["file_type"] == "pdf"
    assert emit_call["dims"]["source_type"] == "pull"
    assert emit_call["dims"]["source_tag"] == "sharepoint"
    assert "quantities" not in emit_call
    count_args, count_kwargs = fake_writer.count_calls[0]
    assert count_args == ("temporal.ingestion.documents_total", 1)
    assert count_kwargs["dims"]["status"] == "success"


def test_emit_temporal_workflow_status_kpi_emits_counter(monkeypatch):
    class _FakeWriter:
        def __init__(self) -> None:
            self.count_calls = []

        def count(self, *args, **kwargs):
            self.count_calls.append((args, kwargs))

    fake_writer = _FakeWriter()

    class _FakeAppContext:
        def get_kpi_writer(self):
            return fake_writer

    fake_info = SimpleNamespace(
        task_queue="ingestion",
        workflow_type="ProcessPush",
    )

    monkeypatch.setattr(kpi_utils.activity, "in_activity", lambda: True)
    monkeypatch.setattr(kpi_utils.activity, "info", lambda: fake_info)

    import knowledge_flow_backend.application_context as app_context_module

    monkeypatch.setattr(
        app_context_module.ApplicationContext,
        "get_instance",
        staticmethod(lambda: _FakeAppContext()),
    )

    kpi_utils.emit_temporal_workflow_status_kpi(
        status="COMPLETED",
        workflow_id="pipeline-123",
        document_uid="doc-1",
        filename="report.pdf",
        error=None,
    )

    assert len(fake_writer.count_calls) == 1
    count_args, count_kwargs = fake_writer.count_calls[0]
    assert count_args == ("temporal.ingestion.workflows_total", 1)
    assert count_kwargs["dims"]["status"] == "completed"
    assert count_kwargs["dims"]["workflow_id_prefix"] == "pipeline"

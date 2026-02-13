import asyncio
from types import SimpleNamespace

from knowledge_flow_backend.features.scheduler import workflow as workflow_module


class _AwaitableResult:
    def __init__(self, result):
        self._result = result

    def __await__(self):
        async def _inner():
            return self._result

        return _inner().__await__()


def _patch_workflow_runtime(monkeypatch) -> None:
    monkeypatch.setattr(
        workflow_module.workflow,
        "info",
        lambda: SimpleNamespace(
            workflow_id="wf-1",
            run_id="run-1",
            task_queue="ingestion-workflow",
            attempt=1,
        ),
    )
    monkeypatch.setattr(
        workflow_module.workflow,
        "logger",
        SimpleNamespace(
            info=lambda *args, **kwargs: None,
            exception=lambda *args, **kwargs: None,
        ),
    )


def test_process_routes_process_file_on_workflow_queue_without_child_retry(monkeypatch):
    _patch_workflow_runtime(monkeypatch)
    start_child_calls: list[dict] = []

    async def fake_start_child_workflow(workflow_fn, *, args, id, task_queue=None, **kwargs):
        start_child_calls.append(
            {
                "workflow_fn": workflow_fn,
                "args": args,
                "id": id,
                "task_queue": task_queue,
                "kwargs": kwargs,
            }
        )
        return _AwaitableResult({"document_uid": "doc-1", "filename": "file-1.csv"})

    async def fake_execute_activity(name, *, args, **kwargs):
        return None

    monkeypatch.setattr(workflow_module.workflow, "start_child_workflow", fake_start_child_workflow)
    monkeypatch.setattr(workflow_module.workflow, "execute_activity", fake_execute_activity)

    definition = {
        "name": "pipeline",
        "files": [{"document_uid": "doc-1", "display_name": "file-1.csv"}],
        "max_parallelism": 1,
        "workflow_task_queue": "ingestion-workflow",
        "io_task_queue": "ingestion-io",
        "cpu_task_queue": "ingestion-cpu",
    }

    result = asyncio.run(workflow_module.Process().run(definition))

    assert result == "success"
    assert len(start_child_calls) == 1
    assert start_child_calls[0]["task_queue"] == "ingestion-workflow"
    assert start_child_calls[0]["kwargs"].get("retry_policy") is None
    # ProcessFile args include the io/cpu queue routing.
    assert start_child_calls[0]["args"][3] == "ingestion-io"
    assert start_child_calls[0]["args"][4] == "ingestion-cpu"


def test_process_file_routes_child_steps_without_retry_policy(monkeypatch):
    _patch_workflow_runtime(monkeypatch)
    child_calls: list[dict] = []

    async def fake_execute_activity(name, *, args, **kwargs):
        return None

    async def fake_execute_child_workflow(workflow_fn, *, args, id, task_queue=None, **kwargs):
        qualname = workflow_fn.__qualname__
        child_calls.append(
            {
                "qualname": qualname,
                "task_queue": task_queue,
                "retry_policy": kwargs.get("retry_policy"),
            }
        )
        if "CreatePullFileMetadata" in qualname:
            return {"document_uid": "doc-1"}
        if "LoadPullFile" in qualname:
            return "/tmp/input-file.pdf"
        if "InputProcess" in qualname:
            return {"document_uid": "doc-1"}
        if "OutputProcess" in qualname:
            return None
        raise AssertionError(f"Unexpected workflow call: {qualname}")

    monkeypatch.setattr(workflow_module.workflow, "execute_activity", fake_execute_activity)
    monkeypatch.setattr(workflow_module.workflow, "execute_child_workflow", fake_execute_child_workflow)

    file_payload = {
        "display_name": "pull-file.pdf",
        "external_path": "/pull/pull-file.pdf",
        "source_tag": "source-a",
        "hash": "hash-a",
        "processed_by": {"uid": "user-1"},
    }

    result = asyncio.run(
        workflow_module.ProcessFile().run(
            "wf-1",
            file_payload,
            0,
            io_task_queue="ingestion-io",
            cpu_task_queue="ingestion-cpu",
        )
    )

    assert result["document_uid"] == "doc-1"

    by_step = {call["qualname"]: call for call in child_calls}
    assert by_step["CreatePullFileMetadata.run"]["task_queue"] == "ingestion-io"
    assert by_step["LoadPullFile.run"]["task_queue"] == "ingestion-io"
    assert by_step["InputProcess.run"]["task_queue"] == "ingestion-cpu"
    assert by_step["OutputProcess.run"]["task_queue"] == "ingestion-cpu"
    assert all(call["retry_policy"] is None for call in child_calls)

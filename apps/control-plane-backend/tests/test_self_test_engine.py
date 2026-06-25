from __future__ import annotations

import pytest

from control_plane_backend.self_test import corpus, engine
from control_plane_backend.self_test.engine import SelfTestEngine
from control_plane_backend.self_test.models import RunState, StepStatus


class _FakeKnowledgeFlowClient:
    """Deterministic stand-in: alpha library holds the marker, beta does not."""

    def __init__(self, base_url: str, authorization: str | None) -> None:
        self.deleted_docs: list[str] = []
        self.deleted_libs: list[str] = []

    async def create_library(self, *, name: str, description: str, team_id: str) -> str:
        return f"id-{name}"

    async def ingest_document(
        self, *, library_id: str, filename: str, text: str
    ) -> str:
        return f"uid-{filename}"

    async def search(
        self,
        *,
        question: str,
        owner_filter: str,
        team_id: str | None,
        library_id: str | None = None,
        document_uid: str | None = None,
        **_: object,
    ) -> list[dict[str, str]]:
        if library_id and "alpha" in library_id:
            return [{"content": f"... {corpus.MARKER_PHRASE} ...", "uid": "u1"}]
        return [{"content": "unrelated content", "uid": "u2"}]

    async def delete_document(self, document_uid: str) -> None:
        self.deleted_docs.append(document_uid)

    async def delete_library(self, library_id: str) -> None:
        self.deleted_libs.append(library_id)


async def _drain(run_id: str) -> None:
    queue = engine.get_queue(run_id)
    assert queue is not None
    while await queue.get() is not None:
        pass


@pytest.mark.asyncio
async def test_campaign_passes_with_golden_corpus(monkeypatch) -> None:
    monkeypatch.setattr(engine, "KnowledgeFlowClient", _FakeKnowledgeFlowClient)
    eng = SelfTestEngine(
        knowledge_flow_base_url="http://kf.test", team_id="fred-selftest"
    )

    run_id = eng.start(authorization=None)
    await _drain(run_id)

    run = engine.get_run(run_id)
    assert run is not None
    assert run.state == RunState.passed
    assert run.total == 10
    assert all(s.status == StepStatus.passed for s in run.steps), [
        (s.id, s.status, s.error) for s in run.steps
    ]


@pytest.mark.asyncio
async def test_isolation_failure_is_caught_but_teardown_still_runs(monkeypatch) -> None:
    class _LeakyClient(_FakeKnowledgeFlowClient):
        async def search(self, *, question, library_id, team_id, **_):
            # Marker leaks into every scope -> the isolation step must fail.
            return [{"content": corpus.MARKER_PHRASE, "uid": "x"}]

    monkeypatch.setattr(engine, "KnowledgeFlowClient", _LeakyClient)
    eng = SelfTestEngine(
        knowledge_flow_base_url="http://kf.test", team_id="fred-selftest"
    )

    run_id = eng.start(authorization=None)
    await _drain(run_id)

    run = engine.get_run(run_id)
    assert run is not None
    assert run.state == RunState.failed
    statuses = {s.id: s.status for s in run.steps}
    assert statuses["query-scope-isolation"] == StepStatus.failed
    # Teardown must still have run despite the failure (no leaked fixtures).
    assert statuses["delete-library-alpha"] == StepStatus.passed
    assert statuses["delete-library-beta"] == StepStatus.passed

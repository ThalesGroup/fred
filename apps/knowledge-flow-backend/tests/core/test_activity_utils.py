import asyncio

import pytest
from temporalio import exceptions

from knowledge_flow_backend.features.scheduler import activity_utils


def test_await_with_heartbeat_skips_heartbeat_outside_temporal_activity(monkeypatch):
    async def _scenario() -> None:
        heartbeat_calls = 0

        def fake_heartbeat(details):
            nonlocal heartbeat_calls
            heartbeat_calls += 1

        monkeypatch.setattr(activity_utils.activity, "in_activity", lambda: False)
        monkeypatch.setattr(activity_utils.activity, "heartbeat", fake_heartbeat)

        async def _work() -> str:
            await asyncio.sleep(0.01)
            return "done"

        result = await activity_utils.await_with_heartbeat(
            _work(),
            heartbeat_details={"stage": "test"},
            heartbeat_interval_seconds=0.005,
        )
        assert result == "done"
        assert heartbeat_calls == 0

    asyncio.run(_scenario())


def test_await_with_heartbeat_calls_heartbeat_inside_temporal_activity(monkeypatch):
    async def _scenario() -> None:
        heartbeat_calls = 0

        def fake_heartbeat(details):
            nonlocal heartbeat_calls
            heartbeat_calls += 1

        monkeypatch.setattr(activity_utils.activity, "in_activity", lambda: True)
        monkeypatch.setattr(activity_utils.activity, "heartbeat", fake_heartbeat)

        async def _work() -> str:
            await asyncio.sleep(0.01)
            return "done"

        result = await activity_utils.await_with_heartbeat(
            _work(),
            heartbeat_details={"stage": "test"},
            heartbeat_interval_seconds=0.005,
        )
        assert result == "done"
        assert heartbeat_calls >= 1

    asyncio.run(_scenario())


# ── #2315: a deleted document aborts its activity ────────────────────────────


def test_raise_if_document_deleted_passes_when_the_write_landed():
    assert activity_utils.raise_if_document_deleted(True, "doc-1") is None


def test_raise_if_document_deleted_aborts_non_retryably_when_the_row_is_gone():
    # The conditional UPDATE matched no row: the document was deleted mid-flight
    # (cancelled ingestion). Retrying cannot bring it back.
    with pytest.raises(exceptions.ApplicationError) as excinfo:
        activity_utils.raise_if_document_deleted(False, "doc-1")
    assert excinfo.value.non_retryable is True
    assert "doc-1" in str(excinfo.value)

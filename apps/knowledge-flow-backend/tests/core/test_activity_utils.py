import asyncio
import threading
import time

import pytest
from temporalio import exceptions

from knowledge_flow_backend.common.cancellation import cancellation_requested, raise_if_cancelled
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


# ── #2315: cancelling drains the worker thread before the workflow resumes ───


def test_to_thread_cancel_with_drain_waits_for_the_thread_to_stop(monkeypatch):
    # The ordering this guards: the workflow's compensation purges the
    # document's artifacts as soon as the activity returns, so the activity
    # must not return until the thread's last write. Without the drain, six
    # batches of vectors were observed landing *after* the purge.
    events: list[str] = []

    def _work() -> None:
        for _ in range(1000):
            if cancellation_requested():
                events.append("thread-stopped")
                raise_if_cancelled("test loop")
            time.sleep(0.005)
        events.append("thread-never-cancelled")

    async def _scenario() -> None:
        monkeypatch.setattr(activity_utils.activity, "in_activity", lambda: False)
        task = asyncio.ensure_future(
            activity_utils.to_thread_with_heartbeat(
                _work,
                heartbeat_details={"stage": "test", "document_uid": "doc-1"},
                heartbeat_interval_seconds=0.01,
                drain_on_cancel=True,
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        events.append("activity-cancelled")

    asyncio.run(_scenario())
    assert events == ["thread-stopped", "activity-cancelled"]


def test_to_thread_cancel_without_drain_detaches_immediately(monkeypatch):
    # Work without cancellation checkpoints (input restore/processing) must not
    # pay the drain bound: the activity returns at once and the thread's output
    # is discarded later by the persist/purge fences.
    events: list[str] = []
    release = threading.Event()

    def _work() -> None:
        release.wait(timeout=5)
        events.append("thread-stopped")

    async def _scenario() -> None:
        monkeypatch.setattr(activity_utils.activity, "in_activity", lambda: False)
        task = asyncio.ensure_future(
            activity_utils.to_thread_with_heartbeat(
                _work,
                heartbeat_interval_seconds=0.01,
            )
        )
        await asyncio.sleep(0.05)
        started = asyncio.get_running_loop().time()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        events.append("activity-cancelled")
        assert asyncio.get_running_loop().time() - started < 2.0
        release.set()

    asyncio.run(_scenario())
    assert events == ["activity-cancelled", "thread-stopped"]


def test_to_thread_cancel_drain_gives_up_after_the_bound(monkeypatch):
    # A thread stuck past the bound (e.g. one stalled provider call) must not
    # hold the cancellation hostage: the activity detaches with a warning and
    # the thread's output is discarded by the fences.
    events: list[str] = []
    release = threading.Event()

    def _work() -> None:
        release.wait(timeout=5)
        events.append("thread-stopped")

    async def _scenario() -> None:
        monkeypatch.setattr(activity_utils.activity, "in_activity", lambda: False)
        monkeypatch.setattr(activity_utils, "THREAD_CANCEL_DRAIN_MAX_SECONDS", 0.05)
        task = asyncio.ensure_future(
            activity_utils.to_thread_with_heartbeat(
                _work,
                heartbeat_interval_seconds=0.01,
                drain_on_cancel=True,
            )
        )
        await asyncio.sleep(0.05)
        started = asyncio.get_running_loop().time()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        events.append("activity-cancelled")
        assert asyncio.get_running_loop().time() - started < 2.0
        release.set()

    asyncio.run(_scenario())
    assert events == ["activity-cancelled", "thread-stopped"]

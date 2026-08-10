import asyncio

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


# ── #2315: guard against resurrecting a deleted document ─────────────────────


class _StubStore:
    def __init__(self, metadata):
        self._metadata = metadata

    async def get_metadata_by_uid(self, document_uid):
        if isinstance(self._metadata, Exception):
            raise self._metadata
        return self._metadata


def test_document_still_registered_true_when_row_exists(monkeypatch):
    monkeypatch.setattr(activity_utils, "_resolve_metadata_store", lambda: _StubStore(object()))
    assert asyncio.run(activity_utils.document_still_registered("doc-1")) is True


def test_document_still_registered_false_when_row_deleted(monkeypatch):
    monkeypatch.setattr(activity_utils, "_resolve_metadata_store", lambda: _StubStore(None))
    assert asyncio.run(activity_utils.document_still_registered("doc-1")) is False


def test_document_still_registered_true_on_store_failure(monkeypatch):
    # A transient read failure must never discard a legitimate save.
    monkeypatch.setattr(activity_utils, "_resolve_metadata_store", lambda: _StubStore(RuntimeError("pg down")))
    assert asyncio.run(activity_utils.document_still_registered("doc-1")) is True

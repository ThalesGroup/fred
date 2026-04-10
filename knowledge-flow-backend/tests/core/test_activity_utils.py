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

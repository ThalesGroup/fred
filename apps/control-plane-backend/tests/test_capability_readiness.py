# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Capability readiness: the `capability_pending` suspension set and cleared
from the pod's `readiness` verdicts after a save, on listings and on re-check."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from control_plane_backend.agent_instances.suspension import (
    ReadinessVerdict,
    SuspensionReason,
    aggregate_readiness,
    reconcile_instance_readiness,
)
from control_plane_backend.product import service
from httpx import ASGITransport, AsyncClient
from test_capability_selection_1974 import (
    _fake_pod_validate,
    _record_with_selection,
    _setup,
)
from test_main import _FakeAgentInstanceStore

_PENDING = ReadinessVerdict(ready=False, capability_ids=("demo_echo",))
_FAILED = ReadinessVerdict(
    ready=False, capability_ids=("demo_echo",), detail="Template unreadable."
)
_READY = ReadinessVerdict(ready=True)


@pytest.fixture(autouse=True)
def _use_test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")


def _fake_readiness(
    monkeypatch: pytest.MonkeyPatch, verdict: ReadinessVerdict | None
) -> list[str | None]:
    """Replace the pod readiness call; records the authorization it got."""

    seen: list[str | None] = []

    async def _fake(*, base_url: str, instance, authorization, **_: Any):
        seen.append(authorization)
        return verdict

    monkeypatch.setattr(service, "_fetch_capability_readiness", _fake)
    return seen


# --- aggregation and the per-instance unit ---------------------------------


def test_failed_capability_outranks_pending_and_carries_its_detail() -> None:
    verdict = aggregate_readiness(
        [
            {"capability_id": "a", "state": "pending"},
            {"capability_id": "b", "state": "failed", "detail": "boom"},
            {"capability_id": "c", "state": "ready"},
        ]
    )
    assert verdict == ReadinessVerdict(
        ready=False, capability_ids=("a", "b"), detail="boom"
    )
    assert aggregate_readiness([{"capability_id": "c", "state": "ready"}]).ready


@pytest.mark.asyncio
async def test_pending_verdict_suspends_and_ready_clears() -> None:
    record = _record_with_selection()
    store = _FakeAgentInstanceStore([record])

    reason = await reconcile_instance_readiness(
        instance=record, store=store, verdict=_FAILED
    )
    assert reason is SuspensionReason.CAPABILITY_PENDING
    assert record.suspension_reason == "capability_pending"
    assert record.suspension_detail == "Template unreadable."

    reason = await reconcile_instance_readiness(
        instance=record, store=store, verdict=_READY
    )
    assert reason is None
    assert record.suspension_reason is None
    assert record.suspension_detail is None


@pytest.mark.asyncio
async def test_other_reasons_outrank_pending() -> None:
    record = _record_with_selection()
    record.suspension_reason = SuspensionReason.CAPABILITY_CONFIG_INVALID.value
    store = _FakeAgentInstanceStore([record])

    for verdict in (_PENDING, _READY):
        await reconcile_instance_readiness(
            instance=record, store=store, verdict=verdict
        )
        assert record.suspension_reason == "capability_config_invalid"


@pytest.mark.asyncio
async def test_no_verdict_leaves_state_unchanged() -> None:
    record = _record_with_selection()
    record.suspension_reason = SuspensionReason.CAPABILITY_PENDING.value
    store = _FakeAgentInstanceStore([record])

    reason = await reconcile_instance_readiness(
        instance=record, store=store, verdict=None
    )
    assert reason is SuspensionReason.CAPABILITY_PENDING
    assert record.suspension_reason == "capability_pending"


# --- pod call --------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_sends_stored_slices_and_folds_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def _fake_post(self, url, *args, **kwargs):  # noqa: ANN001
        captured["url"] = str(url)
        captured["json"] = kwargs.get("json")
        return httpx.Response(
            200,
            json={"results": [{"capability_id": "demo_echo", "state": "pending"}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    record = _record_with_selection()

    verdict = await service._fetch_capability_readiness(
        client=httpx.AsyncClient(),
        base_url="http://runtime-a/pod/v1",
        instance=record,
        authorization=None,
    )

    assert verdict == ReadinessVerdict(ready=False, capability_ids=("demo_echo",))
    assert captured["url"].endswith("/agents/capabilities/readiness")
    assert captured["json"]["agent_instance_id"] == record.agent_instance_id
    assert captured["json"]["items"] == [
        {
            "capability_id": "demo_echo",
            "stored": record.tuning.capability_config["demo_echo"],
        }
    ]


@pytest.mark.asyncio
async def test_fetch_from_an_older_pod_reads_as_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_post(self, url, *args, **kwargs):  # noqa: ANN001
        return httpx.Response(404, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    verdict = await service._fetch_capability_readiness(
        client=httpx.AsyncClient(),
        base_url="http://runtime-a/pod/v1",
        instance=_record_with_selection(),
        authorization=None,
    )

    assert verdict == _READY


@pytest.mark.asyncio
async def test_fetch_error_gives_no_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_post(self, url, *args, **kwargs):  # noqa: ANN001
        return httpx.Response(503, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    verdict = await service._fetch_capability_readiness(
        client=httpx.AsyncClient(),
        base_url="http://runtime-a/pod/v1",
        instance=_record_with_selection(),
        authorization=None,
    )

    assert verdict is None


# --- save, re-check -------------------------------------------------


@pytest.mark.asyncio
async def test_save_does_not_clear_a_pending_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record_with_selection()
    record.suspension_reason = SuspensionReason.CAPABILITY_PENDING.value
    app, store = _setup(monkeypatch, records=[record])
    _fake_pod_validate(monkeypatch)
    seen = _fake_readiness(monkeypatch, _PENDING)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-1",
            json={"capability_ids": ["demo_echo"]},
            headers={"Authorization": "Bearer user-token"},
        )

    assert resp.status_code == 200
    assert resp.json()["suspension_reason"] == "capability_pending"
    assert store._records[0].suspension_reason == "capability_pending"
    assert seen == ["Bearer user-token"]


@pytest.mark.asyncio
async def test_recheck_exposes_failure_detail_then_clears_when_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = _setup(monkeypatch, records=[_record_with_selection()])
    url = "/control-plane/v1/teams/personal/agent-instances/instance-1/readiness-check"

    _fake_readiness(monkeypatch, _FAILED)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(url)
    assert resp.status_code == 200
    assert resp.json()["suspension_reason"] == "capability_pending"
    assert resp.json()["suspension_detail"] == "Template unreadable."

    _fake_readiness(monkeypatch, _READY)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(url)
    assert resp.status_code == 200
    assert "suspension_reason" not in resp.json()
    assert store._records[0].suspension_reason is None


@pytest.mark.asyncio
async def test_recheck_unknown_instance_is_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _ = _setup(monkeypatch, records=[])
    _fake_readiness(monkeypatch, _READY)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances/nope/readiness-check"
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_save_routing_params_carry_the_team_default_and_recommendation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _snapshot(team_id, deps):
        return "chat.team"

    monkeypatch.setattr(service, "resolve_execution_routing_snapshot", _snapshot)

    params = await service._capability_save_routing_params(
        object(),  # type: ignore[arg-type]
        "personal",  # type: ignore[arg-type]
        "rico",
    )

    assert params == {
        "template_agent_id": "rico",
        "chat_default_profile_id": "chat.team",
    }

    recommended = await service._capability_save_routing_params(
        object(),  # type: ignore[arg-type]
        "personal",  # type: ignore[arg-type]
        "rico",
        "chat.instance",
    )
    assert recommended["recommended_chat_profile_id"] == "chat.instance"


# --- lazy re-check on listing ------------------------------------------------

_LIST_URL = "/control-plane/v1/teams/personal/agent-instances"


def _pending_record(instance_id: str = "instance-1"):
    record = _record_with_selection()
    record.agent_instance_id = instance_id
    record.suspension_reason = SuspensionReason.CAPABILITY_PENDING.value
    return record


@pytest.mark.asyncio
async def test_listing_makes_an_agent_available_once_its_capability_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = _setup(monkeypatch, records=[_pending_record()])
    seen = _fake_readiness(monkeypatch, _READY)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(_LIST_URL, headers={"Authorization": "Bearer u"})

    assert resp.status_code == 200
    assert "suspension_reason" not in resp.json()[0]
    assert store._records[0].suspension_reason is None
    assert seen == ["Bearer u"]


@pytest.mark.asyncio
async def test_listing_leaves_state_unchanged_when_the_pod_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    import time

    app, store = _setup(monkeypatch, records=[_pending_record()])
    monkeypatch.setattr(service, "_LISTING_READINESS_TIMEOUT_S", 0.2)

    async def _slow_post(self, url, *args, **kwargs):  # noqa: ANN001
        await asyncio.sleep(5)
        raise AssertionError("the timeout should have fired")

    monkeypatch.setattr(httpx.AsyncClient, "post", _slow_post)

    started = time.monotonic()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(_LIST_URL)
    elapsed = time.monotonic() - started

    assert resp.status_code == 200
    assert resp.json()[0]["suspension_reason"] == "capability_pending"
    assert store._records[0].suspension_reason == "capability_pending"
    assert elapsed < 2.0


@pytest.mark.asyncio
async def test_listing_rechecks_at_most_ten_instances_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    import time

    records = [_pending_record(f"instance-{i}") for i in range(12)]
    app, _ = _setup(monkeypatch, records=records)
    calls: list[str] = []

    async def _fake(*, base_url: str, instance, authorization, timeout, **_: Any):
        calls.append(instance.agent_instance_id)
        await asyncio.sleep(0.3)
        return None

    monkeypatch.setattr(service, "_fetch_capability_readiness", _fake)

    started = time.monotonic()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(_LIST_URL)
    elapsed = time.monotonic() - started

    assert resp.status_code == 200
    assert len(resp.json()) == 12
    assert len(calls) == 10
    # Ten 0.3 s checks in parallel, not 3 s in sequence.
    assert elapsed < 1.5


# --- review fixes: conditional writes, save settlement, listing ---------------


class _CountingStore(_FakeAgentInstanceStore):
    def __init__(self, records) -> None:
        super().__init__(records)
        self.writes: list[str | None] = []

    async def set_suspension(self, *args: Any, **kwargs: Any):
        self.writes.append(kwargs.get("reason"))
        return await super().set_suspension(*args, **kwargs)


@pytest.mark.asyncio
async def test_ready_verdict_never_clears_a_reason_written_meanwhile() -> None:
    import copy

    stored = _record_with_selection()
    stored.suspension_reason = SuspensionReason.CAPABILITY_ACCESS_REVOKED.value
    store = _FakeAgentInstanceStore([stored])
    # Read before a revocation landed, during the slow pod call.
    seen = copy.copy(stored)
    seen.suspension_reason = SuspensionReason.CAPABILITY_PENDING.value

    reason = await reconcile_instance_readiness(
        instance=seen, store=store, verdict=_READY
    )

    assert reason is None
    assert stored.suspension_reason == "capability_access_revoked"


@pytest.mark.asyncio
async def test_agent_instance_store_suspension_write_is_compare_and_set(
    tmp_path,
) -> None:
    from control_plane_backend.agent_instances.store import AgentInstanceStore
    from control_plane_backend.models.agent_instance_models import AgentInstanceRow
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cas.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(AgentInstanceRow.metadata.create_all)
    store = AgentInstanceStore(engine=engine)
    record = await store.create(_record_with_selection())
    team_id = record.team_id
    instance_id = record.agent_instance_id
    before = (await store.get(instance_id)).updated_at  # type: ignore[union-attr]

    await store.set_suspension(
        instance_id, team_id, reason="capability_pending", expected_reason=None
    )
    # A stale "pending" read must not clear the revocation written since.
    await store.set_suspension(instance_id, team_id, reason="capability_access_revoked")
    after = await store.set_suspension(
        instance_id, team_id, reason=None, expected_reason="capability_pending"
    )

    assert after is not None
    assert after.suspension_reason == "capability_access_revoked"
    assert after.updated_at == before
    await engine.dispose()


@pytest.mark.asyncio
async def test_save_with_no_verdict_keeps_the_agent_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = _setup(monkeypatch, records=[_record_with_selection()])
    _fake_pod_validate(monkeypatch)
    _fake_readiness(monkeypatch, None)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-1",
            json={"capability_ids": ["demo_echo"]},
        )

    assert resp.status_code == 200
    assert resp.json()["suspension_reason"] == "capability_pending"
    assert store._records[0].suspension_reason == "capability_pending"
    assert store._records[0].suspension_detail is None


@pytest.mark.asyncio
async def test_save_moves_an_earlier_reason_to_pending_in_one_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record_with_selection()
    record.suspension_reason = SuspensionReason.CAPABILITY_CONFIG_INVALID.value
    app, _ = _setup(monkeypatch, records=[record])
    store = _CountingStore([record])
    from test_main import _patch_store

    _patch_store(monkeypatch, store)
    _fake_pod_validate(monkeypatch)
    _fake_readiness(monkeypatch, _PENDING)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-1",
            json={"capability_ids": ["demo_echo"]},
        )

    assert resp.status_code == 200
    assert store._records[0].suspension_reason == "capability_pending"
    # No clear-then-suspend: the agent never reads as available in between.
    assert store.writes == ["capability_pending"]


@pytest.mark.asyncio
async def test_save_answered_ready_clears_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record_with_selection()
    record.suspension_reason = SuspensionReason.CAPABILITY_PENDING.value
    app, store = _setup(monkeypatch, records=[record])
    _fake_pod_validate(monkeypatch)
    _fake_readiness(monkeypatch, _READY)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-1",
            json={"capability_ids": ["demo_echo"]},
        )

    assert resp.status_code == 200
    assert store._records[0].suspension_reason is None


@pytest.mark.asyncio
async def test_listing_skips_failed_preparations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed = _pending_record("failed")
    failed.suspension_detail = "Template unreadable."
    app, store = _setup(monkeypatch, records=[failed, _pending_record("pending")])
    calls: list[str] = []

    async def _fake(*, instance, **_: Any):
        calls.append(instance.agent_instance_id)
        return _READY

    monkeypatch.setattr(service, "_fetch_capability_readiness", _fake)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(_LIST_URL)

    assert resp.status_code == 200
    assert calls == ["pending"]
    assert store._records[0].suspension_detail == "Template unreadable."


@pytest.mark.asyncio
async def test_listing_rotates_over_the_cap_on_one_shared_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = [_pending_record(f"instance-{i}") for i in range(12)]
    app, _ = _setup(monkeypatch, records=records)
    calls: list[str] = []
    clients: set[int] = set()

    async def _fake(*, client, instance, **_: Any):
        calls.append(instance.agent_instance_id)
        clients.add(id(client))
        return None

    class _LastFirst:
        def sample(self, population, k):
            return list(reversed(population))[:k]

    monkeypatch.setattr(service, "_fetch_capability_readiness", _fake)
    monkeypatch.setattr(service, "_readiness_sampler", _LastFirst())

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(_LIST_URL)
        await client.get(_LIST_URL)

    assert resp.status_code == 200
    assert "instance-11" in calls and "instance-0" not in calls
    assert len(clients) == 1

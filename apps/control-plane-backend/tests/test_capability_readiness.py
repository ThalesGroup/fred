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
from the pod's `readiness` verdicts after a save, in the sweep and on re-check."""

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
    _product_deps,
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

    async def _fake(*, base_url: str, instance, authorization, timeout=5.0):
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
        base_url="http://runtime-a/pod/v1", instance=record, authorization=None
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
async def test_fetch_from_an_older_pod_gives_no_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_post(self, url, *args, **kwargs):  # noqa: ANN001
        return httpx.Response(404, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    verdict = await service._fetch_capability_readiness(
        base_url="http://runtime-a/pod/v1",
        instance=_record_with_selection(),
        authorization=None,
    )

    assert verdict is None


# --- save, re-check, sweep -------------------------------------------------


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
async def test_sweep_sets_pending_after_availability_and_config_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = _setup(monkeypatch, records=[_record_with_selection()])

    async def _available(_deps):
        return {"runtime-a": frozenset({"demo_echo"})}

    monkeypatch.setattr(service, "_available_capability_ids_by_source", _available)
    _fake_pod_validate(monkeypatch)
    _fake_readiness(monkeypatch, _PENDING)

    summary = await service.run_capability_reconciliation_sweep(_product_deps(app))

    assert summary.newly_suspended == 1
    assert summary.suspended_reasons == {"capability_pending": 1}
    assert store._records[0].suspension_reason == "capability_pending"


@pytest.mark.asyncio
async def test_save_routing_params_narrow_the_team_policy_to_this_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _snapshot(team_id, deps):
        return "chat.team", {"rico": "chat.rico", "other": "chat.other"}

    monkeypatch.setattr(service, "resolve_execution_routing_snapshot", _snapshot)

    params = await service._capability_save_routing_params(
        object(),  # type: ignore[arg-type]
        "personal",  # type: ignore[arg-type]
        "rico",
    )

    assert params == {
        "template_agent_id": "rico",
        "chat_default_profile_id": "chat.team",
        "agent_profile_overrides": '{"rico": "chat.rico"}',
    }


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

    async def _fake(*, base_url: str, instance, authorization, timeout):
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

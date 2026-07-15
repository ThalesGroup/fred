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

"""
Agent suspension lifecycle for broken/revoked capabilities
(#1975, RFC AGENT-CAPABILITY-RFC.md §3.9).

Covers:
- `reconcile_instance_suspension`: an unavailable selected capability suspends
  the instance (`capability_unavailable`); the #1980 ReBAC entry point suspends
  with `capability_access_revoked`; ids in `tolerated_ids` (known-but-disabled
  catalog MCP servers, #1988) are never suspended; availability suspension
  clears when the capability returns; a config-invalid suspension is NOT cleared
  by availability reconcile
- `reconcile_instance_config_health`: a stored slice that no longer validates
  through the pod suspends `capability_config_invalid`; a healthy slice is a
  no-op
- `run_capability_reconciliation_sweep`: the proactive sweep suspends affected
  instances (before anyone hits an error) and leaves healthy ones alone
- `prepare_execution`: refuses a suspended instance loudly (409)
- save clears suspension: a successful capability re-save (untick + save) clears
  the suspension — the single clearing mechanism
- the suspension reason is exposed on `ManagedAgentInstanceSummary`
"""

from __future__ import annotations

import control_plane_backend.product.service as service
import pytest
from control_plane_backend.agent_instances.suspension import (
    SliceInvalid,
    SuspensionReason,
    reconcile_instance_config_health,
    reconcile_instance_suspension,
)
from httpx import ASGITransport, AsyncClient
from test_capability_selection_1974 import (
    _fake_pod_validate,
    _record_with_selection,
    _setup,
)
from test_main import _FakeAgentInstanceStore, _make_record


@pytest.fixture(autouse=True)
def _use_test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")


def _suspended_record(reason: SuspensionReason):
    record = _record_with_selection()
    record.suspension_reason = reason.value
    return record


# ---------------------------------------------------------------------------
# reconcile_instance_suspension — availability (the #1980 entry point)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_capability_suspends_unavailable() -> None:
    record = _record_with_selection()  # selects "demo_echo"
    store = _FakeAgentInstanceStore([record])

    reason = await reconcile_instance_suspension(
        instance=record,
        store=store,
        available_capability_ids=frozenset(),  # pod no longer advertises it
    )

    assert reason is SuspensionReason.CAPABILITY_UNAVAILABLE
    assert record.suspension_reason == "capability_unavailable"


@pytest.mark.asyncio
async def test_revoked_reason_is_the_rebac_entry_point() -> None:
    # #1980 calls the same entry point with the access-revoked reason.
    record = _record_with_selection()
    store = _FakeAgentInstanceStore([record])

    reason = await reconcile_instance_suspension(
        instance=record,
        store=store,
        available_capability_ids=frozenset(),
        revoked_reason=SuspensionReason.CAPABILITY_ACCESS_REVOKED,
    )

    assert reason is SuspensionReason.CAPABILITY_ACCESS_REVOKED
    assert record.suspension_reason == "capability_access_revoked"


@pytest.mark.asyncio
async def test_tolerated_id_is_never_unavailable() -> None:
    # #1988: a selected id in `tolerated_ids` (a known-but-disabled catalog MCP
    # server, supplied by the availability sweep) is never a suspension even
    # when absent from the advertised set.
    record = _make_record()
    record.tuning = record.tuning.model_copy(
        update={"selected_capability_ids": ["some_server"]}
    )
    store = _FakeAgentInstanceStore([record])

    reason = await reconcile_instance_suspension(
        instance=record,
        store=store,
        available_capability_ids=frozenset(),  # server absent from templates
        tolerated_ids=frozenset({"some_server"}),  # but disabled in MCP catalog
    )

    assert reason is None
    assert record.suspension_reason is None


@pytest.mark.asyncio
async def test_revocation_path_suspends_revoked_mcp_capability() -> None:
    # #1988: the revocation path passes NO tolerated ids, so revoking an
    # MCP-backed capability suspends its dependents like any other capability.
    record = _make_record()
    record.tuning = record.tuning.model_copy(
        update={"selected_capability_ids": ["market_data"]}
    )
    store = _FakeAgentInstanceStore([record])

    reason = await reconcile_instance_suspension(
        instance=record,
        store=store,
        available_capability_ids=frozenset(),  # grant revoked
        revoked_reason=SuspensionReason.CAPABILITY_ACCESS_REVOKED,
    )

    assert reason is SuspensionReason.CAPABILITY_ACCESS_REVOKED
    assert record.suspension_reason == "capability_access_revoked"


@pytest.mark.asyncio
async def test_availability_suspension_clears_when_capability_returns() -> None:
    record = _suspended_record(SuspensionReason.CAPABILITY_UNAVAILABLE)
    store = _FakeAgentInstanceStore([record])

    reason = await reconcile_instance_suspension(
        instance=record,
        store=store,
        available_capability_ids=frozenset({"demo_echo"}),  # back in catalog
    )

    assert reason is None
    assert record.suspension_reason is None


@pytest.mark.asyncio
async def test_config_invalid_is_not_cleared_by_availability_reconcile() -> None:
    record = _suspended_record(SuspensionReason.CAPABILITY_CONFIG_INVALID)
    store = _FakeAgentInstanceStore([record])

    reason = await reconcile_instance_suspension(
        instance=record,
        store=store,
        available_capability_ids=frozenset({"demo_echo"}),
    )

    # Availability is fine, but config-invalid is only cleared by a save.
    assert reason is None
    assert record.suspension_reason == "capability_config_invalid"


# ---------------------------------------------------------------------------
# reconcile_instance_config_health — config-invalid / upgrade_config failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_stored_slice_suspends_config_invalid() -> None:
    record = _record_with_selection()
    store = _FakeAgentInstanceStore([record])

    async def _validate(capability_id: str, config: dict) -> None:
        raise SliceInvalid(
            capability_id,
            "parameters for capability demo_echo are no longer valid — "
            "reset them and re-save the agent.",
        )

    reason = await reconcile_instance_config_health(
        instance=record, store=store, validate_slice=_validate
    )

    assert reason is SuspensionReason.CAPABILITY_CONFIG_INVALID
    assert record.suspension_reason == "capability_config_invalid"


@pytest.mark.asyncio
async def test_healthy_slice_is_a_noop() -> None:
    record = _record_with_selection()
    store = _FakeAgentInstanceStore([record])

    async def _validate(capability_id: str, config: dict) -> None:
        return None

    reason = await reconcile_instance_config_health(
        instance=record, store=store, validate_slice=_validate
    )

    assert reason is None
    assert record.suspension_reason is None


# ---------------------------------------------------------------------------
# run_capability_reconciliation_sweep — the proactive mechanism
# ---------------------------------------------------------------------------


def _patch_available(monkeypatch: pytest.MonkeyPatch, ids: set[str]) -> None:
    async def _fake(_deps):
        return {"runtime-a": frozenset(ids)}

    monkeypatch.setattr(service, "_available_capability_ids_by_source", _fake)


@pytest.mark.asyncio
async def test_sweep_suspends_instance_whose_capability_vanished(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = _setup(monkeypatch, records=[_record_with_selection()])
    _patch_available(monkeypatch, ids=set())  # demo_echo gone
    deps = _product_deps(app)

    summary = await service.run_capability_reconciliation_sweep(deps)

    assert summary.newly_suspended == 1
    assert store._records[0].suspension_reason == "capability_unavailable"


@pytest.mark.asyncio
async def test_sweep_leaves_healthy_instance_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = _setup(monkeypatch, records=[_record_with_selection()])
    _patch_available(monkeypatch, ids={"demo_echo"})
    # Config health round-trip returns a valid envelope.
    _fake_pod_validate(monkeypatch)
    deps = _product_deps(app)

    summary = await service.run_capability_reconciliation_sweep(deps)

    assert summary.newly_suspended == 0
    assert store._records[0].suspension_reason is None


@pytest.mark.asyncio
async def test_sweep_detects_config_invalid_via_pod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = _setup(monkeypatch, records=[_record_with_selection()])
    _patch_available(monkeypatch, ids={"demo_echo"})

    async def _fail(**_kwargs):
        raise service.EnrollmentError(
            "parameters for capability demo_echo are no longer valid — "
            "reset them and re-save the agent.",
            http_status=422,
        )

    monkeypatch.setattr(service, "_validate_capability_config_via_pod", _fail)
    deps = _product_deps(app)

    summary = await service.run_capability_reconciliation_sweep(deps)

    assert summary.newly_suspended == 1
    assert store._records[0].suspension_reason == "capability_config_invalid"


# ---------------------------------------------------------------------------
# prepare_execution guard + save clears suspension (HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_execution_refuses_suspended_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _ = _setup(
        monkeypatch,
        records=[_suspended_record(SuspensionReason.CAPABILITY_UNAVAILABLE)],
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances/"
            "instance-1/prepare-execution",
        )
    assert resp.status_code == 409
    assert "suspended" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_successful_capability_save_clears_suspension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _suspended_record(SuspensionReason.CAPABILITY_CONFIG_INVALID)
    app, store = _setup(monkeypatch, records=[record])
    _fake_pod_validate(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Untick the broken capability and re-save (RFC §3.9 fix path).
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-1",
            json={"capability_ids": []},
        )
    assert resp.status_code == 200
    # response_model_exclude_none omits the field once cleared.
    assert resp.json().get("suspension_reason") is None
    assert store._records[0].suspension_reason is None


@pytest.mark.asyncio
async def test_listing_exposes_suspension_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _ = _setup(
        monkeypatch,
        records=[_suspended_record(SuspensionReason.CAPABILITY_UNAVAILABLE)],
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/teams/personal/agent-instances")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["suspension_reason"] == "capability_unavailable"


def _product_deps(app):
    """Build the request-scoped product dependencies from the test app."""

    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )
    from control_plane_backend.product.dependencies import (
        build_product_service_dependencies,
    )

    container = get_application_container_from_app(app)
    return build_product_service_dependencies(container)

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
Control-plane capability selection (#1974, RFC AGENT-CAPABILITY-RFC.md §3.8).

Covers:
- catalog aggregation: `available_capabilities` flows from the pod template
  advertisement into `AgentTemplateSummary`
- agent save: `capability_ids` validated against the pod-advertised catalog
  (unknown -> typed 422); each selected capability's config round-trips to the
  pod and the returned {"schema_version", "config"} envelope is persisted
  VERBATIM in tuning_json; pod-side 422s propagate with their wording
- agent update: capability writes re-validate every active slice through the
  pod, prune envelopes of deselected capabilities, and `null` config resets
  the selected capabilities to their defaults
"""

# pyright: reportArgumentType=false
# ^ the CAPAB-01 migration tests below pass a lightweight SimpleNamespace
#   fake in place of ProductServiceDependencies on purpose (same convention as
#   test_capability_enablement_1980.py).
from __future__ import annotations

from typing import Any

import control_plane_backend.product.service as service
import httpx
import pytest
from control_plane_backend.app.dependencies import get_application_container_from_app
from control_plane_backend.config.models import (
    ManagedAgentTuning,
    RuntimeCatalogSourceConfig,
)
from control_plane_backend.main import create_app
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.models import FieldSpec, TeamScopePolicy
from httpx import ASGITransport, AsyncClient
from test_capability_enablement_1980 import _FilterRebac
from test_main import (
    _PERSONAL_TEAM_ID,
    _fake_get_team_by_id,
    _FakeAgentInstanceStore,
    _make_record,
    _patch_store,
)


@pytest.fixture(autouse=True)
def _use_test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")


_DEMO_ENTRY = CapabilityCatalogEntry(
    id="demo_echo",
    version="0.1.0",
    name="capability.demo_echo.name",
    description="capability.demo_echo.description",
    icon="graphic_eq",
    config_fields=[
        FieldSpec(key="uppercase", type="boolean", title="Uppercase", default=False)
    ],
)

_PROBE_ENTRY = CapabilityCatalogEntry(
    id="probe_echo",
    version="1.0.0",
    name="capability.probe_echo.name",
    description="capability.probe_echo.description",
    icon="hub",
)


def _template_payload(
    default_capability_ids: list[str] | None = None,
) -> service._RuntimeTemplatePayload:
    return service._RuntimeTemplatePayload(
        template_agent_id="rags.sample.echo",
        title="Echo Agent",
        description="Echo template description",
        kind="assistant",
        default_tuning=ManagedAgentTuning(
            role="Echo Agent",
            description="Echo template description",
        ),
        available_capabilities=[_DEMO_ENTRY, _PROBE_ENTRY],
        default_capability_ids=default_capability_ids,
    )


def _wire_runtime_source(app) -> None:
    container = get_application_container_from_app(app)
    container.configuration.platform.runtime_catalog_sources = [
        RuntimeCatalogSourceConfig(
            runtime_id="runtime-a",
            base_url="http://runtime-a/pod/v1",
            enabled=True,
            ingress_prefix="/runtime/runtime-a",
        )
    ]


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    records=None,
    default_capability_ids: list[str] | None = None,
):
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakeAgentInstanceStore(records or [])
    app = create_app()
    _patch_store(monkeypatch, store)
    _wire_runtime_source(app)

    async def _fake_fetch_runtime_templates(
        _base_url: str, include_non_public: bool = False
    ):
        return [_template_payload(default_capability_ids=default_capability_ids)]

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch_runtime_templates,
    )
    return app, store


class _FilterRebacForEnrollment(_FilterRebac):
    """`_FilterRebac` plus the platform-admin check `enroll_agent_instance`
    makes to resolve non-public-template visibility (service.py:1571-1575) —
    not exercised by `_FilterRebac`'s own test suite, which never enrolls."""

    async def has_user_permission(self, user, permission, resource_id) -> bool:
        return False


def _wire_rebac(monkeypatch: pytest.MonkeyPatch, usable_by_team) -> None:
    """
    Inject a `_FilterRebac` (team -> usable capability ids, or `None` for
    ReBAC-disabled) into every request's `team_dependencies.rebac`. Must be
    called BEFORE `_setup`/`create_app()` — the engine is resolved fresh per
    request via `ApplicationContext.get_rebac_engine`, not a persistent
    container attribute.
    """

    fake = _FilterRebacForEnrollment(usable_by_team)
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_rebac_engine",
        lambda self: fake,
    )


def _product_deps(app):
    """Build the request-scoped product dependencies from the test app."""

    from control_plane_backend.product.dependencies import (
        build_product_service_dependencies,
    )

    container = get_application_container_from_app(app)
    return build_product_service_dependencies(container)


def _fake_pod_validate(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace the pod round-trip; records calls, echoes a derived envelope."""

    calls: list[dict[str, Any]] = []

    async def _fake(
        *,
        base_url: str,
        capability_id: str,
        config_values: dict[str, Any],
        team_id,
        agent_instance_id,
        authorization,
    ) -> dict[str, Any]:
        calls.append(
            {
                "base_url": base_url,
                "capability_id": capability_id,
                "config_values": config_values,
                "team_id": str(team_id),
                "agent_instance_id": agent_instance_id,
                "authorization": authorization,
            }
        )
        # A pod may ENRICH the stored config (RFC §3.2) — the envelope must be
        # persisted verbatim, derived field included.
        return {
            "schema_version": "0.1.0",
            "config": {**config_values, "derived_marker": f"pod:{capability_id}"},
        }

    monkeypatch.setattr(
        "control_plane_backend.product.service._validate_capability_config_via_pod",
        _fake,
    )
    return calls


# ---------------------------------------------------------------------------
# Catalog aggregation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_templates_expose_pod_capability_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _store = _setup(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/control-plane/v1/teams/{_PERSONAL_TEAM_ID}/agent-templates"
        )
    assert resp.status_code == 200
    entries = resp.json()[0]["available_capabilities"]
    assert [e["id"] for e in entries] == ["demo_echo", "probe_echo"]
    assert entries[0]["config_fields"][0]["key"] == "uppercase"
    assert entries[0]["version"] == "0.1.0"


# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enroll_persists_pod_validated_envelopes_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = _setup(monkeypatch)
    calls = _fake_pod_validate(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances",
            headers={"Authorization": "Bearer user-token"},
            json={
                "template_id": "runtime-a:rags.sample.echo",
                "display_name": "Echo with capabilities",
                "capability_ids": ["demo_echo"],
                "capability_config_values": {"demo_echo": {"uppercase": True}},
            },
        )
    assert resp.status_code == 201
    payload = resp.json()
    assert payload["selected_capability_ids"] == ["demo_echo"]
    assert payload["capability_config"] == {
        "demo_echo": {
            "schema_version": "0.1.0",
            "config": {"uppercase": True, "derived_marker": "pod:demo_echo"},
        }
    }
    tuning = store._records[0].tuning
    assert tuning.selected_capability_ids == ["demo_echo"]
    # Persisted VERBATIM, pod-derived field included (RFC §3.8).
    assert tuning.capability_config["demo_echo"]["config"]["derived_marker"] == (
        "pod:demo_echo"
    )
    assert calls == [
        {
            "base_url": "http://runtime-a/pod/v1",
            "capability_id": "demo_echo",
            "config_values": {"uppercase": True},
            "team_id": "personal",
            "agent_instance_id": store._records[0].agent_instance_id,
            "authorization": "Bearer user-token",
        }
    ]


@pytest.mark.asyncio
async def test_enroll_unknown_capability_id_is_typed_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = _setup(monkeypatch)
    _fake_pod_validate(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances",
            json={
                "template_id": "runtime-a:rags.sample.echo",
                "display_name": "Bad selection",
                "capability_ids": ["ghost"],
            },
        )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "ghost" in detail
    assert "capability" in detail.lower()
    assert store._records == []


@pytest.mark.asyncio
async def test_enroll_config_for_unselected_capability_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = _setup(monkeypatch)
    calls = _fake_pod_validate(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances",
            json={
                "template_id": "runtime-a:rags.sample.echo",
                "display_name": "Selective",
                "capability_ids": ["demo_echo"],
                "capability_config_values": {
                    "demo_echo": {"uppercase": False},
                    "probe_echo": {"whatever": 1},
                },
            },
        )
    assert resp.status_code == 201
    assert [c["capability_id"] for c in calls] == ["demo_echo"]
    assert set(store._records[0].tuning.capability_config) == {"demo_echo"}


@pytest.mark.asyncio
async def test_enroll_propagates_pod_422_wording(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = _setup(monkeypatch)

    pod_detail = "Asset slot 'template': expected exactly 1 file(s), got 0."
    original_post = httpx.AsyncClient.post

    async def _pod_422_post(self, url, *args, **kwargs):  # noqa: ANN001
        if "validate-config" in str(url):
            request = httpx.Request("POST", url)
            return httpx.Response(422, json={"detail": pod_detail}, request=request)
        return await original_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", _pod_422_post)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances",
            json={
                "template_id": "runtime-a:rags.sample.echo",
                "display_name": "Missing asset",
                "capability_ids": ["demo_echo"],
            },
        )
    assert resp.status_code == 422
    assert resp.json()["detail"] == pod_detail
    assert store._records == []


# ---------------------------------------------------------------------------
# None-selection materialization (CAPAB-01 / #1980 bypass fix, RFC §8.1)
#
# Previously, `capability_ids` omitted at enroll time left
# `selected_capability_ids = None` persisted with ZERO ReBAC check, and the
# runtime pod then activated every one of the template's `default_mcp_servers`
# regardless of team grants. These tests cover the fix: the effective
# selection is always resolved and always persisted as an explicit list.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enroll_no_selection_materializes_only_granted_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_rebac(
        monkeypatch,
        {"personal": {"demo_echo", "runtime-a__rags.sample.echo"}},
    )
    app, store = _setup(monkeypatch, default_capability_ids=["demo_echo", "probe_echo"])
    calls = _fake_pod_validate(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances",
            json={
                "template_id": "runtime-a:rags.sample.echo",
                "display_name": "Default selection",
            },
        )
    assert resp.status_code == 201
    tuning = store._records[0].tuning
    # Materialized to an EXPLICIT list — never left `None` — and narrowed to
    # only the capability this team is actually granted.
    assert tuning.selected_capability_ids == ["demo_echo"]
    assert set(tuning.capability_config) == {"demo_echo"}
    assert [c["capability_id"] for c in calls] == ["demo_echo"]


@pytest.mark.asyncio
async def test_enroll_no_selection_with_no_grants_materializes_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Granted the TEMPLATE itself (CAPAB-01, RFC §8.6) but none of its default
    # tool capabilities — isolates "no capability grants" from "no template
    # grant" (covered separately by test_enroll_hidden_template_is_404_not_500).
    _wire_rebac(monkeypatch, {"personal": {"runtime-a__rags.sample.echo"}})
    app, store = _setup(monkeypatch, default_capability_ids=["demo_echo", "probe_echo"])
    calls = _fake_pod_validate(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances",
            json={
                "template_id": "runtime-a:rags.sample.echo",
                "display_name": "No grants",
            },
        )
    assert resp.status_code == 201
    tuning = store._records[0].tuning
    # This is the exact bypass the fix closes: a team with no grant for the
    # template's admin-gated default capabilities used to get `None`
    # persisted (skipping every ReBAC check), and the runtime pod activated
    # every default MCP server anyway. Now it materializes to an empty list.
    assert tuning.selected_capability_ids == []
    assert tuning.capability_config == {}
    assert calls == []


@pytest.mark.asyncio
async def test_enroll_hidden_template_is_404_not_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    CAPAB-01 (RFC §8.6) defense in depth: a team not granted the template
    itself gets 404 — same anti-guessing posture as the non-public-template
    check (never leak "the template exists but you can't use it").
    """
    _wire_rebac(monkeypatch, {"personal": {"demo_echo", "probe_echo"}})
    app, store = _setup(monkeypatch, default_capability_ids=["demo_echo", "probe_echo"])
    _fake_pod_validate(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances",
            json={
                "template_id": "runtime-a:rags.sample.echo",
                "display_name": "Should not exist for this team",
            },
        )
    assert resp.status_code == 404
    assert store._records == []


@pytest.mark.asyncio
async def test_enroll_no_selection_with_rebac_disabled_takes_all_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_rebac(monkeypatch, None)  # ReBAC disabled -> no scoping (RFC §8.1)
    app, store = _setup(monkeypatch, default_capability_ids=["demo_echo", "probe_echo"])
    _fake_pod_validate(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances",
            json={
                "template_id": "runtime-a:rags.sample.echo",
                "display_name": "ReBAC disabled",
            },
        )
    assert resp.status_code == 201
    assert store._records[0].tuning.selected_capability_ids == [
        "demo_echo",
        "probe_echo",
    ]


@pytest.mark.asyncio
async def test_enroll_explicit_selection_denied_by_rebac_is_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Template itself granted (else this would 404 before ever reaching the
    # capability-selection check) but not the explicitly-requested capability.
    _wire_rebac(monkeypatch, {"personal": {"runtime-a__rags.sample.echo"}})
    app, store = _setup(monkeypatch)
    _fake_pod_validate(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances",
            json={
                "template_id": "runtime-a:rags.sample.echo",
                "display_name": "Deliberate but denied",
                "capability_ids": ["demo_echo"],
            },
        )
    assert resp.status_code == 403
    assert "CAPAB-01" in resp.json()["detail"]
    assert store._records == []


@pytest.mark.asyncio
async def test_update_capability_config_only_materializes_still_none_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Covers `update_agent_instance`'s narrower gap: a client sends
    `capability_config_values` without `capability_ids` on an instance still
    holding a legacy `selected_capability_ids = None`. Before the fix, this
    reached `_apply_capability_selection(selected_ids=None)` and skipped the
    ReBAC check the same way enroll did.
    """
    record = _make_record()
    assert record.tuning.selected_capability_ids is None
    _wire_rebac(monkeypatch, {"personal": {"demo_echo"}})
    app, store = _setup(
        monkeypatch,
        records=[record],
        default_capability_ids=["demo_echo", "probe_echo"],
    )
    _fake_pod_validate(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-1",
            json={"capability_config_values": {"demo_echo": {"uppercase": True}}},
        )
    assert resp.status_code == 200
    tuning = store._records[0].tuning
    assert tuning.selected_capability_ids == ["demo_echo"]


@pytest.mark.asyncio
async def test_materialization_sweep_backfills_legacy_none_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    `materialize_default_capability_selections` is the required backfill
    companion to the code fix: instances persisted BEFORE this change still
    hold `selected_capability_ids = None` and stay exploitable until swept.
    """
    record = _make_record()
    assert record.tuning.selected_capability_ids is None
    _wire_rebac(monkeypatch, {"personal": {"demo_echo"}})
    app, store = _setup(
        monkeypatch,
        records=[record],
        default_capability_ids=["demo_echo", "probe_echo"],
    )
    deps = _product_deps(app)

    summary = await service.materialize_default_capability_selections(deps)

    assert summary.checked == 1
    assert summary.materialized == 1
    assert store._records[0].tuning.selected_capability_ids == ["demo_echo"]


@pytest.mark.asyncio
async def test_materialization_sweep_dry_run_does_not_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _make_record()
    _wire_rebac(monkeypatch, {"personal": {"demo_echo"}})
    app, store = _setup(
        monkeypatch,
        records=[record],
        default_capability_ids=["demo_echo"],
    )
    deps = _product_deps(app)

    summary = await service.materialize_default_capability_selections(
        deps, dry_run=True
    )

    assert summary.materialized == 1
    assert store._records[0].tuning.selected_capability_ids is None


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def _record_with_selection():
    record = _make_record()
    record.tuning = record.tuning.model_copy(
        update={
            "selected_capability_ids": ["demo_echo"],
            "capability_config": {
                "demo_echo": {
                    "schema_version": "0.1.0",
                    "config": {"uppercase": True, "derived_marker": "pod:demo_echo"},
                }
            },
        }
    )
    return record


@pytest.mark.asyncio
async def test_update_selection_revalidates_and_prunes_deselected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = _setup(monkeypatch, records=[_record_with_selection()])
    calls = _fake_pod_validate(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-1",
            json={"capability_ids": ["probe_echo"]},
        )
    assert resp.status_code == 200
    tuning = store._records[0].tuning
    assert tuning.selected_capability_ids == ["probe_echo"]
    # demo_echo envelope pruned; probe_echo freshly validated with defaults.
    assert set(tuning.capability_config) == {"probe_echo"}
    assert [c["capability_id"] for c in calls] == ["probe_echo"]
    assert calls[0]["config_values"] == {}


@pytest.mark.asyncio
async def test_update_reuses_stored_config_when_values_not_submitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = _setup(monkeypatch, records=[_record_with_selection()])
    calls = _fake_pod_validate(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-1",
            json={"capability_ids": ["demo_echo"]},
        )
    assert resp.status_code == 200
    # The stored config was round-tripped again (a successful save is what
    # clears a config-invalid state, RFC §3.9).
    assert calls[0]["config_values"] == {
        "uppercase": True,
        "derived_marker": "pod:demo_echo",
    }
    assert (
        store._records[0].tuning.capability_config["demo_echo"]["config"]["uppercase"]
        is True
    )


@pytest.mark.asyncio
async def test_update_null_config_resets_selected_to_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = _setup(monkeypatch, records=[_record_with_selection()])
    calls = _fake_pod_validate(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-1",
            json={"capability_config_values": None},
        )
    assert resp.status_code == 200
    assert calls[0]["config_values"] == {}
    stored = store._records[0].tuning.capability_config["demo_echo"]["config"]
    assert "uppercase" not in stored


@pytest.mark.asyncio
async def test_update_unknown_capability_id_is_typed_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = _setup(monkeypatch, records=[_record_with_selection()])
    _fake_pod_validate(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-1",
            json={"capability_ids": ["ghost"]},
        )
    assert resp.status_code == 422
    assert "ghost" in resp.json()["detail"]
    # stored selection untouched
    assert store._records[0].tuning.selected_capability_ids == ["demo_echo"]


# ---------------------------------------------------------------------------
# Agent templates as capabilities (CAPAB-01, RFC §8.6)
# ---------------------------------------------------------------------------


def test_template_capability_id_is_colon_free() -> None:
    cap_id = service.template_capability_id("runtime-a", "rags.sample.echo")
    assert cap_id == "runtime-a__rags.sample.echo"
    assert ":" not in cap_id


@pytest.mark.asyncio
async def test_agent_projection_always_hardcodes_admin_gated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Guard test (cross-review correction 1): `AgentDefinition` has no
    `team_scope` field at all — a template author cannot declare
    `DEFAULT_ON`, so there is nothing to scan (unlike `kind="tool"` static
    manifests, guarded separately). The projection function itself is the
    only place this could vary; assert directly that it never does.
    """

    async def _fake_fetch(base_url: str, include_non_public: bool = False):
        return [
            _template_payload(default_capability_ids=["demo_echo"]),
        ]

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch,
    )
    entries = await service._agent_capabilities_for_source(
        "http://runtime-a/pod/v1", "runtime-a"
    )
    assert entries is not None and len(entries) == 1
    assert entries[0].kind == "agent"
    assert entries[0].team_scope == TeamScopePolicy.ADMIN_GATED
    assert entries[0].id == "runtime-a__rags.sample.echo"


@pytest.mark.asyncio
async def test_agent_projection_never_requests_non_public_templates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Regression (capabilities audit, 2026-07-18): `_agent_capabilities_for_source`
    used to call `_fetch_runtime_templates(..., include_non_public=True)`, so an
    internal/hidden template (`AgentDefinition.public=False`, e.g. the self-test
    harness agent) was projected into the admin capabilities catalog as a normal
    `kind="agent"` entry. AGENT-VISIBILITY-RFC hides those from the default
    catalog for a reason — no team can knowingly select them, so they have no
    business appearing as a gateable capability. Assert the call never opts in.
    """

    seen: dict[str, bool] = {}

    async def _fake_fetch(base_url: str, include_non_public: bool = False):
        seen["include_non_public"] = include_non_public
        return [_template_payload(default_capability_ids=["demo_echo"])]

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch,
    )
    await service._agent_capabilities_for_source("http://runtime-a/pod/v1", "runtime-a")
    assert seen["include_non_public"] is False


@pytest.mark.asyncio
async def test_agent_projection_returns_none_when_pod_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_fetch(base_url: str, include_non_public: bool = False):
        raise ConnectionError("pod down")

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch,
    )
    entries = await service._agent_capabilities_for_source(
        "http://runtime-a/pod/v1", "runtime-a"
    )
    assert entries is None


@pytest.mark.asyncio
async def test_list_agent_templates_hides_template_team_is_not_granted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_rebac(monkeypatch, {"personal": set()})
    app, _store = _setup(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/teams/personal/agent-templates")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_agent_templates_shows_template_when_granted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_rebac(monkeypatch, {"personal": {"runtime-a__rags.sample.echo"}})
    app, _store = _setup(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/teams/personal/agent-templates")
    assert resp.status_code == 200
    assert [t["template_id"] for t in resp.json()] == ["runtime-a:rags.sample.echo"]


class _FakeTemplateGrantRebac:
    """
    Combines the two interfaces `grant_existing_teams_served_templates` needs:
    `lookup_resources`/`has_permission` (read side, `usable_capability_ids`)
    seeded from `already_granted`, and `add_relation`/`delete_relation` (write
    side, `enable_capability_for_team`) — records every `enabled` tuple write
    for assertions, ignores the rest (anchor, settings-related opt-out clear).
    """

    def __init__(self, already_granted: dict[str, set[str]] | None = None) -> None:
        self.already_granted = already_granted or {}
        self.enabled_writes: list[tuple[str, str]] = []

    async def lookup_resources(
        self, subject, permission, resource_type, *, contextual_relations=None
    ):
        from fred_core.security.rebac.rebac_engine import RebacReference

        team_id = subject.id
        return [
            RebacReference(type=resource_type, id=cap_id)
            for cap_id in self.already_granted.get(team_id, set())
        ]

    async def has_permission(
        self, subject, permission, resource, *, contextual_relations=None
    ) -> bool:
        return resource.id in self.already_granted.get(subject.id, set())

    async def add_relation(self, relation) -> str | None:
        if relation.relation.value == "enabled":
            self.enabled_writes.append((relation.subject.id, relation.resource.id))
        return None

    async def delete_relation(self, relation) -> str | None:
        return None


class _FakeTeamMetadataStoreForMigration:
    def __init__(self, team_ids: list[str]) -> None:
        from types import SimpleNamespace

        self._teams = [SimpleNamespace(id=tid) for tid in team_ids]

    async def list_all(self):
        return self._teams


@pytest.mark.asyncio
async def test_grant_existing_teams_served_templates_migration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from control_plane_backend.capabilities.settings_store import (
        TeamCapabilitySettings,
    )

    async def _fake_fetch(base_url: str, include_non_public: bool = False):
        return [_template_payload()]

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch,
    )

    class _FakeSettings:
        async def upsert(self, *, team_id, capability_id, settings, updated_by):
            return TeamCapabilitySettings(
                team_id=team_id,
                capability_id=capability_id,
                settings=dict(settings),
                updated_by=updated_by,
                updated_at=None,
            )

    rebac = _FakeTemplateGrantRebac(
        already_granted={"team-already-granted": {"runtime-a__rags.sample.echo"}}
    )
    deps = SimpleNamespace(
        team_dependencies=SimpleNamespace(
            rebac=rebac,
            get_team_metadata_store=lambda: _FakeTeamMetadataStoreForMigration(
                ["team-already-granted", "team-needs-grant"]
            ),
        ),
        get_team_capability_settings_store=lambda: _FakeSettings(),
        configuration=SimpleNamespace(
            platform=SimpleNamespace(
                runtime_catalog_sources=[
                    RuntimeCatalogSourceConfig(
                        runtime_id="runtime-a",
                        base_url="http://runtime-a/pod/v1",
                        enabled=True,
                    )
                ]
            )
        ),
    )

    summary = await service.grant_existing_teams_served_templates(deps)

    assert summary.teams_checked == 2
    assert summary.templates_checked == 1
    assert summary.already_granted == 1
    assert summary.grants_written == 1
    assert rebac.enabled_writes == [("team-needs-grant", "runtime-a__rags.sample.echo")]


@pytest.mark.asyncio
async def test_grant_existing_teams_served_templates_migration_dry_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    async def _fake_fetch(base_url: str, include_non_public: bool = False):
        return [_template_payload()]

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch,
    )

    rebac = _FakeTemplateGrantRebac()
    deps = SimpleNamespace(
        team_dependencies=SimpleNamespace(
            rebac=rebac,
            get_team_metadata_store=lambda: _FakeTeamMetadataStoreForMigration(
                ["team-needs-grant"]
            ),
        ),
        get_team_capability_settings_store=lambda: None,
        configuration=SimpleNamespace(
            platform=SimpleNamespace(
                runtime_catalog_sources=[
                    RuntimeCatalogSourceConfig(
                        runtime_id="runtime-a",
                        base_url="http://runtime-a/pod/v1",
                        enabled=True,
                    )
                ]
            )
        ),
    )

    summary = await service.grant_existing_teams_served_templates(deps, dry_run=True)

    assert summary.grants_written == 1
    assert rebac.enabled_writes == []  # dry_run never calls enable_capability_for_team

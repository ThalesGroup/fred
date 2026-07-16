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

from __future__ import annotations

from typing import Any

import httpx
import pytest
from control_plane_backend.app.dependencies import get_application_container_from_app
from control_plane_backend.config.models import (
    ManagedAgentTuning,
    RuntimeCatalogSourceConfig,
)
from control_plane_backend.main import create_app
from control_plane_backend.product.service import _RuntimeTemplatePayload
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.models import FieldSpec
from httpx import ASGITransport, AsyncClient
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


def _template_payload() -> _RuntimeTemplatePayload:
    return _RuntimeTemplatePayload(
        template_agent_id="rags.sample.echo",
        title="Echo Agent",
        description="Echo template description",
        kind="assistant",
        default_tuning=ManagedAgentTuning(
            role="Echo Agent",
            description="Echo template description",
        ),
        available_capabilities=[_DEMO_ENTRY, _PROBE_ENTRY],
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


def _setup(monkeypatch: pytest.MonkeyPatch, records=None):
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
        return [_template_payload()]

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch_runtime_templates,
    )
    return app, store


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

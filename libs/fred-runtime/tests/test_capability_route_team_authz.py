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

"""Capability save, copy and readiness routes build services scoped to the team
the caller names (the team's models): on a secured pod the caller must hold the
team permission control-plane checks for the same operation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import fred_core.security.oidc as oidc_module
import pytest
from _tracer_capability import TracerEchoCapability
from fastapi import HTTPException
from fred_core.security.structure import KeycloakUser
from fred_runtime.app import agent_app as agent_app_module
from fred_sdk.contracts.capability import (
    CapabilityConfigCopyRequest,
    StoredCapabilityConfig,
)
from fred_sdk.contracts.runtime import RuntimeServices
from test_agent_app import _pod_inbound_security  # noqa: F401  (fixture)
from test_capability_endpoints_1974 import _app_with_capabilities

pytestmark = pytest.mark.usefixtures("offline_pod_infrastructure")

_HEADERS = {"Authorization": "Bearer user-token"}
_VERSION = TracerEchoCapability.manifest.version


def _secured(tmp_path, monkeypatch, *, member: bool):
    monkeypatch.setattr(
        oidc_module,
        "decode_jwt",
        lambda token: KeycloakUser(
            uid="u1", username="u1", roles=[], client_id="browser"
        ),
    )

    async def _check(authorization, permission, *, space_id=None):
        if not member:
            raise HTTPException(403, "access_denied")

    check = AsyncMock(side_effect=_check)
    monkeypatch.setattr(agent_app_module, "require_permission", check)
    monkeypatch.setattr(
        agent_app_module,
        "_build_capability_save_services",
        lambda **kwargs: RuntimeServices(),
    )
    client = _app_with_capabilities(
        tmp_path, monkeypatch, TracerEchoCapability(), user_security_enabled=True
    )
    return client, check


def _validate(client, team_id: str | None = "team-1"):
    data = {"config": json.dumps({"uppercase": True})}
    if team_id is not None:
        data["team_id"] = team_id
    return client.post(
        "/pod/v1/agents/capabilities/tracer_echo/validate-config",
        data=data,
        headers=_HEADERS,
    )


def _copy(client, asset_files: dict[str, str] | None = None):
    request = CapabilityConfigCopyRequest(
        config=StoredCapabilityConfig(schema_version=_VERSION, config={}),
        source_team_id="team-1",
        source_agent_instance_id="agent-1",
        target_team_id="team-2",
        target_agent_instance_id="agent-2",
        asset_files=asset_files,
    )
    return client.post(
        "/pod/v1/agents/capabilities/tracer_echo/copy-config",
        json=request.model_dump(mode="json"),
        headers=_HEADERS,
    )


def _export(client):
    return client.post(
        "/pod/v1/agents/capabilities/tracer_echo/export-config",
        json={
            "config": {"schema_version": _VERSION, "config": {}},
            "team_id": "team-1",
            "agent_instance_id": "agent-1",
        },
        headers=_HEADERS,
    )


@pytest.mark.usefixtures("_pod_inbound_security")
@pytest.mark.parametrize("call", [_validate, _copy, _export])
def test_a_non_member_is_refused(tmp_path, monkeypatch, call) -> None:
    client, _ = _secured(tmp_path, monkeypatch, member=False)
    try:
        assert call(client).status_code == 403
    finally:
        client.__exit__(None, None, None)


@pytest.mark.usefixtures("_pod_inbound_security")
def test_a_member_passes_with_the_permission_of_each_route(
    tmp_path, monkeypatch
) -> None:
    client, rebac = _secured(tmp_path, monkeypatch, member=True)
    try:
        assert _validate(client).status_code == 200
        assert _copy(client).status_code == 200
        assert _export(client).status_code == 200
        checks = [
            (call.args[1], call.kwargs["space_id"]) for call in rebac.await_args_list
        ]
        assert checks == [
            ("write", "team-1"),
            ("write", "team-1"),
            ("write", "team-2"),
            ("write", "team-1"),
        ]
    finally:
        client.__exit__(None, None, None)


@pytest.mark.usefixtures("_pod_inbound_security")
def test_cp_config_only_validation_needs_no_fabricated_team(
    tmp_path, monkeypatch
) -> None:
    client, _ = _secured(tmp_path, monkeypatch, member=True)
    try:
        assert _validate(client, team_id=None).status_code == 200
    finally:
        client.__exit__(None, None, None)


@pytest.mark.usefixtures("_pod_inbound_security")
def test_a_snapshot_import_checks_the_target_team_only(tmp_path, monkeypatch) -> None:
    client, rebac = _secured(tmp_path, monkeypatch, member=True)
    try:
        assert _copy(client, asset_files={}).status_code == 200
        checks = [
            (call.args[1], call.kwargs["space_id"]) for call in rebac.await_args_list
        ]
        assert checks == [("write", "team-2")]
    finally:
        client.__exit__(None, None, None)


@pytest.mark.usefixtures("_pod_inbound_security")
def test_resource_validation_requires_a_space(tmp_path, monkeypatch) -> None:
    client, permission = _secured(tmp_path, monkeypatch, member=True)
    try:
        response = client.post(
            "/pod/v1/agents/capabilities/tracer_echo/validate-config",
            data={"config": "{}", "agent_instance_id": "foreign-agent"},
            headers=_HEADERS,
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "space_id_required"
        permission.assert_not_awaited()
    finally:
        client.__exit__(None, None, None)

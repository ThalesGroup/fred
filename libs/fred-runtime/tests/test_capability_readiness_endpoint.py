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

"""`POST /agents/capabilities/readiness`: the pod asks each capability's
`readiness` hook about one instance's stored slices."""

from __future__ import annotations

from _tracer_capability import TracerEchoCapability
from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityIdentity,
    CapabilityManifest,
    CapabilityReadiness,
    EmptyModel,
)
from pydantic import BaseModel
from test_capability_endpoints_1974 import _app_with_capabilities

_URL = "/pod/v1/agents/capabilities/readiness"
SEEN: list[tuple[str, str | None]] = []


class _JobConfig(BaseModel):
    state: str = "pending"


class _JobCapability(AgentCapability[_JobConfig, _JobConfig, EmptyModel]):
    manifest = CapabilityManifest(
        id="job_probe",
        version="2.0.0",
        name="capability.job_probe.name",
        description="capability.job_probe.description",
        icon="Hourglass",
    )
    ConfigModel = _JobConfig

    async def readiness(
        self, stored: _JobConfig, identity: CapabilityIdentity
    ) -> CapabilityReadiness:
        SEEN.append((stored.state, identity.agent_instance_id))
        if stored.state == "failed":
            return CapabilityReadiness.failed("analysis crashed")
        if stored.state == "boom":
            raise RuntimeError("store down")
        return CapabilityReadiness(state=stored.state)  # type: ignore[arg-type]


def _item(capability_id: str, config: dict, version: str = "2.0.0") -> dict:
    return {
        "capability_id": capability_id,
        "stored": {"schema_version": version, "config": config},
    }


def test_readiness_reports_each_known_capability(tmp_path, monkeypatch) -> None:
    SEEN.clear()
    client = _app_with_capabilities(
        tmp_path, monkeypatch, TracerEchoCapability(), _JobCapability()
    )
    try:
        response = client.post(
            _URL,
            json={
                "agent_instance_id": "inst-1",
                "team_id": "team-1",
                "items": [
                    _item("job_probe", {"state": "failed"}),
                    _item(
                        "tracer_echo",
                        {"uppercase": True},
                        TracerEchoCapability.manifest.version,
                    ),
                    _item("ghost", {}),
                ],
            },
        )
        assert response.status_code == 200
        assert response.json() == {
            "results": [
                {
                    "capability_id": "job_probe",
                    "state": "failed",
                    "detail": "analysis crashed",
                },
                # Default hook: ready. The unknown capability is omitted.
                {"capability_id": "tracer_echo", "state": "ready", "detail": None},
            ]
        }
        assert SEEN == [("failed", "inst-1")]
    finally:
        client.__exit__(None, None, None)


def test_a_raising_hook_gives_no_verdict(tmp_path, monkeypatch) -> None:
    client = _app_with_capabilities(tmp_path, monkeypatch, _JobCapability())
    try:
        response = client.post(
            _URL,
            json={
                "agent_instance_id": "inst-1",
                "items": [_item("job_probe", {"state": "boom"})],
            },
        )
        assert response.status_code == 200
        assert response.json() == {"results": []}
    finally:
        client.__exit__(None, None, None)

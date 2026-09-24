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

"""`AgentConfigAssetsAdapter._config_path` — the layout a caller cannot see.

A capability only ever names a slot-relative key, so nothing in the capability
suites pins where those bytes actually land. The frontend now READS that layout
to hand a configured template back to an administrator, mirroring the literal in
`features/capabilities/ppt_filler/templateDownload.ts`. Both sides assert the
same string: change one alone and a suite fails, instead of the download
404-ing in a browser with nothing else to show for it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import fred_runtime.integrations.v2_runtime.adapters as adapters_module
import pytest
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import AgentTuning, MCPServerRef


class _FakeSettings:
    id: str = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


class _NoClient:
    """The path is computed before any call; the client is never exercised."""

    def __init__(self, agent: object) -> None:
        self._agent = agent


def _adapter(monkeypatch: pytest.MonkeyPatch, **runtime_kwargs: Any):
    monkeypatch.setattr(adapters_module, "KfWorkspaceClient", _NoClient)
    binding = BoundRuntimeContext(
        runtime_context=RuntimeContext(session_id="s-1", **runtime_kwargs),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="u-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )
    return adapters_module.AgentConfigAssetsAdapter(
        binding=binding, settings=_FakeSettings()
    )


def test_config_path_is_the_layout_the_frontend_mirrors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter(monkeypatch, team_id="team-a", agent_instance_id="inst-1")

    # Keep in step with `storedTemplateUrl` in templateDownload.ts.
    assert (
        adapter._config_path("ppt_filler_template.pptx")
        == "teams/team-a/agents/inst-1/config/ppt_filler_template.pptx"
    )


def test_config_path_uses_the_canonical_personal_team_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The frontend routes through a bare `personal` alias; storage never does."""
    adapter = _adapter(
        monkeypatch, team_id="personal-user-9", agent_instance_id="inst-1"
    )

    assert adapter._config_path("ppt_filler_template.pptx").startswith(
        "teams/personal-user-9/agents/inst-1/config/"
    )


def test_config_path_refuses_a_key_escaping_the_instance_area(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter(monkeypatch, team_id="team-a", agent_instance_id="inst-1")

    with pytest.raises(ValueError):
        adapter._config_path("../../other/secret.pptx")


def test_config_path_requires_a_team_and_an_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter(monkeypatch, team_id="team-a", agent_instance_id=None)

    with pytest.raises(RuntimeError):
        adapter._config_path("ppt_filler_template.pptx")

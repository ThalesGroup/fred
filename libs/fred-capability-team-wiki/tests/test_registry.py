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

"""Registry boot invariants for the `team_wiki` capability (WIKI-03).

fred-runtime is a dev-group (test-only) dependency here: the capability's own
runtime seam is the fred-sdk `TeamWikiPort` contract, but the boot invariant —
entry-point discovery into a fresh `CapabilityRegistry` plus `.validate()` —
is a fred-runtime concern.
"""

from __future__ import annotations

from importlib.metadata import EntryPoint

from fred_capability_team_wiki.wiki.capability import TeamWikiCapability
from fred_capability_team_wiki.wiki.capability import TeamWikiConfig
from fred_sdk.contracts.capability import EmptyModel
from fred_runtime.capabilities import CapabilityRegistry
from fred_runtime.capabilities.registry import FRED_CAPABILITIES_ENTRY_POINT_GROUP

# Must match the [project.entry-points."fred.capabilities"] declaration in
# pyproject.toml — installing the package IS the registration.
_ENTRY_POINT_VALUE = "fred_capability_team_wiki.wiki.capability:TeamWikiCapability"


def test_capability_registers_via_entry_point_and_boots() -> None:
    registry = CapabilityRegistry()
    entry = EntryPoint(
        name="team_wiki",
        value=_ENTRY_POINT_VALUE,
        group=FRED_CAPABILITIES_ENTRY_POINT_GROUP,
    )
    registered = registry.discover(entry_points=[entry])

    assert registered == ["team_wiki"]
    assert isinstance(registry.capability("team_wiki"), TeamWikiCapability)
    registry.validate(env={})


def test_manifest_is_react_only() -> None:
    """The prompt fragment carrying the team's rules is a ReAct-loop hook the
    Graph runtime never runs. Declaring both models would let a Graph agent
    select this capability and answer without the rules — silently. Pod boot
    enforces the pairing; this pins the declaration itself."""

    assert TeamWikiCapability.manifest.execution_models == ("react",)


def test_manifest_stays_admin_gated() -> None:
    """Enabling this capability is what makes a team's wiki exist at all — for
    its agents AND its people (the control-plane refuses the wiki routes when
    it is off). Flipping it default-on would hand every team a wiki nobody
    asked for."""

    from fred_sdk.contracts.capability import TeamScopePolicy

    assert TeamWikiCapability.manifest.team_scope == TeamScopePolicy.ADMIN_GATED


def test_middleware_does_not_re_register_the_tools() -> None:
    """`tools()` and `middleware()` compose — the assembler builds the tool
    carrier from `tools()` and calls `middleware()` separately
    (`fred_runtime/capabilities/assembly.py`). Returning a carrier here too
    would call `tools()` a second time and put both tools in the model's
    schema twice, on every model call of every turn."""

    from typing import Any

    from fred_sdk.contracts.capability import CapabilityContext, CapabilityIdentity
    from fred_sdk.contracts.capability.base import ToolCarrierMiddleware
    from fred_sdk.contracts.runtime import RuntimeServices

    ctx: Any = CapabilityContext(
        identity=CapabilityIdentity(user_id="u", session_id="s"),
        config=TeamWikiConfig(),
        turn_options=EmptyModel(),
        services=RuntimeServices(),
    )
    stack = TeamWikiCapability().middleware(ctx)

    assert len(stack) == 1
    assert not any(isinstance(m, ToolCarrierMiddleware) for m in stack)

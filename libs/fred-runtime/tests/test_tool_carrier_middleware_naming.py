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
Regression test for a latent `assembly.py` bug (found 2026-07-31 in local
manual testing of `fred.github.assistant`): `ToolCarrierMiddleware` never
overrode `AgentMiddleware.name`, so every instance shared the class-name
default. `create_agent()` rejects a middleware list with duplicate `.name`s
("Please remove duplicate middleware instances."), so ANY agent selecting two
or more tool-bearing capabilities crashed on every execution — this file
proves the fix with two synthetic, single-tool probe capabilities, decoupled
from any real capability (document_access/document_summarize included), to
show the bug and its fix are general to `assembly.py`, not specific to one
capability pairing.

`_McpInstructionsMiddleware` (`fred_runtime/capabilities/mcp.py`) hit this
exact bug first and fixed it by keying `.name` on the MCP server id;
`ToolCarrierMiddleware` (`fred-sdk`) was never given the same treatment.
"""

from __future__ import annotations

from fred_runtime.capabilities import (
    CapabilityRegistry,
    build_capability_agent_block,
    build_capability_context,
)
from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityIdentity,
    CapabilityManifest,
    EmptyModel,
)
from fred_sdk.contracts.runtime import RuntimeServices
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel


class _ProbeConfig(BaseModel):
    pass


def _make_probe_capability(capability_id: str, tool_name: str) -> type[AgentCapability]:
    """One minimal capability with a single tool, relying on the DEFAULT
    `middleware()` (not overridden) — exactly the path `assembly.py` takes
    for every real tool-bearing capability today (document_access,
    document_summarize, ...)."""

    class _Probe(AgentCapability[_ProbeConfig, _ProbeConfig, EmptyModel]):
        manifest = CapabilityManifest(
            id=capability_id,
            version="1.0.0",
            name=f"cap.{capability_id}.name",
            description=f"cap.{capability_id}.description",
            icon="extension",
        )
        ConfigModel = _ProbeConfig

        def tools(
            self, ctx: CapabilityContext[_ProbeConfig, EmptyModel]
        ) -> list[BaseTool]:
            del ctx

            @tool(tool_name)
            def probe_tool(x: str) -> str:
                """A probe tool."""
                return x

            return [probe_tool]

    _Probe.__name__ = f"_Probe_{capability_id}"
    return _Probe


def test_two_tool_bearing_capabilities_get_distinct_middleware_names() -> None:
    """Two DIFFERENT capabilities, each contributing its own
    `ToolCarrierMiddleware` via the default `middleware()` path, must not
    collide — this is exactly what `create_agent()`'s
    `len({m.name for m in middleware}) != len(middleware)` check enforces."""

    registry = CapabilityRegistry()
    first = _make_probe_capability("probe_alpha", "alpha_tool")()
    second = _make_probe_capability("probe_beta", "beta_tool")()
    registry.register(first)
    registry.register(second)

    identity = CapabilityIdentity(user_id="u-1", session_id="s-1", team_id=None)
    services = RuntimeServices()
    contexts = {
        "probe_alpha": build_capability_context(
            first, identity=identity, services=services, config={}
        ),
        "probe_beta": build_capability_context(
            second, identity=identity, services=services, config={}
        ),
    }

    block = build_capability_agent_block(registry, contexts)

    names = [mw.name for mw in block.middleware]
    # The exact invariant `create_agent()` enforces (langchain
    # `agents/factory.py`): a duplicate here means agent execution crashes
    # with AssertionError("Please remove duplicate middleware instances.")
    # for EVERY agent selecting both capabilities.
    assert len(set(names)) == len(names), names
    assert "ToolCarrier[probe_alpha]" in names
    assert "ToolCarrier[probe_beta]" in names


def test_tool_carrier_name_keys_on_capability_id_via_default_middleware() -> None:
    """The default `AgentCapability.middleware()` path (not the assembly
    shortcut) must key `.name` the same way — this is what a capability
    author gets when they call `cap.middleware(ctx)` directly, e.g. in a
    unit test that doesn't go through `build_capability_agent_block`."""

    probe = _make_probe_capability("probe_solo", "solo_tool")()
    ctx = build_capability_context(
        probe,
        identity=CapabilityIdentity(user_id="u-1", session_id="s-1", team_id=None),
        services=RuntimeServices(),
        config={},
    )

    middleware = probe.middleware(ctx)

    assert len(middleware) == 1
    assert middleware[0].name == "ToolCarrier[probe_solo]"

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

"""Tool KPIs carry the id of the capability that provided the tool."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from fred_core.kpi.base_kpi_store import BaseKPIStore
from fred_core.kpi.kpi_reader_structures import KPIQuery, KPIQueryResult
from fred_core.kpi.kpi_writer import KPIWriter
from fred_core.kpi.kpi_writer_structures import KPIEvent
from fred_runtime.capabilities import (
    CapabilityRegistry,
    build_capability_agent_block,
    build_capability_context,
)
from fred_runtime.graph.node_context import NodeContext
from fred_runtime.react.middleware.tool_observability import (
    ToolObservabilityMiddleware,
)
from fred_runtime.runtime_support.tool_execution import (
    CAPABILITY_ID_METADATA_KEY,
    capability_id_of,
)
from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityIdentity,
    CapabilityManifest,
    EmptyModel,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import RuntimeServices
from langchain_core.messages.tool import ToolMessage
from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt.tool_node import ToolCallRequest
from pydantic import BaseModel

SHARED_METADATA = {"owner": "shared"}


@tool("probe_tool")
def _probe_tool(x: str) -> str:
    """A probe tool."""
    return x


_probe_tool.metadata = SHARED_METADATA


class _ProbeConfig(BaseModel):
    pass


class _Probe(AgentCapability[_ProbeConfig, _ProbeConfig, EmptyModel]):
    manifest = CapabilityManifest(
        id="probe_cap",
        version="1.0.0",
        name="cap.probe_cap.name",
        description="cap.probe_cap.description",
        icon="extension",
    )
    ConfigModel = _ProbeConfig

    def tools(self, ctx: CapabilityContext[_ProbeConfig, EmptyModel]) -> list[BaseTool]:
        del ctx
        return [_probe_tool]


class _Store(BaseKPIStore):
    def __init__(self) -> None:
        self.events: list[KPIEvent] = []

    def ensure_ready(self) -> None:
        return

    def index_event(self, event: KPIEvent) -> None:
        self.events.append(event)

    def bulk_index(self, events: list[KPIEvent]) -> None:
        self.events.extend(events)

    def query(self, q: KPIQuery) -> KPIQueryResult:
        return KPIQueryResult(rows=[])

    def dims_of(self, name: str) -> list[dict[str, Any]]:
        return [dict(e.dims) for e in self.events if e.metric.name == name]


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(session_id="s", user_id="u", team_id="t"),
        portable_context=PortableContext(
            request_id="r",
            correlation_id="c",
            actor="u",
            tenant="t",
            environment=PortableEnvironment.DEV,
            session_id="s",
            user_id="u",
        ),
    )


def test_assembly_stamps_the_capability_without_mutating_shared_metadata() -> None:
    registry = CapabilityRegistry()
    capability = _Probe()
    registry.register(capability)
    identity = CapabilityIdentity(user_id="u", session_id="s", team_id=None)
    contexts = {
        "probe_cap": build_capability_context(
            capability, identity=identity, services=RuntimeServices(), config={}
        )
    }

    block = build_capability_agent_block(registry, contexts)

    assert [capability_id_of(t) for t in block.tools] == ["probe_cap"]
    carried = [t for mw in block.middleware for t in getattr(mw, "tools", ())]
    assert [capability_id_of(t) for t in carried] == ["probe_cap"]
    assert block.tools[0].metadata == {
        "owner": "shared",
        CAPABILITY_ID_METADATA_KEY: "probe_cap",
    }
    assert SHARED_METADATA == {"owner": "shared"}


@tool("stamped_tool")
def _stamped(x: str) -> str:
    """Stamped."""
    return x


_stamped.metadata = {CAPABILITY_ID_METADATA_KEY: "documents"}


@tool("builtin_tool")
def _builtin(x: str) -> str:
    """No capability."""
    return x


def _request(tool_obj: BaseTool) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": tool_obj.name, "args": {}, "id": "call-1"},
        tool=tool_obj,
        state={"messages": []},
        runtime=cast(Any, None),
    )


@pytest.mark.asyncio
async def test_middleware_tags_latency_and_failures_with_the_capability() -> None:
    store = _Store()
    middleware = ToolObservabilityMiddleware(
        kpi=KPIWriter(store=store), binding=_binding()
    )

    async def failing(req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(
            content="no",
            name=req.tool_call["name"],
            tool_call_id="call-1",
            status="error",
        )

    await middleware.awrap_tool_call(_request(_stamped), failing)
    await middleware.awrap_tool_call(_request(_builtin), failing)

    latency = store.dims_of("agent.tool_latency_ms")
    failed = store.dims_of("agent.tool_failed_total")
    assert latency[0]["capability_id"] == "documents"
    assert failed[0]["capability_id"] == "documents"
    assert "capability_id" not in latency[1]
    assert "capability_id" not in failed[1]


def test_graph_runtime_tool_tags_latency_with_the_capability() -> None:
    store = _Store()
    ctx = NodeContext(
        binding=_binding(),
        services=RuntimeServices(kpi_writer=KPIWriter(store=store)),
        model=None,
        graph_agent_id="graph-agent",
        node_id="node-1",
        allowed_tool_refs=frozenset(),
        runtime_tools={_stamped.name: _stamped},
        tuning_values={},
        sink=lambda _event: None,
    )

    asyncio.run(ctx.invoke_runtime_tool("stamped_tool", {"x": "hi"}))

    assert store.dims_of("agent.tool_latency_ms")[0]["capability_id"] == "documents"

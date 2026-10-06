# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import json
from typing import cast

import pytest
from fred_capability_web_research.capability import WebResearchCapability
from fred_runtime.capabilities.registry import CapabilityRegistry
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
    SaveContext,
)
from fred_sdk.contracts.runtime import RuntimeServices
from fred_sdk.contracts.web_research import (
    WebPage,
    WebResearchError,
    WebResearchPort,
    WebResearchResult,
)
from pydantic import BaseModel


class Port(WebResearchPort):
    def __init__(self, fail=False):
        self.requests = []
        self.fail = fail

    async def check_ready(self):
        if self.fail:
            raise WebResearchError("activity_unavailable")

    async def execute(self, request):
        self.requests.append(request)
        if self.fail:
            raise WebResearchError("timed_out")
        return WebResearchResult(
            results=[WebPage(url="https://example.com", title="Source")]
        )


def context(port):
    return CapabilityContext(
        identity=CapabilityIdentity(user_id="user"),
        config=EmptyModel(),
        turn_options=EmptyModel(),
        services=RuntimeServices(web_research=port),
    )


def test_registered_capability_is_native_and_execution_agnostic():
    registry = CapabilityRegistry()
    registry.register(WebResearchCapability())
    registry.validate()
    assert "web_research" in registry.ids()
    assert registry.capability("web_research").manifest.execution_models == (
        "react",
        "graph",
    )
    tools = WebResearchCapability().tools(context(Port()))
    assert {tool.name for tool in tools} == {
        "web_search",
        "fetch_url",
        "search_and_fetch",
    }
    for tool in tools:
        properties = cast(type[BaseModel], tool.args_schema).model_json_schema()[
            "properties"
        ]
        assert (
            not {"user_id", "headers", "token", "egress_url", "operation"}
            & properties.keys()
        )


@pytest.mark.asyncio
async def test_tool_result_has_sources_and_shared_error_signal():
    port = Port()
    tool = WebResearchCapability().tools(context(port))[0]
    result = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "web_search",
            "id": "call",
            "args": {"query": "evidence"},
        }
    )
    assert json.loads(result.content)["results"][0]["url"] == "https://example.com"
    assert not result.artifact.is_error
    port.fail = True
    result = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "web_search",
            "id": "call-2",
            "args": {"query": "evidence"},
        }
    )
    assert result.artifact.is_error
    assert json.loads(result.content) == {"error_code": "timed_out"}


@pytest.mark.asyncio
async def test_absent_or_unready_sink_blocks_save_and_tool_construction():
    capability = WebResearchCapability()
    with pytest.raises(RuntimeError):
        capability.tools(context(None))
    with pytest.raises(WebResearchError, match="activity_unavailable"):
        await capability.validate_config(
            EmptyModel(),
            {},
            SaveContext(
                identity=CapabilityIdentity(user_id="user"),
                services=RuntimeServices(web_research=Port(True)),
            ),
        )


@pytest.mark.asyncio
async def test_graph_uses_same_native_tools_and_error_artifacts():
    from fred_runtime.graph.node_context import NodeContext
    from fred_sdk.contracts.context import (
        BoundRuntimeContext,
        PortableContext,
        PortableEnvironment,
        RuntimeContext,
    )

    capability = WebResearchCapability()
    port = Port()
    ctx = context(port)
    graph = NodeContext(
        binding=BoundRuntimeContext(
            runtime_context=RuntimeContext(user_id="user"),
            portable_context=PortableContext(
                request_id="request",
                correlation_id="correlation",
                actor="user",
                tenant="default",
                environment=PortableEnvironment.DEV,
                user_id="user",
            ),
        ),
        services=ctx.services,
        model=None,
        graph_agent_id="graph",
        node_id="web",
        allowed_tool_refs=frozenset(),
        tuning_values={},
        sink=lambda event: None,
        runtime_tools={tool.name: tool for tool in capability.tools(ctx)},
    )
    result = await graph.invoke_runtime_tool("web_search", {"query": "evidence"})
    assert isinstance(result, dict)
    assert result["is_error"] is False
    assert "https://example.com" in result["blocks"][0]["text"]
    port.fail = True
    result = await graph.invoke_runtime_tool("web_search", {"query": "evidence"})
    assert isinstance(result, dict)
    assert result["is_error"] is True
    carrier = capability.middleware(ctx)
    assert {tool.name for tool in carrier[0].tools} == {
        "web_search",
        "fetch_url",
        "search_and_fetch",
    }

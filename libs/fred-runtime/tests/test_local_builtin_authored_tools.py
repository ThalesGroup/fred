"""Native local tools remain callable from Python-authored tools."""

from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace
from typing import cast

import pytest
from fred_runtime.integrations.v2_runtime.adapters import FredKnowledgeSearchToolInvoker
from fred_runtime.runtime_context import RuntimeConfig, set_runtime_context
from fred_runtime.runtime_context import RuntimeContext as FredRuntimeContext
from fred_sdk.authoring.api import ToolContext
from fred_sdk.authoring.authored_tool_runtime import _AuthorRuntime
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    GeoPart,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import AgentTuning, MCPServerRef
from fred_sdk.contracts.ui_part_union import rebuild_ui_part_union
from fred_sdk.support.builtins import (
    TOOL_REF_CHART_RENDER,
    TOOL_REF_GEO_RENDER_POINTS,
    ChartPart,
)


class _Settings:
    id: str = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


@pytest.fixture(autouse=True)
def runtime_context():
    set_runtime_context(
        FredRuntimeContext(RuntimeConfig(knowledge_flow_url="http://kf.invalid/kf/v1"))
    )
    yield
    set_runtime_context(None)


def _authored_context() -> ToolContext:
    binding = BoundRuntimeContext(
        runtime_context=RuntimeContext(session_id="s-1", team_id="team-1"),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="u-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )
    invoker = FredKnowledgeSearchToolInvoker(binding=binding, settings=_Settings())
    runtime = cast(
        _AuthorRuntime,
        SimpleNamespace(binding=binding, tool_invoker=invoker),
    )
    return ToolContext(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_ref", [TOOL_REF_GEO_RENDER_POINTS, "geo.render_points"])
async def test_authored_tool_context_can_invoke_local_builtin(tool_ref: str) -> None:
    context = _authored_context()

    result = await context.invoke_tool(
        tool_ref,
        points=[{"latitude": 48.8566, "longitude": 2.3522}],
    )

    assert result.tool_ref == TOOL_REF_GEO_RENDER_POINTS
    assert result.ui_parts[0].type == "geo"

    zone = await context.invoke_tool(
        TOOL_REF_GEO_RENDER_POINTS,
        points=[
            {"latitude": 43.1242, "longitude": 5.928},
            {"latitude": 43.08, "longitude": 5.95},
            {"latitude": 43.119, "longitude": 6.132},
        ],
        connect_as_zone=True,
    )
    zone_part = zone.ui_parts[0]
    assert isinstance(zone_part, GeoPart)
    assert zone_part.geojson["features"][-1]["geometry"]["type"] == "Polygon"

    invalid = await context.invoke_tool(
        TOOL_REF_GEO_RENDER_POINTS,
        points=[{"latitude": 91, "longitude": 2}],
    )
    assert invalid.is_error
    assert invalid.ui_parts == ()
    assert "points.0.latitude" in (invalid.blocks[0].text or "")


@pytest.mark.asyncio
async def test_authored_chart_call_and_validation_error() -> None:
    rebuild_ui_part_union((ChartPart,))
    try:
        context = _authored_context()
        result = await context.invoke_tool(
            TOOL_REF_CHART_RENDER,
            chart_type="bar",
            title="Revenue",
            rows=[{"label": "Q1", "value": 12}],
            x_key="label",
            y_keys=["value"],
        )
        invalid = await context.invoke_tool(
            TOOL_REF_CHART_RENDER,
            chart_type="bar",
            title="Revenue",
            rows=[{"label": "Q1"}],
        )
    finally:
        rebuild_ui_part_union(())

    assert result.ui_parts[0].type == "chart"
    assert invalid.is_error
    assert invalid.ui_parts == ()

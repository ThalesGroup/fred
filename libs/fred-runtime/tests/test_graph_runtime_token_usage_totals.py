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
Regression test for the Graph-engine token-usage undercount (TRACE-01
follow-up) — the same bug as react_runtime.py's, at the node level: a node
that calls the model more than once before invoking a tool must report the
*sum* of those calls as its contribution to the turn total, not just the
last one. `last_model_metadata` (what the executor folds into the turn
total) must carry that sum, while the per-step attribution used by
`ToolCallRuntimeEvent` (TRACE-01) must keep showing only the most recent
individual call, not a running total.
"""

from __future__ import annotations

import asyncio

from fred_runtime.graph.graph_runtime import _GraphNodeExecutionContext
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import RuntimeServices, ToolCallRuntimeEvent
from langchain_core.tools import tool as lc_tool


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
            team_id="t",
        ),
    )


def _node_context(runtime_tools: dict) -> _GraphNodeExecutionContext:
    return _GraphNodeExecutionContext(
        binding=_binding(),
        services=RuntimeServices(),
        model=None,
        model_resolver=None,
        graph_agent_id="graph-agent",
        node_id="node-1",
        allowed_tool_refs=frozenset(),
        runtime_tools=runtime_tools,
        tuning_values={},
    )


@lc_tool("noop_probe")
async def _noop_probe(x: str) -> str:
    """A tool whose only job is to let invoke_runtime_tool run."""
    return x


def test_last_model_metadata_sums_every_call_the_node_made() -> None:
    ctx = _node_context({})

    ctx.record_model_metadata(
        model_name="gpt-4o",
        token_usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        finish_reason=None,
    )
    ctx.record_model_metadata(
        model_name="gpt-4o",
        token_usage={"input_tokens": 5, "output_tokens": 1, "total_tokens": 6},
        finish_reason="stop",
    )

    model_name, token_usage, finish_reason = ctx.last_model_metadata

    # The bug: this used to equal just {"input_tokens": 5, ...} (the second
    # call alone), silently dropping the first call's 120 tokens.
    assert token_usage == {
        "input_tokens": 105,
        "output_tokens": 21,
        "total_tokens": 126,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
    }
    assert model_name == "gpt-4o"
    assert finish_reason == "stop"


def test_tool_call_event_keeps_only_the_most_recent_call_not_the_running_total() -> (
    None
):
    """
    TRACE-01 per-step display must not regress into showing a node-level
    running total: a tool call right after the node's *second* model call
    should show only that call's usage, not the sum of both.
    """

    ctx = _node_context({"noop_probe": _noop_probe})

    ctx.record_model_metadata(
        model_name="gpt-4o",
        token_usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        finish_reason=None,
    )
    ctx.record_model_metadata(
        model_name="gpt-4o",
        token_usage={"input_tokens": 5, "output_tokens": 1, "total_tokens": 6},
        finish_reason=None,
    )

    asyncio.run(ctx.invoke_runtime_tool("noop_probe", {"x": "y"}))

    (event,) = [e for e in ctx.events if isinstance(e, ToolCallRuntimeEvent)]
    assert event.token_usage == {
        "input_tokens": 5,
        "output_tokens": 1,
        "total_tokens": 6,
    }

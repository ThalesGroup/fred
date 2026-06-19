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

"""Tests for typed, scoped agent invocation (RFC AGENT-INVOKE).

Covers the JSON-coercion helpers and ``GraphNodeContext.invoke_agent``'s structured
output + per-call scope + bounded-retry behaviour against a fake invoker.
"""

import asyncio

from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    AgentInvocationResult,
    BoundRuntimeContext,
    InvocationScope,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import AgentInvokerPort, RuntimeServices
from pydantic import BaseModel

from fred_runtime.graph.graph_runtime import (
    _coerce_structured_payload,
    _extract_json_object,
    _GraphNodeExecutionContext,
)


class _Extraction(BaseModel):
    component: str
    version: str | None = None


class _FakeInvoker(AgentInvokerPort):
    """Records requests and replays a fixed list of response contents."""

    def __init__(self, contents: list[str]) -> None:
        self._contents = contents
        self.requests: list[AgentInvocationRequest] = []

    async def invoke(self, request: AgentInvocationRequest) -> AgentInvocationResult:
        index = min(len(self.requests), len(self._contents) - 1)
        self.requests.append(request)
        return AgentInvocationResult(
            agent_id=request.agent_id, content=self._contents[index]
        )


def _context(invoker: AgentInvokerPort) -> _GraphNodeExecutionContext:
    binding = BoundRuntimeContext(
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
    return _GraphNodeExecutionContext(
        binding=binding,
        services=RuntimeServices(agent_invoker=invoker),
        model=None,
        model_resolver=None,
        graph_agent_id="caller",
        node_id="node-1",
        allowed_tool_refs=frozenset(),
        runtime_tools={},
        tuning_values={},
    )


# --- pure helpers ---------------------------------------------------------


def test_extract_json_object_handles_plain_fenced_and_embedded() -> None:
    assert _extract_json_object('{"a": 1}') == {"a": 1}
    assert _extract_json_object('```json\n{"a": 2}\n```') == {"a": 2}
    assert _extract_json_object('text {"a": 3} more') == {"a": 3}
    assert _extract_json_object("no json") is None
    # a bare JSON array is not an object
    assert _extract_json_object("[1, 2, 3]") is None


def test_coerce_structured_payload_validates_against_schema() -> None:
    assert _coerce_structured_payload('{"component": "nginx"}', _Extraction) == {
        "component": "nginx",
        "version": None,
    }
    # missing required field → no coercion
    assert _coerce_structured_payload('{"version": "1"}', _Extraction) is None


# --- invoke_agent: structured output + scope + retry ----------------------


def test_invoke_agent_returns_validated_structured_payload() -> None:
    invoker = _FakeInvoker(['{"component": "nginx", "version": "1.25"}'])
    ctx = _context(invoker)

    result = asyncio.run(
        ctx.invoke_agent("callee", "is nginx installed?", output_schema=_Extraction)
    )

    assert result.structured == {"component": "nginx", "version": "1.25"}
    assert len(invoker.requests) == 1
    # the callee was asked for schema-conformant JSON, and the schema travelled too
    assert "JSON Schema" in invoker.requests[0].message
    assert invoker.requests[0].output_schema is not None


def test_invoke_agent_retries_then_gives_up_with_none() -> None:
    invoker = _FakeInvoker(["not json", "still not json"])
    ctx = _context(invoker)

    result = asyncio.run(
        ctx.invoke_agent("callee", "extract", output_schema=_Extraction)
    )

    assert result.structured is None
    assert len(invoker.requests) == 2  # bounded retry happened
    assert result.is_error is False  # text answer still returned


def test_invoke_agent_forwards_scope_and_stays_backward_compatible() -> None:
    invoker = _FakeInvoker(["plain text answer"])
    ctx = _context(invoker)

    scope = InvocationScope(document_uids=["doc-1"], search_policy="strict")
    result = asyncio.run(ctx.invoke_agent("callee", "hi", scope=scope))

    assert result.content == "plain text answer"
    assert result.structured is None  # no schema requested
    assert len(invoker.requests) == 1
    assert invoker.requests[0].scope == scope
    assert invoker.requests[0].output_schema is None
    # message is untouched when no schema is requested
    assert invoker.requests[0].message == "hi"

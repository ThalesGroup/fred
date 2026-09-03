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
Test doubles for the fred-sdk graph authoring surface.

Why this module exists:
- every fred-sdk graph node reaches the model, sub-agents, and declared
  platform tools through the same three calls:
  `context.invoke_agent(...)` (directly, or via `invoke_agent`),
  `context.invoke_structured_model(...)` (via `structured_model_step`), and
  `context.invoke_tool(...)` (declared_tool_refs, e.g. `knowledge.search`)
- testing a node offline means faking exactly those three calls, nothing else
  on `GraphNodeContext` — every other member can stay unimplemented
- this shape is not a new design: it was hand-rolled independently at least
  twice (fred-sdk's own test suite, and a real external fred-sdk pod) before
  being promoted here, converging on the same two calls and the same
  fail-loud-on-unconfigured-call behaviour without ever being coordinated
  (`invoke_tool` added later, same convention, once a second graph agent
  needed to test a declared_tool_ref node)

How to use it:
- `GraphNodeContext` is a `Protocol`, not a base class — do not subclass
  `FakeGraphNodeContext` from it; instead construct it directly and pass it
  to your node function with `cast(GraphNodeContext, fake)` at the call site,
  exactly as you would for any other `GraphNodeContext` double
- configure only what the node under test actually calls: `agent_result`
  (optionally keyed by `agent_id` when a node calls more than one agent) for
  `invoke_agent`, `structured_results` for `structured_model_step` — one
  value, or a list when the node under test calls it more than once (each
  call pops the next queued value, in order), `tool_result` (optionally
  keyed by `tool_ref`) for `invoke_tool`
- a call the test did not configure raises `AssertionError` immediately,
  so an under-specified test fails loudly instead of silently returning
  `None` or an empty result into your node's business logic

Example:
```python
from typing import cast
from fred_sdk import AgentInvocationResult, GraphNodeContext
from fred_sdk.testing import FakeGraphNodeContext

context = FakeGraphNodeContext(
    agent_result=AgentInvocationResult(
        agent_id="tessa", content="", structured={"trust": "high"}
    ),
    structured_results={"intent": "question_cloud_general"},
)
result = await my_node(state, cast(GraphNodeContext, context))
assert context.agent_calls[0]["agent_id"] == "tessa"
assert context.structured_model_calls == 1
```
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .contracts.context import AgentInvocationResult, ToolInvocationResult


class FakeGraphNodeContext:
    """
    Minimal `GraphNodeContext` double for testing graph nodes offline.

    See the module docstring for why this exists and how to use it.
    """

    def __init__(
        self,
        *,
        agent_result: AgentInvocationResult
        | Mapping[str, AgentInvocationResult]
        | None = None,
        structured_results: Any | Sequence[Any] | None = None,
        tool_result: ToolInvocationResult
        | Mapping[str, ToolInvocationResult]
        | None = None,
        model: object | None = object(),
    ) -> None:
        self._agent_result = agent_result
        self._structured_results: list[Any] = (
            list(structured_results)
            if isinstance(structured_results, list)
            else [structured_results]
            if structured_results is not None
            else []
        )
        self._tool_result = tool_result
        self.model = model
        self.agent_calls: list[dict[str, Any]] = []
        self.structured_model_calls = 0
        self.tool_calls: list[dict[str, Any]] = []

    def emit_status(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def invoke_agent(
        self,
        agent_id: str,
        message: str,
        *,
        prior_turns: tuple[Any, ...] = (),
        output_schema: Any = None,
        scope: Any = None,
    ) -> AgentInvocationResult:
        self.agent_calls.append(
            {
                "agent_id": agent_id,
                "message": message,
                "output_schema": output_schema,
                "scope": scope,
                "prior_turns": prior_turns,
            }
        )
        if isinstance(self._agent_result, Mapping):
            if agent_id not in self._agent_result:
                raise AssertionError(
                    "FakeGraphNodeContext.invoke_agent: no canned agent_result "
                    f"configured for agent_id={agent_id!r}."
                )
            return self._agent_result[agent_id]
        if self._agent_result is None:
            raise AssertionError(
                "FakeGraphNodeContext.invoke_agent was called but no agent_result "
                "was configured."
            )
        return self._agent_result

    async def invoke_tool(
        self, tool_ref: str, payload: Mapping[str, Any]
    ) -> ToolInvocationResult:
        self.tool_calls.append({"tool_ref": tool_ref, "payload": dict(payload)})
        if isinstance(self._tool_result, Mapping):
            if tool_ref not in self._tool_result:
                raise AssertionError(
                    "FakeGraphNodeContext.invoke_tool: no canned tool_result "
                    f"configured for tool_ref={tool_ref!r}."
                )
            return self._tool_result[tool_ref]
        if self._tool_result is None:
            raise AssertionError(
                "FakeGraphNodeContext.invoke_tool was called but no tool_result "
                "was configured."
            )
        return self._tool_result

    async def invoke_structured_model(
        self,
        output_model: type,
        messages: Any,
    ) -> Any:
        if not self._structured_results:
            raise AssertionError(
                "FakeGraphNodeContext.invoke_structured_model was called but no "
                "(more) structured_results were configured."
            )
        self.structured_model_calls += 1
        return self._structured_results.pop(0)

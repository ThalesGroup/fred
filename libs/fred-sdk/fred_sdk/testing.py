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
- every fred-sdk graph node reaches the platform through the same two calls:
  `context.invoke_agent(...)` (directly, or via `invoke_agent`) and
  `context.invoke_structured_model(...)` (via `structured_model_step`)
- testing a node offline means faking exactly those two calls, nothing else
  on `GraphNodeContext` — every other member can stay unimplemented
- this shape is not a new design: it was hand-rolled independently at least
  twice (fred-sdk's own test suite, and a real external fred-sdk pod) before
  being promoted here, converging on the same two calls and the same
  fail-loud-on-unconfigured-call behaviour without ever being coordinated

How to use it:
- `GraphNodeContext` is a `Protocol`, not a base class — do not subclass
  `FakeGraphNodeContext` from it; instead construct it directly and pass it
  to your node function with `cast(GraphNodeContext, fake)` at the call site,
  exactly as you would for any other `GraphNodeContext` double
- configure only what the node under test actually calls: `agent_result`
  (optionally keyed by `agent_id` when a node calls more than one agent) for
  `invoke_agent`, `structured_by_operation` for `structured_model_step`
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
    structured_by_operation={"classify": {"intent": "question_cloud_general"}},
)
result = await my_node(state, cast(GraphNodeContext, context))
assert context.agent_calls[0]["agent_id"] == "tessa"
assert context.structured_operations == ["classify"]
```
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts.context import AgentInvocationResult


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
        structured_by_operation: Mapping[str, Any] | None = None,
        model: object | None = object(),
    ) -> None:
        self._agent_result = agent_result
        self._structured_by_operation = dict(structured_by_operation or {})
        self.model = model
        self.agent_calls: list[dict[str, Any]] = []
        self.structured_operations: list[str] = []

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

    async def invoke_structured_model(
        self,
        output_model: type,
        messages: Any,
        *,
        operation: str = "default",
    ) -> Any:
        self.structured_operations.append(operation)
        if operation not in self._structured_by_operation:
            raise AssertionError(
                "FakeGraphNodeContext.invoke_structured_model: no canned output "
                f"configured for operation={operation!r}."
            )
        return self._structured_by_operation[operation]

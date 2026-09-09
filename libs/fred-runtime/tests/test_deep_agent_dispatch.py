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
Regression guard for the per-turn runtime dispatch in
`_iterate_runtime_event_payloads`: a `DeepAgentDefinition` must route to
`DeepAgentRuntime`, never to plain `ReActRuntime`, even though
`DeepAgentDefinition` is-a `ReActAgentDefinition` and previously fell through
the `else` branch unnoticed.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.react.react_runtime import _TransportBackedReActExecutor
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import (
    DeepAgentDefinition,
    ReActAgentDefinition,
    ReActPolicy,
)
from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_sdk.contracts.runtime import ExecutionConfig, RuntimeServices


class _DeepAgent(DeepAgentDefinition):
    agent_id: str = "test.deep.dispatch"
    role: str = "test"
    description: str = "test"

    def policy(self) -> ReActPolicy:
        raise NotImplementedError


class _ReActAgent(ReActAgentDefinition):
    agent_id: str = "test.react.dispatch"
    role: str = "test"
    description: str = "test"

    def policy(self) -> ReActPolicy:
        raise NotImplementedError


class _NullExecutor:
    async def stream(self, *args: object, **kwargs: object) -> AsyncIterator[Any]:
        return
        yield  # pragma: no cover - makes this an async generator


class _RecordingRuntime:
    instances: list["_RecordingRuntime"]

    def __init__(
        self, *, definition: object, services: object, capability_block: object
    ) -> None:
        self.definition = definition
        self.capability_block = capability_block
        type(self).instances.append(self)

    def bind(self, binding: object) -> None:
        pass

    async def activate(self) -> None:
        pass

    async def get_executor(self) -> _NullExecutor:
        return _NullExecutor()

    async def dispose(self) -> None:
        pass


class _FakeDeepRuntime(_RecordingRuntime):
    instances: list["_FakeDeepRuntime"] = []


class _FakeReActRuntime(_RecordingRuntime):
    instances: list["_FakeReActRuntime"] = []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("definition", "expect_deep"),
    [(_DeepAgent(), True), (_ReActAgent(), False)],
)
async def test_dispatch_routes_deep_definition_to_deep_runtime(
    monkeypatch: pytest.MonkeyPatch,
    definition: ReActAgentDefinition,
    expect_deep: bool,
) -> None:
    _FakeDeepRuntime.instances.clear()
    _FakeReActRuntime.instances.clear()
    monkeypatch.setattr(agent_app_module, "DeepAgentRuntime", _FakeDeepRuntime)
    monkeypatch.setattr(agent_app_module, "ReActRuntime", _FakeReActRuntime)
    monkeypatch.setattr(
        agent_app_module,
        "_build_runtime_services",
        lambda *args, **kwargs: RuntimeServices(),
    )
    # Needs a `.middleware` attribute: agent_app.py's debug trace logs
    # `len(capability_block.middleware)` before dispatch even runs.
    sentinel_capability_block = SimpleNamespace(middleware=())
    monkeypatch.setattr(
        agent_app_module,
        "_build_capability_block",
        lambda *args, **kwargs: sentinel_capability_block,
    )

    request = agent_app_module._AgentExecuteRequest(
        agent_id=definition.agent_id, message="hello"
    )

    payloads = [
        payload
        async for payload in agent_app_module._iterate_runtime_event_payloads(
            definition, request
        )
    ]

    assert payloads == []
    assert len(_FakeDeepRuntime.instances) == (1 if expect_deep else 0)
    assert len(_FakeReActRuntime.instances) == (0 if expect_deep else 1)
    # Whichever runtime class dispatch selects, capability_block must reach
    # it unchanged — this was the exact regression a dispatch-only fix would
    # otherwise have introduced for Deep (see RUNTIME-EXECUTION-CONTRACT.md
    # §8.75).
    selected = (
        _FakeDeepRuntime.instances[0] if expect_deep else _FakeReActRuntime.instances[0]
    )
    assert selected.capability_block is sentinel_capability_block


class _RecordingCompiledAgent:
    async def ainvoke(
        self, graph_input: object, *, config: object = None
    ) -> dict[str, object]:
        from langchain_core.messages import AIMessage

        return {"messages": [AIMessage(content="ok")]}


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="user-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
            session_id="session-1",
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runtime_class_name", "unexpected"),
    [("DeepAgentRuntime", "ReActRuntime"), ("ReActRuntime", "DeepAgentRuntime")],
)
async def test_executor_invoke_log_names_the_actual_runtime_class(
    caplog: pytest.LogCaptureFixture,
    runtime_class_name: str,
    unexpected: str,
) -> None:
    """`_TransportBackedReActExecutor` is shared by both `ReActRuntime` and
    `DeepAgentRuntime` — its per-exchange log line must name whichever
    runtime actually built it, not a string hard-coded to "ReActRuntime"
    regardless of caller (the ambiguity a prior fix left in place)."""
    executor = _TransportBackedReActExecutor(
        compiled_agent=cast(Any, _RecordingCompiledAgent()),
        binding=_binding(),
        services=cast(Any, RuntimeServices()),
        runtime_class_name=runtime_class_name,
    )
    input_model = ReActInput(
        messages=(ReActMessage(role=ReActMessageRole.USER, content="hi"),)
    )

    with caplog.at_level(logging.INFO, logger="fred_runtime.react.react_runtime"):
        await executor.invoke(input_model, ExecutionConfig(session_id="session-1"))

    messages = [r.getMessage() for r in caplog.records]
    assert any(runtime_class_name in m for m in messages)
    assert not any(unexpected in m for m in messages)

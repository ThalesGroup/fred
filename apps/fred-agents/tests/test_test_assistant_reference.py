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
Graph conformance, offline.

Runs the checks of `fred_agents.test_assistant.conformance` — the same ones
`graph check` runs live through the pod's HTTP API — against `Executor.stream`
with the in-process mock model, fake platform services and a shared in-memory
checkpointer. Every turn builds a fresh runtime, as another replica would.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fred_agents.test_assistant.conformance import CHECKS, Check, Event, TurnResult
from fred_agents.test_assistant.graph_agent import TestAssistantGraphAgent
from fred_agents.test_assistant.graph_state import TestInput
from fred_agents.test_assistant.mock_llm import MockChatModelFactory
from fred_core.store import VectorSearchHit
from fred_runtime.graph.graph_runtime import GraphRuntime
from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    AgentInvocationResult,
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    PublishedArtifact,
    RuntimeContext,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from fred_sdk.contracts.runtime import (
    AgentInvokerPort,
    ExecutionConfig,
    FinalRuntimeEvent,
    RuntimeServices,
    ToolInvokerPort,
)
from fred_sdk.graph.runtime import GraphExecutionOutput
from langgraph.checkpoint.memory import InMemorySaver


class _FakeKnowledgeSearch(ToolInvokerPort):
    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        return ToolInvocationResult(
            tool_ref=request.tool_ref,
            sources=(
                VectorSearchHit(
                    uid="doc-fred-1",
                    title="Fred Overview",
                    content="Fred is an agentic platform.",
                    score=0.9,
                ),
            ),
        )


class _InProcessAgentInvoker(AgentInvokerPort):
    """Runs the callee in this process, as LocalRegistryAgentInvoker does."""

    def __init__(self, services: RuntimeServices) -> None:
        self._services = services

    async def invoke(self, request: AgentInvocationRequest) -> AgentInvocationResult:
        runtime = GraphRuntime(
            definition=TestAssistantGraphAgent(),
            services=self._services,
        )
        runtime.bind(_binding(session_id="s-delegate", instance_id=None))
        executor = await runtime.get_executor()
        final = [
            event
            async for event in executor.stream(
                TestInput(message=request.message),
                ExecutionConfig(session_id="s-delegate"),
            )
        ][-1]
        assert isinstance(final, FinalRuntimeEvent)
        return AgentInvocationResult(agent_id=request.agent_id, content=final.content)


def _binding(*, session_id: str, instance_id: str | None) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id=session_id, user_id="u1", team_id="t1"
        ),
        portable_context=PortableContext(
            request_id="r1",
            correlation_id="c1",
            actor="u1",
            tenant="t1",
            environment=PortableEnvironment.DEV,
            session_id=session_id,
            user_id="u1",
            team_id="t1",
            baggage={"agent_instance_id": instance_id} if instance_id else {},
        ),
    )


class _ExecutorDriver:
    """conformance `Driver` over `Executor.stream`: one pod's worth of services."""

    def __init__(self) -> None:
        workspace = SimpleNamespace(
            bind=Mock(),
            write=AsyncMock(
                return_value=PublishedArtifact(
                    key="k1", file_name="test_assistant_answer.md", size=10
                )
            ),
        )
        base = RuntimeServices(
            chat_model_factory=MockChatModelFactory(), checkpointer=InMemorySaver()
        )
        self.services = RuntimeServices(
            chat_model_factory=base.chat_model_factory,
            checkpointer=base.checkpointer,
            tool_invoker=_FakeKnowledgeSearch(),
            workspace_fs=workspace,  # type: ignore[arg-type]
            agent_invoker=_InProcessAgentInvoker(base),
        )

    async def executor(self, session_id: str):
        runtime = GraphRuntime(
            definition=TestAssistantGraphAgent(),
            services=self.services,
        )
        runtime.bind(_binding(session_id=session_id, instance_id="inst-parent"))
        return await runtime.get_executor()

    async def send(self, session_id: str, message: str) -> TurnResult:
        return await self._turn(
            session_id, message, ExecutionConfig(session_id=session_id)
        )

    async def resume(
        self, session_id: str, request: Event, choice_id: str
    ) -> TurnResult:
        return await self._turn(
            session_id,
            "resume",
            ExecutionConfig(
                session_id=session_id,
                interrupt_id=request.get("interrupt_id"),
                resume_payload={"answer": choice_id, "choice_id": choice_id},
            ),
        )

    async def _turn(
        self, session_id: str, message: str, config: ExecutionConfig
    ) -> TurnResult:
        executor = await self.executor(session_id)
        try:
            events = [
                event.model_dump(mode="json")
                async for event in executor.stream(TestInput(message=message), config)
            ]
        except RuntimeError as exc:
            return TurnResult(rejected=str(exc))
        return TurnResult(events=events)


@pytest.mark.asyncio
@pytest.mark.parametrize("check", CHECKS, ids=lambda check: check.name)
async def test_conformance(check: Check) -> None:
    failures = await check.run(_ExecutorDriver(), f"s-{check.name}")
    assert failures == [], f"{check.name}: {failures}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prompt", "resume_payload", "expected"),
    [
        ("hitl confirm", {"choice_id": "yes"}, "selected **yes**"),
        ("hitl choice", {"choice_id": "option_d"}, "another review"),
        ("hitl text", {"text": "Bonjour"}, "**Bonjour**"),
        (
            "hitl comment",
            {"choice_id": "short", "text": "Keep it brief"},
            "**Keep it brief**",
        ),
    ],
)
async def test_no_llm_hitl_examples_pause_and_resume(
    prompt: str, resume_payload: dict[str, str], expected: str
) -> None:
    driver = _ExecutorDriver()
    session = f"s-{prompt.replace(' ', '-')}"
    paused = await driver.send(session, prompt)
    awaiting = next(
        event for event in paused.events if event.get("kind") == "awaiting_human"
    )
    resumed = await driver._turn(
        session,
        "resume",
        ExecutionConfig(
            session_id=session,
            interrupt_id=awaiting.get("interrupt_id"),
            resume_payload=resume_payload,
        ),
    )
    assert resumed.rejected is None
    final = next(event for event in resumed.events if event.get("kind") == "final")
    assert expected in str(final.get("content"))


@pytest.mark.asyncio
async def test_invoke_returns_the_output_model() -> None:
    executor = await _ExecutorDriver().executor("s-invoke")
    output = await executor.invoke(
        TestInput(message="echo invoke"), ExecutionConfig(session_id="s-invoke")
    )
    assert isinstance(output, GraphExecutionOutput)
    assert output.content.startswith("Echo: echo invoke")

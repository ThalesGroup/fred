# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
"""Real no-model Graph questions through the platform ask_user tool."""

from __future__ import annotations

import pytest
from fred_agents.test_assistant.graph_agent import TestAssistantGraphAgent
from fred_agents.test_assistant.graph_state import TestInput
from fred_runtime.graph.graph_runtime import GraphRuntime
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import (
    AwaitingHumanRuntimeEvent,
    ExecutionConfig,
    FinalRuntimeEvent,
    RuntimeServices,
    ToolCallRuntimeEvent,
    ToolResultRuntimeEvent,
)
from langgraph.checkpoint.memory import InMemorySaver


def _binding(*, ask_user: bool) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(ask_user=ask_user, language="fr"),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="user-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario", "answer", "expected_choice_count", "expected_text"),
    [
        ("hitl confirm", {"choice_id": "yes"}, 2, "You selected **yes**"),
        ("hitl choice", {"choice_id": "option_d"}, 4, "sent for another review"),
        ("hitl text", {"text": "A short answer"}, 0, "A short answer"),
        (
            "hitl comment",
            {"choice_id": "detailed", "text": "Include examples"},
            2,
            "Include examples",
        ),
        ("hitl choice", {"skipped": True}, 4, "question was skipped"),
    ],
)
async def test_test_assistant_questions_use_real_tool_and_resume(
    scenario: str,
    answer: dict[str, object],
    expected_choice_count: int,
    expected_text: str,
) -> None:
    saver = InMemorySaver()
    services = RuntimeServices(checkpointer=saver)
    runtime = GraphRuntime(definition=TestAssistantGraphAgent(), services=services)
    executor = await runtime.build_executor(_binding(ask_user=True))
    session_id = "hitl-scenario"

    pending = [
        event
        async for event in executor.stream(
            TestInput(message=scenario), ExecutionConfig(session_id=session_id)
        )
    ]
    pause = next(
        event for event in pending if isinstance(event, AwaitingHumanRuntimeEvent)
    )
    calls = [event for event in pending if isinstance(event, ToolCallRuntimeEvent)]
    assert len(calls) == 1
    assert calls[0].tool_name == "ask_user"
    assert pause.request.stage == "agent_question"
    assert pause.request.occurrence_id == calls[0].call_id
    assert len(pause.request.choices) == expected_choice_count
    assert pause.request.free_text is True
    assert not any(isinstance(event, ToolResultRuntimeEvent) for event in pending)

    resumed = [
        event
        async for event in executor.stream(
            TestInput(message=scenario),
            ExecutionConfig(
                session_id=session_id,
                interrupt_id=pause.request.interrupt_id,
                resume_payload=answer,
            ),
        )
    ]
    results = [event for event in resumed if isinstance(event, ToolResultRuntimeEvent)]
    assert len(results) == 1
    assert results[0].call_id == calls[0].call_id
    assert results[0].tool_name == "ask_user"
    assert results[0].is_error is False
    final = next(event for event in resumed if isinstance(event, FinalRuntimeEvent))
    assert expected_text in final.content


@pytest.mark.asyncio
async def test_test_assistant_question_requires_interactive_toggle() -> None:
    runtime = GraphRuntime(
        definition=TestAssistantGraphAgent(),
        services=RuntimeServices(checkpointer=InMemorySaver()),
    )
    executor = await runtime.build_executor(_binding(ask_user=False))
    events = [
        event
        async for event in executor.stream(
            TestInput(message="hitl choice"), ExecutionConfig(session_id="disabled")
        )
    ]
    assert not any(isinstance(event, AwaitingHumanRuntimeEvent) for event in events)
    assert not any(isinstance(event, ToolCallRuntimeEvent) for event in events)
    final = next(event for event in events if isinstance(event, FinalRuntimeEvent))
    assert "no valid selection received" in final.content

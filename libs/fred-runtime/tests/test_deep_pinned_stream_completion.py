# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Native context patches retain stream completion without replaying tool results."""

from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from conftest import ToolFriendlyFakeChatModel
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from fred_core.history.history_schema import ChatMessage, ToolCallPart, ToolResultPart
from fred_runtime.app.agent_app import _write_turn_history
from fred_runtime.react.react_model_adapter import CompiledReActAgent
from fred_runtime.react.react_runtime import _TransportBackedReActExecutor
from fred_runtime.react.react_stream_adapter import (
    extract_messages_from_update,
    split_stream_event_mode,
)
from fred_runtime.skills.catalog import PlatformSkills
from fred_sdk.contracts.context import ToolInvocationResult
from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_sdk.contracts.runtime import (
    AssistantDeltaRuntimeEvent,
    ExecutionConfig,
    FinalRuntimeEvent,
    HistoryStorePort,
    RuntimeServices,
    SpanPort,
    StatusRuntimeEvent,
    ToolCallRuntimeEvent,
    ToolResultRuntimeEvent,
    TracerPort,
)
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.exceptions import ContextOverflowError
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from test_platform_skills import Model, binding, compiled
from test_skill_eligibility import publish

ANSWER = "```mermaid\ngraph TD\nA --> B\n```"
USAGE: UsageMetadata = {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}


@pytest.mark.parametrize("container", [list, tuple])
def test_partial_updates_keep_new_response_and_tool_execution_messages(
    container: type,
) -> None:
    assistant = AIMessage(content=ANSWER)
    structured = ToolMessage(content="structured output", tool_call_id="structured")
    executed = ToolMessage(content="new tool result", tool_call_id="executed")
    pin = HumanMessage(content="synthetic skill instructions")
    update = {
        "model": container(
            [
                {"model_metadata": {}},
                {
                    "messages": [
                        assistant,
                        structured,
                        {"messages": [AIMessage(content="untyped envelope")]},
                    ]
                },
                {"_skill_tools_disclosed": {}},
                {"messages": [pin]},
                {"fred_pending_skill_names": []},
            ]
        ),
        "tools": container([{"messages": [executed]}]),
    }
    assert extract_messages_from_update(update) == [assistant, structured, executed]


def test_context_repairs_are_not_execution_events() -> None:
    previous = AIMessage(
        content="", tool_calls=[{"id": "old-call", "name": "read_file", "args": {}}]
    )
    repair = PatchToolCallsMiddleware().before_agent(
        {"messages": [HumanMessage(content="Previous turn"), previous]},
        cast(Any, None),
    )
    assert repair is not None
    assert previous in repair["messages"]
    assert any(isinstance(m, ToolMessage) for m in repair["messages"])
    current = AIMessage(content="Current answer")
    refusal = ToolMessage(
        content="Current refusal", tool_call_id="new-call", status="error"
    )
    limit = AIMessage(content="Model call limit exceeded")
    assert extract_messages_from_update(
        {
            "PatchToolCallsMiddleware.before_agent": repair,
            "model": {"messages": [current]},
            "Gate.after_model": {"messages": [refusal]},
            "ModelCallLimitMiddleware.before_model": {"messages": [limit]},
        }
    ) == [current, refusal, limit]


@pytest.mark.asyncio
@pytest.mark.parametrize("read_fails", [False, True])
async def test_deep_repaired_checkpoint_emits_and_saves_only_current_calls(
    read_fails: bool,
) -> None:
    @tool(response_format="content_and_artifact")
    async def current_tool(fail: bool = False) -> tuple[str, ToolInvocationResult]:
        """Return a current result, including a recoverable tool failure."""
        return "Current result", ToolInvocationResult(
            tool_ref="runtime:current_tool", is_error=fail
        )

    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"id": "new-list", "name": "current_tool", "args": {}}],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "new-read",
                        "name": "current_tool",
                        "args": {"fail": read_fails},
                    }
                ],
            ),
            AIMessage(content=ANSWER, usage_metadata=USAGE),
        ]
    )
    graph = create_deep_agent(
        model,
        tools=[current_tool],
        backend=StateBackend(),
        checkpointer=InMemorySaver(),
    )
    config = ExecutionConfig(session_id="repaired-conversation")
    assert config.session_id is not None
    graph_config: RunnableConfig = {"configurable": {"thread_id": config.session_id}}
    historical: list[BaseMessage] = [HumanMessage(content="Previous turn")]
    old_ids = ("plPp8xl0E", "Oh6FEoYlN", "EWj81OsBR", "8A0XVUuV5")
    for index, call_id in enumerate(old_ids):
        historical.append(
            AIMessage(
                content="",
                tool_calls=[{"id": call_id, "name": "current_tool", "args": {}}],
                usage_metadata=USAGE,
            )
        )
        if index < len(old_ids) - 1:
            historical.append(
                ToolMessage(
                    content="Previous result",
                    tool_call_id=call_id,
                    status="error" if index == 1 else "success",
                )
            )
    # The failed last call has no checkpoint result: native Deep repairs it at
    # the next turn, publishing all four historical calls as a context update.
    await graph.aupdate_state(graph_config, {"messages": historical}, as_node="model")
    previous_state = await graph.aget_state(graph_config)
    previous_messages = {
        m.id: m.model_dump() for m in previous_state.values["messages"]
    }
    executor = _TransportBackedReActExecutor(
        compiled_agent=cast(CompiledReActAgent, graph),
        binding=binding(),
        services=RuntimeServices(),
        runtime_class_name="Deep",
        preload_selected_skill=False,
    )
    events = [
        event
        async for event in executor.stream(
            ReActInput(
                messages=(
                    ReActMessage(
                        role=ReActMessageRole.USER, content="Read the correct file"
                    ),
                )
            ),
            config,
        )
    ]
    calls = [e for e in events if isinstance(e, ToolCallRuntimeEvent)]
    results = [e for e in events if isinstance(e, ToolResultRuntimeEvent)]
    assert [e.call_id for e in calls] == ["new-list", "new-read"]
    assert [e.call_id for e in results] == ["new-list", "new-read"]
    assert [e.is_error for e in results] == [False, read_fails]
    assert all(e.latency_ms is not None and e.latency_ms >= 0 for e in results)
    [final] = [e for e in events if isinstance(e, FinalRuntimeEvent)]
    assert final.content == ANSWER
    assert final.token_usage is not None
    assert {key: final.token_usage[key] for key in USAGE} == USAGE

    state = await graph.aget_state(graph_config)
    retained = {
        m.id: m.model_dump()
        for m in state.values["messages"]
        if m.id in previous_messages
    }
    assert retained == previous_messages
    assert any(
        isinstance(m, ToolMessage)
        and m.tool_call_id == old_ids[-1]
        and m.status == "error"
        for m in state.values["messages"]
    )

    history = AsyncMock(spec=HistoryStorePort)
    history.next_rank.return_value = 13
    await _write_turn_history(
        session_id=config.session_id,
        user_id="alice",
        request_message="Read the correct file",
        exchange_id="current-exchange",
        payloads=[e.model_dump(mode="json") for e in events],
        history_store=history,
    )
    history.save.assert_awaited_once()
    saved = history.save.call_args.kwargs["messages"]
    reloaded = [ChatMessage.model_validate_json(m.model_dump_json()) for m in saved]
    assert all(m.exchange_id == "current-exchange" for m in reloaded)
    assert [m.rank for m in reloaded] == list(range(13, 13 + len(reloaded)))
    assert [
        p.call_id for m in reloaded for p in m.parts if isinstance(p, ToolCallPart)
    ] == ["new-list", "new-read"]
    assert [
        (p.call_id, p.ok, p.latency_ms)
        for m in reloaded
        for p in m.parts
        if isinstance(p, ToolResultPart)
    ] == [(e.call_id, not e.is_error, e.latency_ms) for e in results]


class _StreamingModel(Model):
    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # opaque: LangChain provider invocation parameters
    ) -> AsyncIterator[ChatGenerationChunk]:
        self.calls.append(list(messages))
        yield ChatGenerationChunk(message=AIMessageChunk(content=ANSWER))
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                usage_metadata=USAGE,
                response_metadata={
                    "model_name": "offline-model",
                    "finish_reason": "stop",
                },
            )
        )


class _RecordingAgent:
    def __init__(self, graph: CompiledReActAgent) -> None:
        self.graph = graph
        self.model_updates: list[object] = []

    async def ainvoke(
        self,
        input: object,
        *,
        config: Mapping[str, object] | None = None,
        durability: str = "async",
    ) -> dict[str, list[BaseMessage]]:
        return await self.graph.ainvoke(input, config=config, durability=durability)

    async def astream(
        self,
        input: object,
        *,
        config: Mapping[str, object] | None = None,
        stream_mode: str | list[str],
        subgraphs: bool = False,
        durability: str = "async",
    ) -> AsyncIterator[object]:
        async for raw in self.graph.astream(
            input,
            config=config,
            stream_mode=stream_mode,
            subgraphs=subgraphs,
            durability=durability,
        ):
            mode, update = split_stream_event_mode(raw)
            if mode == "updates" and isinstance(update, dict) and "model" in update:
                self.model_updates.append(update["model"])
            yield raw


@pytest.mark.asyncio
@pytest.mark.parametrize("pinned", [False, True])
async def test_native_deep_pin_preserves_stream_completion(
    tmp_path: Path, pinned: bool
) -> None:
    publish(tmp_path, "example")
    skills = PlatformSkills.from_directory(str(tmp_path))
    bound = binding("example" if pinned else None)
    model = _StreamingModel()
    graph = compiled(model, skills, bound, True)
    recording = _RecordingAgent(graph)
    span = Mock(spec=SpanPort)
    tracer = Mock(spec=TracerPort, captures_content=True)
    tracer.start_span.return_value = span
    executor = _TransportBackedReActExecutor(
        compiled_agent=recording,
        binding=bound,
        services=RuntimeServices(skills=skills, tracer=tracer),
        runtime_class_name="Deep",
        preload_selected_skill=False,
    )
    config = ExecutionConfig(session_id="offline-pinned-completion")
    events = [
        event
        async for event in executor.stream(
            ReActInput(
                messages=(
                    ReActMessage(role=ReActMessageRole.USER, content="Draw the flow"),
                )
            ),
            config,
        )
    ]

    assert (
        "".join(e.delta for e in events if isinstance(e, AssistantDeltaRuntimeEvent))
        == ANSWER
    )
    finals = [event for event in events if isinstance(event, FinalRuntimeEvent)]
    assert len(finals) == 1
    assert finals[0].content == ANSWER
    assert finals[0].token_usage is not None
    assert {key: finals[0].token_usage[key] for key in USAGE} == USAGE
    assert finals[0].finish_reason == "stop"
    assert [
        c.kwargs["output"] for c in span.set_io.call_args_list if "output" in c.kwargs
    ] == [ANSWER]
    span.set_usage.assert_called_once_with(
        model="offline-model", usage={"input": 11, "output": 7, "total": 18}
    )
    span.end.assert_called_once()
    assert len(model.calls) == len(recording.model_updates) == 1
    assert isinstance(recording.model_updates[0], list if pinned else dict)
    extracted = extract_messages_from_update({"model": recording.model_updates[0]})
    assert (
        len([message for message in extracted if isinstance(message, AIMessage)]) == 1
    )
    state = await graph.aget_state({"configurable": {"thread_id": config.session_id}})
    assert state.values.get("pinned_skills", []) == []
    assert state.values["fred_pending_skill_names"] == []
    assert [
        m.content
        for m in state.values["messages"]
        if m.type == "human" and m.additional_kwargs.get("lc_source") != "pinned_skill"
    ] == ["Draw the flow"]
    pins = [
        m
        for m in state.values["messages"]
        if m.additional_kwargs.get("lc_source") == "pinned_skill"
    ]
    loads = [
        e
        for e in events
        if isinstance(e, StatusRuntimeEvent) and e.skill_load is not None
    ]
    assert len(pins) == len(loads) == int(pinned)
    if pinned:
        assert pins[0].additional_kwargs["skill"]["name"] == "example"
        assert loads[0].skill_load is not None
        assert loads[0].skill_load.origin == "user"


class _OverflowModel(Model):
    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # opaque: LangChain provider invocation parameters
    ) -> ChatResult:
        self.calls.append(list(messages))
        if len(self.calls) == 1:
            answer = AIMessage(
                content="",
                tool_calls=[{"name": "large_result", "args": {}, "id": "large-call"}],
            )
        elif len(self.calls) == 2:
            raise ContextOverflowError("synthetic context overflow")
        else:
            answer = AIMessage(
                content=ANSWER,
                usage_metadata=USAGE,
                response_metadata={
                    "model_name": "offline-model",
                    "finish_reason": "stop",
                },
            )
        return ChatResult(generations=[ChatGeneration(message=answer)])


@pytest.mark.asyncio
async def test_native_context_clipping_does_not_replay_tool_execution() -> None:
    original_content = "synthetic line\n" * 1200

    @tool
    def large_result() -> str:
        """Return a synthetic long tool result."""
        return original_content

    model = _OverflowModel()
    graph = create_deep_agent(model, tools=[large_result], backend=StateBackend())
    recording = _RecordingAgent(cast(CompiledReActAgent, graph))
    span = Mock(spec=SpanPort)
    tracer = Mock(spec=TracerPort, captures_content=True)
    tracer.start_span.return_value = span
    executor = _TransportBackedReActExecutor(
        compiled_agent=recording,
        binding=binding(),
        services=RuntimeServices(tracer=tracer),
        runtime_class_name="Deep",
        preload_selected_skill=False,
    )
    events = [
        event
        async for event in executor.stream(
            ReActInput(
                messages=(
                    ReActMessage(role=ReActMessageRole.USER, content="Inspect it"),
                )
            ),
            ExecutionConfig(session_id="offline-clipped-tool-result"),
        )
    ]

    assert len(model.calls) == 3
    original = next(m for m in model.calls[1] if isinstance(m, ToolMessage))
    replacement = next(m for m in model.calls[2] if isinstance(m, ToolMessage))
    assert original.id == replacement.id
    assert original.tool_call_id == replacement.tool_call_id == "large-call"
    assert original.content == original_content
    assert len(str(replacement.content)) < len(original_content)
    model_update = recording.model_updates[-1]
    assert isinstance(model_update, list)
    # factory._build_commands emits the response before native context patches.
    message_batches = [
        part["messages"]
        for part in model_update
        if isinstance(part, dict) and isinstance(part.get("messages"), list)
    ]
    assert len(message_batches) == 2
    assert isinstance(message_batches[0][0], AIMessage)
    assert message_batches[1] == [replacement]
    assert extract_messages_from_update({"model": model_update}) == message_batches[0]
    tool_results = [e for e in events if isinstance(e, ToolResultRuntimeEvent)]
    assert [(e.call_id, e.content) for e in tool_results] == [
        ("large-call", original_content)
    ]
    finals = [e for e in events if isinstance(e, FinalRuntimeEvent)]
    assert len(finals) == 1
    assert finals[0].content == ANSWER
    assert finals[0].token_usage is not None
    assert {key: finals[0].token_usage[key] for key in USAGE} == USAGE
    assert [
        c.kwargs["output"] for c in span.set_io.call_args_list if "output" in c.kwargs
    ] == [ANSWER]
    span.set_usage.assert_called_once_with(
        model="offline-model", usage={"input": 11, "output": 7, "total": 18}
    )


@pytest_asyncio.fixture(autouse=True)
async def admitted_unit_turn():
    """Compiled-loop proofs run under a synthetic Weaver turn authority."""
    from test_platform_skills import binding
    from weaver_fixtures import active_turn

    with active_turn(binding()):
        yield

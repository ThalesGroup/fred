# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Native context patches retain stream completion without replaying tool results."""

from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import pytest
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from fred_runtime.react.react_model_adapter import CompiledReActAgent
from fred_runtime.react.react_runtime import _TransportBackedReActExecutor
from fred_runtime.react.react_stream_adapter import (
    extract_messages_from_update,
    split_stream_event_mode,
)
from fred_runtime.skills.catalog import PlatformSkills
from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_sdk.contracts.runtime import (
    AssistantDeltaRuntimeEvent,
    ExecutionConfig,
    FinalRuntimeEvent,
    RuntimeServices,
    SpanPort,
    StatusRuntimeEvent,
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
from langchain_core.tools import tool
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
        self, input: object, *, config: Mapping[str, object] | None = None
    ) -> dict[str, list[BaseMessage]]:
        return await self.graph.ainvoke(input, config=config)

    async def astream(
        self,
        input: object,
        *,
        config: Mapping[str, object] | None = None,
        stream_mode: str | list[str],
        subgraphs: bool = False,
    ) -> AsyncIterator[object]:
        async for raw in self.graph.astream(
            input, config=config, stream_mode=stream_mode, subgraphs=subgraphs
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

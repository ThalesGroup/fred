# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Root trace inputs preserve the question and Deep's actual graph selections."""

import json
from collections.abc import AsyncIterator, Mapping
from operator import add
from typing import Annotated, TypedDict, cast
from unittest.mock import Mock

import pytest
from fred_runtime.integrations.v2_runtime.adapters import LangfuseTracerAdapter
from fred_runtime.react import react_runtime
from fred_runtime.react.react_runtime import _TransportBackedReActExecutor
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_sdk.contracts.runtime import ExecutionConfig, RuntimeServices
from fred_sdk.contracts.skills import SkillInvocation
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langfuse import Langfuse
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, Overwrite, StreamMode, interrupt
from test_langfuse_tracing import _FakeLangfuse


class _State(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    pinned_skills: Annotated[list[str], add]
    pause: bool


class _RecordingGraph:
    def __init__(self, graph: CompiledStateGraph[_State, None, _State, _State]) -> None:
        self.graph = graph
        self.inputs: list[object] = []

    async def ainvoke(
        self, input: object, *, config: Mapping[str, object] | None = None
    ) -> dict[str, list[BaseMessage]]:
        self.inputs.append(input)
        result = await self.graph.ainvoke(
            cast(_State | Command, input),
            config=cast(RunnableConfig, config),
        )
        return {"messages": result["messages"]}

    async def astream(
        self,
        input: object,
        *,
        config: Mapping[str, object] | None = None,
        stream_mode: str | list[str],
        subgraphs: bool = False,
    ) -> AsyncIterator[object]:
        self.inputs.append(input)
        async for event in self.graph.astream(
            cast(_State | Command, input),
            config=cast(RunnableConfig, config),
            stream_mode=cast(StreamMode | list[StreamMode], stream_mode),
            subgraphs=subgraphs,
        ):
            yield event


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("capture", [False, True])
@pytest.mark.parametrize(
    ("deep", "names", "resume"),
    [
        (True, ("second", "first", "second"), False),
        (True, (), False),
        (True, ("second", "first"), True),
        (False, (), False),
    ],
)
async def test_root_trace_input_matches_graph_selections(
    streaming: bool,
    capture: bool,
    deep: bool,
    names: tuple[str, ...],
    resume: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[list[str]] = []

    def answer(state: _State) -> dict[str, object]:
        if state.get("pause"):
            interrupt("Continue?")
        observed.append(list(state.get("pinned_skills", [])))
        return {"messages": [AIMessage(content="answer")]}

    builder = StateGraph(_State)
    builder.add_node("answer", answer)
    builder.add_edge(START, "answer")
    builder.add_edge("answer", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    config = ExecutionConfig(session_id="trace-input")
    if resume:
        graph_config: RunnableConfig = {
            "configurable": {"thread_id": config.session_id}
        }
        await graph.ainvoke(
            {
                "messages": [HumanMessage(content="previous")],
                "pause": True,
                "pinned_skills": ["previous"],
            },
            config=graph_config,
        )
        state = await graph.aget_state(graph_config)
        config = config.model_copy(
            update={
                "resume_payload": "continue",
                "interrupt_id": state.tasks[0].interrupts[0].id,
            }
        )
    recording_graph = _RecordingGraph(graph)
    client = _FakeLangfuse()
    tracer = LangfuseTracerAdapter(cast(Langfuse, client), capture_content=capture)
    binding = BoundRuntimeContext(
        runtime_context=RuntimeContext(
            skills=[SkillInvocation(name=name) for name in names]
        ),
        portable_context=PortableContext(
            request_id="request",
            correlation_id="correlation",
            actor="user",
            tenant="team",
            environment=PortableEnvironment.DEV,
            agent_id="test",
        ),
    )
    executor = _TransportBackedReActExecutor(
        compiled_agent=recording_graph,
        binding=binding,
        services=RuntimeServices(tracer=tracer),
        runtime_class_name="Deep" if deep else "ReAct",
        preload_selected_skill=not deep,
    )
    payload = Mock(wraps=react_runtime._trace_input_payload)
    monkeypatch.setattr(react_runtime, "_trace_input_payload", payload)
    input_model = ReActInput(
        messages=(
            ReActMessage(role=ReActMessageRole.USER, content="earlier question"),
            ReActMessage(role=ReActMessageRole.ASSISTANT, content="earlier answer"),
            ReActMessage(role=ReActMessageRole.USER, content="canonical question"),
        )
    )

    if streaming:
        events = [event async for event in executor.stream(input_model, config)]
        assert events
    else:
        assert (
            await executor.invoke(input_model, config)
        ).final_message.content == "answer"

    assert observed == [([] if resume else list(dict.fromkeys(names)))]
    assert len(recording_graph.inputs) == 1
    assert len(client.start_kwargs) == 1
    assert client.start_kwargs[0]["name"] == (
        "agent.stream" if streaming else "agent.invoke"
    )
    assert client.start_kwargs[0]["as_type"] == "agent"
    observation = client.observations[0]
    assert len(observation.updates) == (1 if capture else 0)
    update_payload = observation.updates[0] if observation.updates else {}
    metadata = {
        **client.start_kwargs[0]["metadata"],
        **update_payload.get("metadata", {}),
    }
    if capture:
        if deep:
            raw_input = recording_graph.inputs[0]
            update = raw_input.update if isinstance(raw_input, Command) else raw_input
            pins = cast(dict[str, Overwrite], update)["pinned_skills"].value
            expected = {"question": "canonical question", "pinned_skills": pins}
            assert update_payload["input"] == expected
            assert metadata["pinned_skills"] == observed[0] == pins
            assert (
                json.loads(observation._otel_span.attributes["langfuse.trace.input"])
                == expected
            )
        else:
            assert update_payload["input"] == "canonical question"
            assert "pinned_skills" not in metadata
            assert (
                observation._otel_span.attributes["langfuse.trace.input"]
                == "canonical question"
            )
        payload.assert_called_once()
    else:
        assert "input" not in update_payload and "output" not in update_payload
        assert "pinned_skills" not in metadata
        assert "langfuse.trace.input" not in observation._otel_span.attributes
        payload.assert_not_called()
    assert observation.ended

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
A run that loses its authority ends, typed, in both engines.

What is pinned here:
- the run ends on the terminal error event carrying the machine-readable
  reason, and the engine's own generator completes instead of raising
- the failure is never handed back to the model as tool text, and nothing is
  retried
- children and in-flight parallel work are cancelled with the run
- the upstream error body reaches no sink: not the transcript, not a log, not a
  span, not a checkpoint, not a streamed event — for the parent and for a child

The canary is a marker string planted in the upstream error body. Every
assertion below is "the marker is nowhere", so the tests fail the moment any
path copies upstream text instead of the platform's own sentence.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, NoReturn, cast

import pytest
from fred_core.portable import (
    InMemoryMetricsProvider,
    Span,
    TimerRecord,
    Tracer,
)
from fred_core.security.delegation import DelegationConfig
from fred_runtime.app.agent_app import LocalRegistryAgentInvoker
from fred_runtime.common.outbound_credentials import (
    DelegationRuntime,
    set_delegation_runtime,
)
from fred_runtime.graph.graph_runtime import GraphRuntime
from fred_runtime.react.react_runtime import _TransportBackedReActExecutor
from fred_runtime.react.react_tool_loop import build_tool_loop_compiled_react_agent
from fred_runtime.runtime_context import (
    RuntimeConfig,
    set_runtime_context,
)
from fred_runtime.runtime_context import (
    RuntimeContext as FredRuntimeContext,
)
from fred_runtime.runtime_support.authority import AuthorityLostError
from fred_runtime.runtime_support.run_budget import RunScope, register_run_child
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import (
    GraphAgentDefinition,
    GraphDefinition,
    GraphEdgeDefinition,
    GraphNodeDefinition,
    ReActAgentDefinition,
    ToolApprovalPolicy,
)
from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_sdk.contracts.runtime import (
    ExecutionConfig,
    FinalRuntimeEvent,
    NodeErrorRuntimeEvent,
    RuntimeErrorEvent,
    RuntimeEvent,
    RuntimeServices,
    RuntimeStopReason,
    ToolResultRuntimeEvent,
)
from fred_sdk.graph.runtime import GraphNodeResult
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Checkpointer
from pydantic import BaseModel, Field


@contextmanager
def delegated_logging_context() -> Iterator[None]:
    set_delegation_runtime(
        DelegationRuntime(
            config=DelegationConfig(enabled=True, allowed_callers=["runtime"])
        )
    )
    try:
        yield
    finally:
        set_delegation_runtime(None)


# The receiver's response body. Nothing the platform emits may contain it.
MARKER = "canary-upstream-body-9f3a"


def raise_authority_lost() -> NoReturn:
    """Raise what an outbound call site raises on a refused delegated call: the
    platform's own error, with the receiver's response kept only as the chained
    cause — which is where `logger.exception` would find and print it."""

    try:
        raise RuntimeError(f"403 Forbidden: {MARKER}")
    except RuntimeError as upstream:
        raise AuthorityLostError() from upstream


def raise_authority_lost_carrying_body() -> NoReturn:
    """A call site that folds the receiver's body into the platform error. The
    engines must still not let that text out: the sentence a stopped run shows
    comes from the reason, never from the error it was given."""

    raise AuthorityLostError(f"403 Forbidden: {MARKER}")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


class _LogSink(logging.Handler):
    """Collects every record's text, tracebacks included — `logger.exception`
    puts the chained upstream error in the traceback, not in the message."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.texts: list[str] = []
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        text = record.getMessage()
        if record.exc_info:
            text += "".join(traceback.format_exception(*record.exc_info))
        self.texts.append(text)

    def payload_text(self) -> str:
        return repr([record.__dict__ for record in self.records]) + "".join(self.texts)


@contextmanager
def capture_logs() -> Iterator[_LogSink]:
    sink = _LogSink()
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(sink)
    root.setLevel(logging.DEBUG)
    try:
        yield sink
    finally:
        root.removeHandler(sink)
        root.setLevel(previous_level)


class RecordingSpan(Span):
    """A span that keeps everything written to it, so the trace sink can be
    asserted on like any other."""

    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}
        self.io: list[object] = []
        self.ended = 0

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value

    def set_io(self, **kwargs: object) -> None:
        self.io.append(kwargs)

    def end(self) -> None:
        self.ended += 1

    def text(self) -> str:
        return repr(self.attributes) + repr(self.io)


class RecordingTracer(Tracer):
    """Captures content, like a backend configured to record payloads — the
    setting under which a leak would actually reach a trace."""

    def __init__(self) -> None:
        self.spans: list[RecordingSpan] = []

    @property
    def captures_content(self) -> bool:
        return True

    def start_span(
        self,
        name: str,
        *,
        context: object | None = None,
        attributes: Mapping[str, object] | None = None,
        parent: Span | None = None,
        **kwargs: object,
    ) -> RecordingSpan:
        del name, context, attributes, parent, kwargs
        span = RecordingSpan()
        self.spans.append(span)
        return span

    def text(self) -> str:
        return "".join(span.text() for span in self.spans)


def binding(agent_id: str = "agent-stop") -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(session_id="s", user_id="u", team_id="t"),
        portable_context=PortableContext(
            request_id="r",
            correlation_id="c",
            actor="u",
            tenant="t",
            environment=PortableEnvironment.DEV,
            agent_id=agent_id,
            session_id="s",
            user_id="u",
            team_id="t",
        ),
    )


def closable(stream: AsyncIterator[RuntimeEvent]) -> AsyncGenerator[RuntimeEvent, None]:
    """
    An engine stream as the async generator it is.

    Closing it is what unwinds the turn's `finally` block, so a stream that
    could not be closed would make every abandonment test below silently prove
    nothing — hence the check rather than a cast.
    """

    assert isinstance(stream, AsyncGenerator), (
        "an engine stream must be closable to be abandoned"
    )
    return stream


async def abandon(stream: AsyncIterator[RuntimeEvent]) -> None:
    """Finalize a stream its consumer walked away from the way the server does:
    from a task of its own, so the context the turn set its variables on is not
    the one resetting them."""

    await asyncio.create_task(closable(stream).aclose())


def phase_sample(metrics: InMemoryMetricsProvider, phase: str) -> TimerRecord:
    """The one `app.phase_latency_ms` sample a turn emits for a given phase.
    A sample is written on the way out, so its absence means a finally block
    never got there."""

    samples = [
        timer
        for timer in metrics.timers
        if timer.name == "app.phase_latency_ms" and timer.dims.get("phase") == phase
    ]
    assert len(samples) == 1, f"expected one {phase} sample: {metrics.timers}"
    return samples[0]


def events_text(events: list[RuntimeEvent]) -> str:
    return "".join(repr(event.model_dump(mode="json")) for event in events)


def checkpoint_text(saver: InMemorySaver) -> str:
    """Everything the checkpointer actually persisted, as it persisted it —
    serialized with the same serde the production checkpointer uses."""

    chunks: list[bytes] = []
    for writes in saver.writes.values():
        for _task_id, _channel, (_kind, blob), _path in writes.values():
            chunks.append(blob)
    for blob in saver.blobs.values():
        chunks.append(blob if isinstance(blob, bytes) else repr(blob).encode())
    for thread in saver.storage.values():
        chunks.append(repr(thread).encode())
    return repr(chunks)


def stored_checkpoints(saver: InMemorySaver) -> int:
    """How many checkpoints were actually written. `storage` is a defaultdict,
    so a mere lookup creates its keys — counting them would prove nothing."""

    return sum(
        len(checkpoints)
        for namespaces in saver.storage.values()
        for checkpoints in namespaces.values()
    )


def terminal_event(events: list[RuntimeEvent]) -> RuntimeErrorEvent:
    errors = [event for event in events if isinstance(event, RuntimeErrorEvent)]
    assert len(errors) == 1, f"expected exactly one terminal error event: {events}"
    assert errors[-1] is events[-1], "the terminal event must be the last one"
    return errors[0]


# ---------------------------------------------------------------------------
# ReAct engine — scripted stream
# ---------------------------------------------------------------------------


class _ObservedStream:
    """Wraps a real async generator so `aclose` is observable while the
    iteration protocol stays the library's own."""

    def __init__(self, inner: AsyncIterator[object]) -> None:
        self._inner = inner
        self.closed = 0

    def __aiter__(self) -> _ObservedStream:
        return self

    async def __anext__(self) -> object:
        return await self._inner.__anext__()  # type: ignore[union-attr]

    async def aclose(self) -> None:
        self.closed += 1
        aclose = getattr(self._inner, "aclose", None)
        if aclose is not None:
            await aclose()


class _ScriptedCompiledAgent:
    """
    Streams one tool round, starts a child, then loses authority.

    The child here is a task registered on the run's scope, which is what a
    spawn path that starts work in its own task has to do (see
    `run_budget.register_run_child`). A child the run merely awaits inline —
    what the in-process agent invoker does today — needs no registration:
    closing this stream unwinds it, which `closed` below covers.
    """

    def __init__(self, raiser: Callable[[], NoReturn] = raise_authority_lost) -> None:
        self.streams: list[_ObservedStream] = []
        self.child: asyncio.Task[None] | None = None
        self._raiser = raiser

    def astream(self, *_args: object, **_kwargs: object) -> _ObservedStream:
        async def _generate() -> AsyncIterator[object]:
            yield (
                "updates",
                {
                    "model": {
                        "messages": [
                            AIMessage(
                                content="",
                                tool_calls=[
                                    {"id": "call-1", "name": "search", "args": {}}
                                ],
                            )
                        ]
                    }
                },
            )
            self.child = asyncio.ensure_future(asyncio.sleep(3600))
            assert register_run_child(cast(Any, self.child)), (
                "the engine must open a run scope"
            )
            await asyncio.sleep(0)
            self._raiser()

        stream = _ObservedStream(_generate())
        self.streams.append(stream)
        return stream


async def _run_react_stream(
    agent: object, *, services: RuntimeServices | None = None
) -> list[RuntimeEvent]:
    executor = _TransportBackedReActExecutor(
        compiled_agent=cast(Any, agent),
        binding=binding(),
        services=services if services is not None else RuntimeServices(),
        runtime_class_name="ReActRuntime",
    )
    input_model = ReActInput(
        messages=(ReActMessage(role=ReActMessageRole.USER, content="hi"),)
    )
    collected: list[RuntimeEvent] = []
    async for event in executor.stream(input_model, ExecutionConfig(session_id="s")):
        collected.append(event)
    return collected


@pytest.mark.asyncio
async def test_react_authority_loss_ends_the_run_typed_and_cancels_children() -> None:
    agent = _ScriptedCompiledAgent()

    events = await _run_react_stream(agent)

    terminal = terminal_event(events)
    assert terminal.reason is RuntimeStopReason.AUTHORITY_LOST
    assert MARKER not in terminal.message
    # The model is never asked to relay the stop, and the turn has no answer.
    assert not any(isinstance(event, FinalRuntimeEvent) for event in events)
    # No retry: the engine ran the compiled agent exactly once.
    assert len(agent.streams) == 1
    # Closing the stream is what cancels the work the run awaits inline —
    # in-flight parallel tool calls, and child agents the invoker awaits.
    assert agent.streams[0].closed >= 1
    # A child running in its own task goes with the run only if it was
    # registered on the scope.
    assert agent.child is not None
    await asyncio.sleep(0)
    assert agent.child.cancelled()


@pytest.mark.asyncio
async def test_react_cancels_registered_children_before_the_terminal_event() -> None:
    """Covers the scope's own contract: a task registered as a child is
    cancelled when the run reports how it ended, not later, when the generator
    happens to be finalized."""

    agent = _ScriptedCompiledAgent()
    executor = _TransportBackedReActExecutor(
        compiled_agent=cast(Any, agent),
        binding=binding(),
        services=RuntimeServices(),
        runtime_class_name="ReActRuntime",
    )
    input_model = ReActInput(
        messages=(ReActMessage(role=ReActMessageRole.USER, content="hi"),)
    )

    cancel_requests_at_terminal: int | None = None
    async for event in executor.stream(input_model, ExecutionConfig(session_id="s")):
        if isinstance(event, RuntimeErrorEvent):
            assert agent.child is not None
            cancel_requests_at_terminal = agent.child.cancelling()

    # The child is already cancelled when the run reports how it ended, not
    # merely by the time the generator is finalized.
    assert cancel_requests_at_terminal == 1


class _HangingCompiledAgent:
    """Streams one tool round and then keeps working — a turn a consumer can
    walk away from."""

    def astream(self, *_args: object, **_kwargs: object) -> AsyncIterator[object]:
        async def _generate() -> AsyncIterator[object]:
            yield (
                "updates",
                {
                    "model": {
                        "messages": [
                            AIMessage(
                                content="",
                                tool_calls=[
                                    {"id": "call-1", "name": "search", "args": {}}
                                ],
                            )
                        ]
                    }
                },
            )
            await asyncio.sleep(30)

        return _generate()


class _HealthyCompiledAgent:
    """One answer, no tools."""

    def astream(self, *_args: object, **_kwargs: object) -> AsyncIterator[object]:
        async def _generate() -> AsyncIterator[object]:
            yield ("updates", {"model": {"messages": [AIMessage(content="all good")]}})

        return _generate()


@pytest.mark.asyncio
async def test_an_abandoned_stream_does_not_poison_the_next_run() -> None:
    """A stream the consumer walks away from leaves its scope visible on that
    task's context. The next turn must not inherit the abandoned run's budget."""

    from fred_runtime.runtime_support.run_budget import configure_run_limits

    try:
        configure_run_limits(wall_clock_seconds=0.2)
        executor = _TransportBackedReActExecutor(
            compiled_agent=cast(Any, _HangingCompiledAgent()),
            binding=binding(),
            services=RuntimeServices(),
            runtime_class_name="ReActRuntime",
        )
        stream = executor.stream(
            ReActInput(
                messages=(ReActMessage(role=ReActMessageRole.USER, content="hi"),)
            ),
            ExecutionConfig(session_id="s"),
        )
        seen = 0
        async for _event in stream:
            seen += 1
            if seen == 2:
                break
        await abandon(stream)
        # The abandoned run's budget is now spent.
        await asyncio.sleep(0.25)

        configure_run_limits(wall_clock_seconds=30.0)
        events = await _run_react_stream(_HealthyCompiledAgent())

        assert any(isinstance(event, FinalRuntimeEvent) for event in events)
        assert not any(isinstance(event, RuntimeErrorEvent) for event in events)
    finally:
        configure_run_limits()


@pytest.mark.asyncio
async def test_an_abandoned_stream_still_closes_the_turns_kpi_timer_and_span() -> None:
    """Ending the run comes first in the turn's finally block, and resetting a
    context variable from the task that finalizes the generator raises. What the
    turn still owes its sinks — the phase KPI, the span — is written anyway."""

    metrics = InMemoryMetricsProvider()
    tracer = RecordingTracer()
    executor = _TransportBackedReActExecutor(
        compiled_agent=cast(Any, _HangingCompiledAgent()),
        binding=binding(),
        services=RuntimeServices(metrics=cast(Any, metrics), tracer=cast(Any, tracer)),
        runtime_class_name="ReActRuntime",
    )
    stream = executor.stream(
        ReActInput(messages=(ReActMessage(role=ReActMessageRole.USER, content="hi"),)),
        ExecutionConfig(session_id="s"),
    )
    seen = 0
    async for _event in stream:
        seen += 1
        if seen == 2:
            break
    await abandon(stream)

    assert phase_sample(metrics, "react_stream")
    assert tracer.spans
    assert all(span.ended == 1 for span in tracer.spans)


@pytest.mark.asyncio
async def test_react_phase_sample_names_the_stop_rather_than_a_healthy_call() -> None:
    """The turn's latency sample is read as success-or-failure. A stopped run
    that leaves it saying `ok` puts a run that went as far as the ceiling into
    the healthy histogram and shows no failure at all."""

    metrics = InMemoryMetricsProvider()

    await _run_react_stream(
        _ScriptedCompiledAgent(), services=RuntimeServices(metrics=metrics)
    )

    sample = phase_sample(metrics, "react_stream")
    assert sample.dims["status"] == "error"
    assert sample.dims["error_code"] == RuntimeStopReason.AUTHORITY_LOST.value


@pytest.mark.asyncio
async def test_react_phase_sample_for_a_turn_that_answered_still_says_ok() -> None:
    metrics = InMemoryMetricsProvider()

    await _run_react_stream(
        _HealthyCompiledAgent(), services=RuntimeServices(metrics=metrics)
    )

    sample = phase_sample(metrics, "react_stream")
    assert sample.dims["status"] == "ok"
    assert "error_code" not in sample.dims


@pytest.mark.asyncio
async def test_a_turn_that_fails_before_streaming_leaves_no_open_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scope opens before the stream is built, and building it runs the
    turn's own input translation. A failure there must still close the scope,
    or the next turn on this task inherits a spent budget."""

    def _refuse(*_args: object, **_kwargs: object) -> NoReturn:
        raise RuntimeError("input translation failed")

    monkeypatch.setattr("fred_runtime.react.react_runtime._graph_input", _refuse)
    executor = _TransportBackedReActExecutor(
        compiled_agent=cast(Any, _HealthyCompiledAgent()),
        binding=binding(),
        services=RuntimeServices(),
        runtime_class_name="ReActRuntime",
    )

    with pytest.raises(RuntimeError, match="input translation failed") as failure:
        async for _event in executor.stream(
            ReActInput(
                messages=(ReActMessage(role=ReActMessageRole.USER, content="hi"),)
            ),
            ExecutionConfig(session_id="s"),
        ):
            pass

    # Holding the traceback keeps the turn's frame, and the scope it opened,
    # alive: without it a garbage collection would close the scope for us and
    # this would pass whether or not the turn closed its own.
    assert failure.traceback
    leaked = RunScope.current()
    assert leaked is None or leaked.closed


@pytest.mark.asyncio
async def test_react_pending_tool_rows_are_closed_without_upstream_text() -> None:
    agent = _ScriptedCompiledAgent()

    events = await _run_react_stream(agent)

    closing_results = [
        event
        for event in events
        if isinstance(event, ToolResultRuntimeEvent) and event.call_id == "call-1"
    ]
    assert closing_results, "the open tool row must be closed"
    assert all(result.content == "" for result in closing_results)
    assert MARKER not in events_text(events)


# ---------------------------------------------------------------------------
# ReAct engine — the real `create_agent` loop, with the platform frame
# ---------------------------------------------------------------------------


class _ScriptedModel(BaseChatModel):
    """Deterministic model that records every input it is given, so a tool
    failure fed back as text is visible as a second call."""

    script: list[AIMessage] = Field(default_factory=list)
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-stop"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_ScriptedModel":
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        message = self.script.pop(0) if self.script else AIMessage(content="done")
        return ChatResult(generations=[ChatGeneration(message=message)])


@tool
def protected_search(query: str) -> str:
    """Search a receiver that has just refused the run's authority."""

    del query
    raise_authority_lost()


@tool
def protected_search_leaky(query: str) -> str:
    """Search a receiver, from a call site that hands the error the body."""

    del query
    raise_authority_lost_carrying_body()


class _FakeReActDefinition:
    agent_id = "agent-stop"


@dataclass
class _RealLoopRun:
    """One run of the real `create_agent` loop, with every sink it wrote to."""

    events: list[RuntimeEvent]
    logs: _LogSink
    tracer: RecordingTracer
    saver: InMemorySaver
    model: _ScriptedModel

    def transcript(self) -> str:
        return "".join(repr(message) for call in self.model.calls for message in call)


async def _run_real_react_loop(tool_obj: Any) -> _RealLoopRun:
    """Drive the platform middleware frame and LangGraph itself, with a real
    checkpointer and a content-capturing tracer behind it."""

    model = _ScriptedModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": tool_obj.name,
                        "args": {"query": "q"},
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            )
        ]
    )
    saver = InMemorySaver()
    tracer = RecordingTracer()
    compiled = build_tool_loop_compiled_react_agent(
        model=model,
        tools=[tool_obj],
        system_prompt="SYS.",
        binding=binding(),
        approval_policy=ToolApprovalPolicy(enabled=False),
        checkpointer=cast(Checkpointer, saver),
        definition=cast(ReActAgentDefinition, _FakeReActDefinition()),
        available_tool_names={tool_obj.name},
    )

    with capture_logs() as logs:
        events = await _run_react_stream(
            compiled, services=RuntimeServices(tracer=cast(Any, tracer))
        )
    return _RealLoopRun(
        events=events, logs=logs, tracer=tracer, saver=saver, model=model
    )


@pytest.mark.asyncio
async def test_react_real_loop_never_turns_the_stop_into_tool_text() -> None:
    with delegated_logging_context():
        run = await _run_real_react_loop(protected_search)
    events, logs, tracer, saver, model = (
        run.events,
        run.logs,
        run.tracer,
        run.saver,
        run.model,
    )

    terminal = terminal_event(events)
    assert terminal.reason is RuntimeStopReason.AUTHORITY_LOST
    # The decisive one: a second model call would mean the failure was handed
    # back to the model as an ordinary tool result and the loop kept going.
    assert len(model.calls) == 1
    assert not any(isinstance(event, FinalRuntimeEvent) for event in events)

    # Canary, parent run: five sinks, one marker, nowhere.
    assert MARKER not in events_text(events)
    assert MARKER not in logs.payload_text()
    assert "agent-stop" not in logs.payload_text()
    assert MARKER not in tracer.text()
    assert MARKER not in checkpoint_text(saver)
    assert MARKER not in run.transcript()

    # The canary only means something while the sinks are live: the tracer
    # opened a span, and the checkpointer really did persist the failure — it
    # is the platform's error that is stored, not the receiver's.
    assert tracer.spans
    assert "AuthorityLostError" in checkpoint_text(saver)
    assert logs.texts


# ---------------------------------------------------------------------------
# Graph engine
# ---------------------------------------------------------------------------


class _GraphInput(BaseModel):
    message: str = ""


class _GraphState(BaseModel):
    message: str = ""
    node_error: str = ""
    visited: str = ""


class _StoppingGraphAgent(GraphAgentDefinition):
    """One node that loses authority, and an `on_error` fallback that must not
    run for a stopped run."""

    agent_id: str = "test.graph.stop"
    role: str = "test"
    description: str = "test"
    carry_body: bool = False
    stops: bool = True

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="State",
            entry_node="work",
            nodes=(
                GraphNodeDefinition(node_id="work", title="Work", on_error="recover"),
                GraphNodeDefinition(node_id="recover", title="Recover"),
            ),
        )

    def input_model(self) -> type[BaseModel]:
        return _GraphInput

    def state_model(self) -> type[BaseModel]:
        return _GraphState

    def output_model(self) -> type[BaseModel]:
        return _GraphInput

    def build_initial_state(
        self, input_model: BaseModel, binding: BoundRuntimeContext
    ) -> BaseModel:
        del binding
        return _GraphState(message=getattr(input_model, "message", ""))

    def node_handlers(self) -> Mapping[str, object]:
        carry_body = self.carry_body
        stops = self.stops

        async def _work(state: BaseModel, ctx: object) -> GraphNodeResult:
            del state, ctx
            if not stops:
                return GraphNodeResult(state_update={"visited": "work"})
            if carry_body:
                raise_authority_lost_carrying_body()
            raise_authority_lost()

        async def _recover(state: BaseModel, ctx: object) -> GraphNodeResult:
            del state, ctx
            return GraphNodeResult(state_update={"visited": "recover"})

        return {"work": _work, "recover": _recover}

    def build_output(self, state: BaseModel) -> BaseModel:
        return _GraphInput(message=getattr(state, "message", ""))


#: What the parallel members did. A definition is a frozen model, so the run's
#: observations live beside it.
PARALLEL_RUN: dict[str, bool] = {}


class _ParallelGraphAgent(GraphAgentDefinition):
    """A fan-out whose members are the run's children: one loses authority
    while the other is still working."""

    agent_id: str = "test.graph.parallel-stop"
    role: str = "test"
    description: str = "test"

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="State",
            entry_node="fan_out",
            nodes=(
                GraphNodeDefinition(node_id="fan_out", title="Fan out"),
                GraphNodeDefinition(node_id="child_stop", title="Child stop"),
                GraphNodeDefinition(node_id="child_busy", title="Child busy"),
                GraphNodeDefinition(node_id="fan_in", title="Fan in"),
                GraphNodeDefinition(node_id="done", title="Done"),
            ),
            edges=(GraphEdgeDefinition(source="fan_in", target="done"),),
            parallel_groups=(("fan_out", "fan_in", "child_stop", "child_busy"),),
        )

    def input_model(self) -> type[BaseModel]:
        return _GraphInput

    def state_model(self) -> type[BaseModel]:
        return _GraphState

    def output_model(self) -> type[BaseModel]:
        return _GraphInput

    def build_initial_state(
        self, input_model: BaseModel, binding: BoundRuntimeContext
    ) -> BaseModel:
        del binding
        return _GraphState(message=getattr(input_model, "message", ""))

    def node_handlers(self) -> Mapping[str, object]:
        async def _fan_out(state: BaseModel, ctx: object) -> GraphNodeResult:
            del state, ctx
            return GraphNodeResult()

        async def _child_stop(state: BaseModel, ctx: object) -> GraphNodeResult:
            del state, ctx
            await asyncio.sleep(0)
            raise_authority_lost()

        async def _child_busy(state: BaseModel, ctx: object) -> GraphNodeResult:
            del state, ctx
            PARALLEL_RUN["busy_started"] = True
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                PARALLEL_RUN["busy_cancelled"] = True
                raise
            return GraphNodeResult()

        async def _fan_in(state: BaseModel, ctx: object) -> GraphNodeResult:
            del state, ctx
            PARALLEL_RUN["fan_in_ran"] = True
            return GraphNodeResult()

        async def _done(state: BaseModel, ctx: object) -> GraphNodeResult:
            del state, ctx
            return GraphNodeResult()

        return {
            "fan_out": _fan_out,
            "child_stop": _child_stop,
            "child_busy": _child_busy,
            "fan_in": _fan_in,
            "done": _done,
        }

    def build_output(self, state: BaseModel) -> BaseModel:
        return _GraphInput(message=getattr(state, "message", ""))


async def _run_graph_stream(
    definition: GraphAgentDefinition,
    *,
    services: RuntimeServices,
) -> list[RuntimeEvent]:
    runtime = GraphRuntime(definition=definition, services=services)
    executor = await runtime.build_executor(binding(definition.agent_id))
    collected: list[RuntimeEvent] = []
    async for event in executor.stream(
        _GraphInput(message="hi"), ExecutionConfig(session_id="s")
    ):
        collected.append(event)
    return collected


@pytest.mark.asyncio
async def test_graph_authority_loss_ends_the_run_without_on_error_recovery() -> None:
    definition = _StoppingGraphAgent()
    saver = InMemorySaver()
    tracer = RecordingTracer()

    with capture_logs() as logs:
        events = await _run_graph_stream(
            definition,
            services=RuntimeServices(
                checkpointer=cast(Any, saver), tracer=cast(Any, tracer)
            ),
        )

    terminal = terminal_event(events)
    assert terminal.reason is RuntimeStopReason.AUTHORITY_LOST
    # `on_error` is a retry under an authority the platform has given up, and it
    # is what puts the failure text into graph state and the next prompt.
    assert not any(isinstance(event, NodeErrorRuntimeEvent) for event in events)
    assert not any(isinstance(event, FinalRuntimeEvent) for event in events)

    # Canary, parent run.
    assert MARKER not in events_text(events)
    assert MARKER not in logs.payload_text()
    assert definition.agent_id not in logs.payload_text()
    assert MARKER not in tracer.text()
    assert MARKER not in checkpoint_text(saver)
    assert tracer.spans
    # A stopped run persists nothing: no completed state, no pending state, so
    # nothing of the failure survives the turn.
    assert stored_checkpoints(saver) == 0


@pytest.mark.asyncio
async def test_graph_phase_sample_names_the_stop_rather_than_a_healthy_call() -> None:
    metrics = InMemoryMetricsProvider()

    await _run_graph_stream(
        _StoppingGraphAgent(), services=RuntimeServices(metrics=metrics)
    )

    sample = phase_sample(metrics, "v2_graph_node")
    assert sample.dims["status"] == "error"
    assert sample.dims["error_code"] == RuntimeStopReason.AUTHORITY_LOST.value


@pytest.mark.asyncio
async def test_graph_phase_sample_for_a_node_that_finished_still_says_ok() -> None:
    metrics = InMemoryMetricsProvider()

    await _run_graph_stream(
        _StoppingGraphAgent(stops=False), services=RuntimeServices(metrics=metrics)
    )

    sample = phase_sample(metrics, "v2_graph_node")
    assert sample.dims["status"] == "ok"
    assert "error_code" not in sample.dims


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", ["react", "graph", "react_real_loop"])
async def test_a_stop_carrying_a_body_still_reports_only_the_platform_sentence(
    engine: str,
) -> None:
    """A call site that hands the receiver's body to the platform error must
    not put it anywhere: the sentence comes from the reason, and the error's
    own text is the platform's."""

    saver: InMemorySaver | None = None
    tracer: RecordingTracer | None = None
    if engine == "react_real_loop":
        run = await _run_real_react_loop(protected_search_leaky)
        events, logs, saver, tracer = run.events, run.logs, run.saver, run.tracer
        assert MARKER not in run.transcript()
    else:
        with capture_logs() as captured:
            if engine == "react":
                events = await _run_react_stream(
                    _ScriptedCompiledAgent(raise_authority_lost_carrying_body)
                )
            else:
                events = await _run_graph_stream(
                    _StoppingGraphAgent(carry_body=True),
                    services=RuntimeServices(),
                )
        logs = captured

    terminal = terminal_event(events)
    assert terminal.reason is RuntimeStopReason.AUTHORITY_LOST
    assert MARKER not in terminal.message
    assert MARKER not in events_text(events)
    assert MARKER not in logs.payload_text()
    assert logs.texts
    if saver is not None and tracer is not None:
        # The real loop writes the failing task's exception into the
        # checkpoint, so this is where a body on the error would surface.
        assert MARKER not in checkpoint_text(saver)
        assert "AuthorityLostError" in checkpoint_text(saver)
        assert MARKER not in tracer.text()
        assert tracer.spans


# A receiver URL as an ordinary client error quotes it back. Under delegation
# the query string names the person, the run and the agent.
GRANT_PERSON = "person-6b21"
GRANT_RUN = "run-6b21"
GRANT_AGENT = "agent-6b21"
GRANT_URL = (
    "https://receiver.invalid/v1/documents"
    f"?person={GRANT_PERSON}&run={GRANT_RUN}&agent={GRANT_AGENT}&limit=5"
)


@tool
def leaky_receiver_call(query: str) -> str:
    """A receiver call that fails the ordinary way, quoting the request URL."""

    del query
    raise RuntimeError(f"Client error '403 Forbidden' for url '{GRANT_URL}'")


class _StaticToolProvider:
    """Hands the executor one runtime tool, the way the provider does."""

    def __init__(self, tools: tuple[Any, ...]) -> None:
        self._tools = tools

    def bind(self, binding: BoundRuntimeContext) -> None:
        del binding

    async def activate(self) -> None:
        return None

    def get_tools(self) -> tuple[Any, ...]:
        return self._tools

    async def aclose(self) -> None:
        return None


class _ToolCallingGraphAgent(GraphAgentDefinition):
    """
    One node that calls a runtime tool which fails the ordinary way.

    `failure_mode` picks which reader the failure text reaches: `swallow` keeps
    the node alive so its buffered tool row is streamed, `crash` lets the error
    end the run on the final event, `recover` routes it to a fallback node and
    into graph state.
    """

    agent_id: str = "test.graph.tool-error"
    role: str = "test"
    description: str = "test"
    failure_mode: str = "swallow"

    def build_graph(self) -> GraphDefinition:
        recovers = self.failure_mode == "recover"
        return GraphDefinition(
            state_model_name="State",
            entry_node="call_tool",
            nodes=(
                GraphNodeDefinition(
                    node_id="call_tool",
                    title="Call tool",
                    on_error="recover" if recovers else None,
                ),
                GraphNodeDefinition(node_id="recover", title="Recover"),
            ),
        )

    def input_model(self) -> type[BaseModel]:
        return _GraphInput

    def state_model(self) -> type[BaseModel]:
        return _GraphState

    def output_model(self) -> type[BaseModel]:
        return _GraphInput

    def build_initial_state(
        self, input_model: BaseModel, binding: BoundRuntimeContext
    ) -> BaseModel:
        del binding
        return _GraphState(message=getattr(input_model, "message", ""))

    def node_handlers(self) -> Mapping[str, object]:
        swallows = self.failure_mode == "swallow"

        async def _call_tool(state: BaseModel, ctx: Any) -> GraphNodeResult:
            del state
            try:
                await ctx.invoke_runtime_tool("leaky_receiver_call", {"query": "q"})
            except RuntimeError:
                if not swallows:
                    raise
            return GraphNodeResult()

        async def _recover(state: BaseModel, ctx: object) -> GraphNodeResult:
            del state, ctx
            return GraphNodeResult(state_update={"visited": "recover"})

        return {"call_tool": _call_tool, "recover": _recover}

    def build_output(self, state: BaseModel) -> BaseModel:
        return _GraphInput(message=getattr(state, "message", ""))


async def _run_leaky_tool_graph(failure_mode: str) -> list[RuntimeEvent]:
    return await _run_graph_stream(
        _ToolCallingGraphAgent(failure_mode=failure_mode),
        services=RuntimeServices(
            tool_provider=cast(Any, _StaticToolProvider((leaky_receiver_call,)))
        ),
    )


def assert_no_grant(text: str) -> None:
    """The failure still reaches its reader; only the identifiers are gone."""

    for value in (GRANT_PERSON, GRANT_RUN, GRANT_AGENT):
        assert value not in text, text
    assert "receiver.invalid/v1/documents" in text
    assert "403 Forbidden" in text


@pytest.mark.asyncio
async def test_a_tool_failure_reaches_the_model_without_naming_the_person() -> None:
    """A client error quotes the request URL, and under delegation that URL
    names the person, the run and the agent. The tool row goes into the
    transcript and back to the model."""

    events = await _run_leaky_tool_graph("swallow")

    rows = [
        event
        for event in events
        if isinstance(event, ToolResultRuntimeEvent) and event.is_error
    ]
    assert len(rows) == 1
    assert_no_grant(rows[0].content)


@pytest.mark.asyncio
async def test_a_crashed_run_reaches_the_person_without_naming_them() -> None:
    with delegated_logging_context():
        with capture_logs() as logs:
            events = await _run_leaky_tool_graph("crash")

    finals = [event for event in events if isinstance(event, FinalRuntimeEvent)]
    assert len(finals) == 1
    assert_no_grant(finals[0].content)
    for canary in (GRANT_PERSON, GRANT_RUN, GRANT_AGENT):
        assert canary not in logs.payload_text()


@pytest.mark.asyncio
async def test_a_recovered_node_error_does_not_name_the_person() -> None:
    """`on_error` routing puts the failure text on its own event and into graph
    state, which is the next prompt the model reads."""

    with capture_logs() as logs:
        events = await _run_leaky_tool_graph("recover")

    errors = [event for event in events if isinstance(event, NodeErrorRuntimeEvent)]
    assert len(errors) == 1
    assert_no_grant(errors[0].error_message)
    for canary in (GRANT_PERSON, GRANT_RUN, GRANT_AGENT):
        assert canary not in logs.payload_text()


ABANDONED_GRAPH: dict[str, bool] = {}


class _TwoStepGraphAgent(GraphAgentDefinition):
    """A first node that emits something for the consumer to see, and a second
    that keeps working after the consumer has gone."""

    agent_id: str = "test.graph.abandoned"
    role: str = "test"
    description: str = "test"

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="State",
            entry_node="announce",
            nodes=(
                GraphNodeDefinition(node_id="announce", title="Announce"),
                GraphNodeDefinition(node_id="keep_working", title="Keep working"),
            ),
            edges=(GraphEdgeDefinition(source="announce", target="keep_working"),),
        )

    def input_model(self) -> type[BaseModel]:
        return _GraphInput

    def state_model(self) -> type[BaseModel]:
        return _GraphState

    def output_model(self) -> type[BaseModel]:
        return _GraphInput

    def build_initial_state(
        self, input_model: BaseModel, binding: BoundRuntimeContext
    ) -> BaseModel:
        del binding
        return _GraphState(message=getattr(input_model, "message", ""))

    def node_handlers(self) -> Mapping[str, object]:
        async def _announce(state: BaseModel, ctx: Any) -> GraphNodeResult:
            del state
            ctx.emit_status("working", detail="step one")
            return GraphNodeResult()

        async def _keep_working(state: BaseModel, ctx: object) -> GraphNodeResult:
            del state, ctx
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                ABANDONED_GRAPH["cancelled"] = True
                raise
            ABANDONED_GRAPH["finished"] = True
            return GraphNodeResult()

        return {"announce": _announce, "keep_working": _keep_working}

    def build_output(self, state: BaseModel) -> BaseModel:
        return _GraphInput(message=getattr(state, "message", ""))


@pytest.mark.asyncio
async def test_an_abandoned_graph_stream_cancels_the_running_graph() -> None:
    """The graph runs in a task of its own, so a consumer that walks away —
    a closed SSE connection — would otherwise leave it running to the end."""

    ABANDONED_GRAPH.clear()
    definition = _TwoStepGraphAgent()
    runtime = GraphRuntime(definition=definition, services=RuntimeServices())
    executor = await runtime.build_executor(binding(definition.agent_id))

    stream = executor.stream(_GraphInput(message="hi"), ExecutionConfig(session_id="s"))
    async for _event in stream:
        break
    await abandon(stream)

    assert ABANDONED_GRAPH.get("cancelled") is True
    assert ABANDONED_GRAPH.get("finished") is not True


@pytest.mark.asyncio
async def test_external_graph_stream_cancellation_does_not_invent_a_terminal() -> None:
    ABANDONED_GRAPH.clear()
    definition = _TwoStepGraphAgent()
    runtime = GraphRuntime(definition=definition, services=RuntimeServices())
    executor = await runtime.build_executor(binding(definition.agent_id))
    events: list[RuntimeEvent] = []

    async def _consume() -> None:
        async for event in executor.stream(
            _GraphInput(message="hi"), ExecutionConfig(session_id="cancelled")
        ):
            events.append(event)

    consumer = asyncio.create_task(_consume())
    while not events:
        await asyncio.sleep(0)
    consumer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await consumer
    await asyncio.sleep(0)

    assert ABANDONED_GRAPH.get("cancelled") is True
    assert not any(isinstance(event, RuntimeErrorEvent) for event in events)


@pytest.mark.asyncio
async def test_a_graph_stream_is_a_child_of_the_run_already_open() -> None:
    """A graph agent invoked inside another run executes in a task of its own,
    joined to that run: ending the run ends the graph with it, without waiting
    for the consumer to walk away."""

    ABANDONED_GRAPH.clear()
    definition = _TwoStepGraphAgent()
    runtime = GraphRuntime(definition=definition, services=RuntimeServices())
    executor = await runtime.build_executor(binding(definition.agent_id))

    with RunScope.open(agent_id="parent") as parent:
        stream = executor.stream(
            _GraphInput(message="hi"), ExecutionConfig(session_id="s")
        )
        async for _event in stream:
            break
        parent.cancel_children()
        await asyncio.sleep(0.05)

        assert ABANDONED_GRAPH.get("cancelled") is True
        assert ABANDONED_GRAPH.get("finished") is not True
        await closable(stream).aclose()


CHILD_RUN: dict[str, bool] = {}


class _StoppedChildInvoker:
    """Models the in-process invoker: the child engine ends its own run on a
    terminal event and records the stop on the shared scope, so the child's
    call returns an ordinary result rather than raising."""

    def __init__(self) -> None:
        self.calls = 0

    async def invoke(self, request: Any) -> Any:
        from fred_sdk.contracts.context import AgentInvocationResult

        self.calls += 1
        scope = RunScope.current()
        assert scope is not None
        scope.record_stop(AuthorityLostError())
        return AgentInvocationResult(
            agent_id=request.agent_id, content="This run was stopped."
        )


class _DelegatingGraphAgent(GraphAgentDefinition):
    """A node that calls a child agent, followed by a node that must not run
    once the child's run has been stopped."""

    agent_id: str = "test.graph.delegating"
    role: str = "test"
    description: str = "test"

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="State",
            entry_node="call_child",
            nodes=(
                GraphNodeDefinition(node_id="call_child", title="Call child"),
                GraphNodeDefinition(node_id="after", title="After"),
            ),
            edges=(GraphEdgeDefinition(source="call_child", target="after"),),
        )

    def input_model(self) -> type[BaseModel]:
        return _GraphInput

    def state_model(self) -> type[BaseModel]:
        return _GraphState

    def output_model(self) -> type[BaseModel]:
        return _GraphInput

    def build_initial_state(
        self, input_model: BaseModel, binding: BoundRuntimeContext
    ) -> BaseModel:
        del binding
        return _GraphState(message=getattr(input_model, "message", ""))

    def node_handlers(self) -> Mapping[str, object]:
        async def _call_child(state: BaseModel, ctx: Any) -> GraphNodeResult:
            del state
            await ctx.invoke_agent("child", "do the thing")
            return GraphNodeResult()

        async def _after(state: BaseModel, ctx: object) -> GraphNodeResult:
            del state, ctx
            CHILD_RUN["after_ran"] = True
            return GraphNodeResult()

        return {"call_child": _call_child, "after": _after}

    def build_output(self, state: BaseModel) -> BaseModel:
        return _GraphInput(message=getattr(state, "message", ""))


@pytest.mark.asyncio
async def test_a_stopped_child_ends_the_parent_run() -> None:
    CHILD_RUN.clear()
    invoker = _StoppedChildInvoker()

    events = await _run_graph_stream(
        _DelegatingGraphAgent(),
        services=RuntimeServices(agent_invoker=cast(Any, invoker)),
    )

    terminal = terminal_event(events)
    assert terminal.reason is RuntimeStopReason.AUTHORITY_LOST
    assert invoker.calls == 1
    # The parent must not go on making calls for a run that is over.
    assert CHILD_RUN.get("after_ran") is not True
    assert not any(isinstance(event, FinalRuntimeEvent) for event in events)


@pytest.mark.asyncio
async def test_a_real_graph_child_stop_reaches_the_parent_terminal_event() -> None:
    """The in-process invoker must receive the child's terminal event before
    the shared run cancels the parent that is consuming it."""

    CHILD_RUN.clear()
    child = _StoppingGraphAgent(agent_id="child")
    invoker = LocalRegistryAgentInvoker(registry={"child": child}, access_token=None)
    set_runtime_context(
        FredRuntimeContext(RuntimeConfig(knowledge_flow_url="http://test.invalid"))
    )
    try:
        events = await _run_graph_stream(
            _DelegatingGraphAgent(),
            services=RuntimeServices(agent_invoker=cast(Any, invoker)),
        )
    finally:
        set_runtime_context(None)

    terminal = terminal_event(events)
    assert terminal.reason is RuntimeStopReason.AUTHORITY_LOST
    assert CHILD_RUN.get("after_ran") is not True
    assert not any(isinstance(event, FinalRuntimeEvent) for event in events)


@pytest.mark.asyncio
async def test_a_parallel_group_refuses_to_run_outside_the_runs_scope() -> None:
    """Members are the run's children. A scope conjured for the group would hand
    it a second full budget and would not be the one the run cancels, so the
    run's own scope is required rather than defaulted."""

    definition = _ParallelGraphAgent()
    runtime = GraphRuntime(definition=definition, services=RuntimeServices())
    executor = cast(Any, await runtime.build_executor(binding(definition.agent_id)))

    with pytest.raises(RuntimeError, match="run scope"):
        await executor._run_parallel_group(
            state=_GraphState(), members=("fan_out",), emit_event=None
        )


@pytest.mark.asyncio
async def test_graph_authority_loss_cancels_the_sibling_child() -> None:
    definition = _ParallelGraphAgent()
    PARALLEL_RUN.clear()
    saver = InMemorySaver()
    tracer = RecordingTracer()

    with capture_logs() as logs:
        events = await _run_graph_stream(
            definition,
            services=RuntimeServices(
                checkpointer=cast(Any, saver), tracer=cast(Any, tracer)
            ),
        )

    terminal = terminal_event(events)
    assert terminal.reason is RuntimeStopReason.AUTHORITY_LOST
    assert PARALLEL_RUN.get("busy_started") is True
    assert PARALLEL_RUN.get("busy_cancelled") is True, (
        "a sibling child left running keeps calling out under an authority the "
        "run has already lost"
    )
    assert PARALLEL_RUN.get("fan_in_ran") is not True

    # Canary, child run: the failure came from a child, and its body must not
    # reach any sink either.
    assert MARKER not in events_text(events)
    assert MARKER not in logs.payload_text()
    assert definition.agent_id not in logs.payload_text()
    assert MARKER not in tracer.text()
    assert MARKER not in checkpoint_text(saver)
    assert tracer.spans
    assert stored_checkpoints(saver) == 0

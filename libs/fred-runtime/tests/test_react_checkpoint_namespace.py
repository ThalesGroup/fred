"""
Where a ReAct V2 checkpoint actually lands, and which namespaces the resume
gate probes for it.

The namespace a root graph is configured with never reaches storage: LangGraph
resets `checkpoint_ns` to `""` for every non-nested run. Passing a per-agent
namespace into `compiled_agent.astream(...)` therefore isolates nothing, and a
reader that looks for it finds no checkpoint at all — which dead-ended every
ReAct V2 HITL resume in a 409 until the reader was aligned back on `""`.
"""

from typing import Any, TypedDict, cast

import pytest
from fred_runtime.app.agent_app import _resume_checkpoint_namespaces
from fred_runtime.react.react_message_codec import to_runnable_config
from fred_runtime.react.react_runtime import _TransportBackedReActExecutor
from fred_runtime.runtime_support.checkpoints import checkpoint_namespace
from fred_sdk.contracts.execution import RuntimeExecuteRequest
from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_sdk.contracts.runtime import ExecutionConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph


class _FakePortable:
    agent_id = "react.agent"
    session_id = "session-1"
    team_id = "personal"
    baggage: dict[str, object] = {}


class _FakeRuntimeContext:
    pass


class _FakeBinding:
    portable_context = _FakePortable()
    runtime_context = _FakeRuntimeContext()


class _FakeServices:
    tracer = None
    metrics = None


class _RecordingCompiledAgent:
    def __init__(self) -> None:
        self.config: object = None

    async def ainvoke(
        self, graph_input: object, *, config: object = None
    ) -> dict[str, object]:
        self.config = config
        return {
            "messages": [
                __import__("langchain_core.messages").messages.AIMessage(content="ok")
            ]
        }


class _CounterState(TypedDict):
    n: int


def test_langgraph_resets_root_checkpoint_namespace() -> None:
    """
    Pin the LangGraph behaviour every read path now depends on: a root graph
    stores its checkpoints under `""`, discarding whatever `checkpoint_ns` the
    caller configured (`pregel/_loop.py::PregelLoop.__init__`). A version bump
    that changed this must fail here rather than silently re-namespace live
    checkpoints out of reach of the resume gate.
    """

    def _step(state: _CounterState) -> _CounterState:
        return {"n": state["n"] + 1}

    graph = StateGraph(_CounterState)
    graph.add_node("step", _step)
    graph.add_edge(START, "step")
    graph.add_edge("step", END)
    saver = InMemorySaver()
    compiled = graph.compile(checkpointer=saver)

    compiled.invoke(
        {"n": 0},
        config={"configurable": {"thread_id": "t1", "checkpoint_ns": "instance-123"}},
    )

    stored = {
        cast(dict[str, Any], tuple_.config.get("configurable", {})).get("checkpoint_ns")
        for tuple_ in saver.list(None)
    }
    assert stored == {""}
    assert (
        saver.get_tuple(
            {"configurable": {"thread_id": "t1", "checkpoint_ns": "instance-123"}}
        )
        is None
    )


@pytest.mark.asyncio
async def test_react_executor_does_not_configure_a_checkpoint_namespace() -> None:
    """The executor stops asking for a namespace LangGraph would throw away."""

    compiled = _RecordingCompiledAgent()
    executor = _TransportBackedReActExecutor(
        compiled_agent=compiled,  # type: ignore[arg-type]
        binding=_FakeBinding(),  # type: ignore[arg-type]
        services=_FakeServices(),  # type: ignore[arg-type]
    )

    input_model = ReActInput(
        messages=(ReActMessage(role=ReActMessageRole.USER, content="hi"),)
    )

    await executor.invoke(input_model, ExecutionConfig(session_id="session-1"))

    assert compiled.config == {"configurable": {"thread_id": "session-1"}}


def test_to_runnable_config_carries_only_the_thread_id() -> None:
    runnable = to_runnable_config(ExecutionConfig(session_id="session-1"))

    assert runnable is not None
    configurable = runnable["configurable"]
    assert isinstance(configurable, dict)
    assert configurable == {"thread_id": "session-1"}


def test_react_resume_probes_the_unnamespaced_checkpoint_first() -> None:
    """
    A ReAct V2 resume (`interrupt_id`, never `checkpoint_id`) must look under
    `""` — where its checkpoint really is — before the per-agent namespace,
    even though the request carries a managed instance id.
    """

    request = RuntimeExecuteRequest(
        agent_instance_id="instance-123",
        session_id="session-1",
        interrupt_id="interrupt-a",
        resume_payload={"choice_id": "proceed"},
    )

    assert _resume_checkpoint_namespaces(request) == ("", "instance-123")


def test_graph_resume_probes_only_the_agent_namespace() -> None:
    """
    The hand-rolled Graph runtime writes through `aput` itself, so its
    per-agent namespace does reach storage — and its executor reads nowhere
    else. A `checkpoint_id`-carrying resume must not be waved past the gate on
    an unnamespaced checkpoint it would then fail to load mid-stream.
    """

    request = RuntimeExecuteRequest(
        agent_instance_id="instance-123",
        session_id="session-1",
        checkpoint_id="stored-checkpoint-id",
        resume_payload={"choice_id": "proceed"},
    )

    assert _resume_checkpoint_namespaces(request) == ("instance-123",)


def test_resume_namespaces_fall_back_to_the_template_agent_id() -> None:
    """An unmanaged (template) agent has no instance id to namespace on."""

    request = RuntimeExecuteRequest(
        agent_id="react.agent",
        session_id="session-1",
        interrupt_id="interrupt-a",
        resume_payload={"choice_id": "proceed"},
    )

    assert _resume_checkpoint_namespaces(request) == ("", "react.agent")


def test_react_checkpoint_namespace_uses_managed_instance_when_available() -> None:
    assert (
        checkpoint_namespace(
            agent_instance_id="managed-456",
            agent_id="react.agent",
        )
        == "managed-456"
    )

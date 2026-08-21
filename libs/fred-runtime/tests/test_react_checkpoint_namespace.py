import pytest

from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_runtime.react.react_runtime import _TransportBackedReActExecutor
from fred_sdk.contracts.runtime import ExecutionConfig
from fred_runtime.react.react_message_codec import to_runnable_config
from fred_runtime.runtime_support.checkpoints import checkpoint_namespace

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

    async def ainvoke(self, graph_input: object, *, config: object = None) -> dict[str, object]:
        self.config = config
        return {
            "messages": [
                __import__("langchain_core.messages").messages.AIMessage(content="ok")
            ]
        }


@pytest.mark.asyncio
async def test_react_executor_passes_checkpoint_namespace_to_langgraph() -> None:
    compiled = _RecordingCompiledAgent()
    executor = _TransportBackedReActExecutor(
        compiled_agent=compiled,  # type: ignore[arg-type]
        binding=_FakeBinding(),  # type: ignore[arg-type]
        services=_FakeServices(),  # type: ignore[arg-type]
        checkpoint_ns="instance-123",
    )

    input_model = ReActInput(
        messages=(ReActMessage(role=ReActMessageRole.USER, content="hi"),)
    )

    await executor.invoke(
        input_model,
        ExecutionConfig(session_id="session-1"),
    )

    assert compiled.config == {
        "configurable": {
            "thread_id": "session-1",
            "checkpoint_ns": "instance-123",
        }
    }

def test_react_checkpoint_namespace_uses_managed_instance_when_available() -> None:
    assert (
        checkpoint_namespace(
            agent_instance_id="managed-456",
            agent_id="react.agent",
        )
        == "managed-456"
    )

def test_to_runnable_config_adds_agent_checkpoint_namespace() -> None:
    config = ExecutionConfig(session_id="session-1")

    runnable = to_runnable_config(
        config,
        checkpoint_ns="instance-123",
    )

    assert runnable is not None
    assert runnable["configurable"]["thread_id"] == "session-1"
    assert runnable["configurable"]["checkpoint_ns"] == "instance-123"

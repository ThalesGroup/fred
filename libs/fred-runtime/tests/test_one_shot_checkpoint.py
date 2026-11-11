"""A turn without a conversation keeps its checkpoints out of the conversation store."""

from dataclasses import dataclass
from typing import Any

import pytest
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.runtime_context import RuntimeConfig, set_runtime_context
from fred_runtime.runtime_context import RuntimeContext as FredRuntimeContext
from fred_sdk.contracts.models import GraphAgentDefinition
from langgraph.checkpoint.memory import InMemorySaver
from weaver_fixtures import INSTANCE_ID, SPACE_ID, active_turn


class _UnusedGraph(GraphAgentDefinition):
    agent_id: str = "test.graph"
    role: str = "test"
    description: str = "test"

    def build_graph(self):
        raise NotImplementedError

    def input_model(self):
        raise NotImplementedError

    def state_model(self):
        raise NotImplementedError

    def output_model(self):
        raise NotImplementedError

    def build_initial_state(self, input_model, binding):
        raise NotImplementedError

    def build_output(self, state):
        raise NotImplementedError

    def node_handlers(self):
        raise NotImplementedError


@dataclass(frozen=True)
class _Services:
    checkpointer: Any


class _ServicesCaptured(Exception):
    pass


@pytest.mark.asyncio
@pytest.mark.parametrize("session_id", [None, "s"])
async def test_only_a_conversation_turn_uses_the_stored_checkpointer(
    monkeypatch, session_id
):
    stored = object()
    captured: dict[str, Any] = {}

    def capture_services(*_args, services, **_kwargs):
        captured["checkpointer"] = services.checkpointer
        raise _ServicesCaptured

    monkeypatch.setattr(
        agent_app_module,
        "_build_runtime_services",
        lambda *_args, **_kwargs: _Services(checkpointer=stored),
    )
    monkeypatch.setattr(agent_app_module, "_build_capability_block", capture_services)
    set_runtime_context(
        FredRuntimeContext(RuntimeConfig(knowledge_flow_url="http://kf.invalid"))
    )
    context = {"user_id": "alice", "space_id": SPACE_ID}
    if session_id is not None:
        context["session_id"] = session_id
    request = agent_app_module._AgentExecuteRequest.model_construct(
        agent_id="test.graph",
        agent_instance_id=INSTANCE_ID,
        message="hello",
        context=context,
    )
    try:
        with active_turn("test.graph", session=session_id):
            # The turn reports the stop as its error event; only the capture matters.
            await anext(
                agent_app_module._iterate_runtime_event_payloads_inner(
                    _UnusedGraph(), request
                )
            )
    finally:
        set_runtime_context(None)

    if session_id is None:
        assert isinstance(captured["checkpointer"], InMemorySaver)
    else:
        assert captured["checkpointer"] is stored

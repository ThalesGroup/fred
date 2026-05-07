"""
Offline unit tests for the multi-agent conversational memory primitives.

Coverage:
- A.1  ConversationTurn / ConversationalState construction, serialisation, immutability
- A.2  GraphAgentDefinition.build_turn_state carry-forward contract
- A.3  GraphAgentDefinition.build_completed_state identity default
- A.4  AgentInvocationRequest.prior_turns / ExecutionConfig.invocation_turns
- B.1  TeamState inherits ConversationalState
- B.2  TeamAgent auto-generates build_completed_state
- B.3  _format_conversation_history helper
- B.4  _make_agent_invoke_step passes prior_turns

All tests are offline — no external services required.

Ref: docs/backlog/MULTI-AGENT-MEMORY-BACKLOG.md M1 phases A+B — SDK primitives
     (ConversationTurn, ConversationalState, TeamAgent state, build_turn_state).
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic import BaseModel

from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    BoundRuntimeContext,
    ConversationalState,
    ConversationTurn,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import (
    GraphAgentDefinition,
    GraphDefinition,
    GraphNodeDefinition,
)
from fred_sdk.contracts.runtime import ExecutionConfig
from fred_sdk.graph.authoring.team_api import (
    AgentSpec,
    TeamAgent,
    TeamMemberResult,
    TeamState,
    _format_conversation_history,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(),
        portable_context=PortableContext(
            request_id="req-1",
            correlation_id="corr-1",
            actor="alice",
            tenant="test",
            environment=PortableEnvironment.DEV,
        ),
    )


def _turn(user: str, response: str, name: str | None = None) -> ConversationTurn:
    return ConversationTurn(user_message=user, agent_response=response, agent_name=name)


# ---------------------------------------------------------------------------
# Minimal test graph agent with ConversationalState
# ---------------------------------------------------------------------------


class _ConvState(ConversationalState, BaseModel):
    message: str = ""


class _MinInput(BaseModel):
    message: str = ""


class _ConvAgent(GraphAgentDefinition):
    agent_id: str = "test.conv"
    role: str = "test"
    description: str = "test"

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="ConvState",
            entry_node="n",
            nodes=(GraphNodeDefinition(node_id="n", title="N"),),
        )

    def input_model(self) -> type[BaseModel]:
        return _MinInput

    def state_model(self) -> type[BaseModel]:
        return _ConvState

    def output_model(self) -> type[BaseModel]:
        return _MinInput

    def build_initial_state(
        self, input_model: BaseModel, binding: BoundRuntimeContext
    ) -> BaseModel:
        return _ConvState(message=getattr(input_model, "message", ""))

    def node_handlers(self) -> Mapping[str, object]:
        return {}

    def build_output(self, state: BaseModel) -> BaseModel:
        return _MinInput(message=getattr(state, "message", ""))


# Minimal test graph agent WITHOUT ConversationalState


class _PlainState(BaseModel):
    message: str = ""


class _PlainAgent(GraphAgentDefinition):
    agent_id: str = "test.plain"
    role: str = "test"
    description: str = "test"

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="PlainState",
            entry_node="n",
            nodes=(GraphNodeDefinition(node_id="n", title="N"),),
        )

    def input_model(self) -> type[BaseModel]:
        return _MinInput

    def state_model(self) -> type[BaseModel]:
        return _PlainState

    def output_model(self) -> type[BaseModel]:
        return _MinInput

    def build_initial_state(
        self, input_model: BaseModel, binding: BoundRuntimeContext
    ) -> BaseModel:
        return _PlainState(message=getattr(input_model, "message", ""))

    def node_handlers(self) -> Mapping[str, object]:
        return {}

    def build_output(self, state: BaseModel) -> BaseModel:
        return _MinInput(message=getattr(state, "message", ""))


_CONV_AGENT = _ConvAgent()
_PLAIN_AGENT = _PlainAgent()

# ---------------------------------------------------------------------------
# A.1 ConversationTurn
# ---------------------------------------------------------------------------


def test_conversation_turn_construction() -> None:
    turn = _turn("hello", "world")
    assert turn.user_message == "hello"
    assert turn.agent_response == "world"
    assert turn.agent_name is None


def test_conversation_turn_with_agent_name() -> None:
    turn = _turn("hello", "world", name="Analyst")
    assert turn.agent_name == "Analyst"


def test_conversation_turn_is_frozen() -> None:
    turn = _turn("u", "a")
    with pytest.raises(Exception):
        turn.user_message = "changed"  # type: ignore[misc]


def test_conversation_turn_serialisation_roundtrip() -> None:
    turn = _turn("q", "r", name="Bot")
    data = turn.model_dump(mode="json")
    restored = ConversationTurn.model_validate(data)
    assert restored == turn


# ---------------------------------------------------------------------------
# A.1 ConversationalState
# ---------------------------------------------------------------------------


def test_conversational_state_default_empty() -> None:
    state = _ConvState()
    assert state.conversation_history == ()


def test_conversational_state_with_history() -> None:
    t = _turn("q", "a")
    state = _ConvState(conversation_history=(t,))
    assert len(state.conversation_history) == 1
    assert state.conversation_history[0].user_message == "q"


# ---------------------------------------------------------------------------
# A.2 GraphAgentDefinition.build_turn_state
# ---------------------------------------------------------------------------


def test_build_turn_state_no_previous_no_turns_returns_initial() -> None:
    inp = _MinInput(message="hello")
    state = _CONV_AGENT.build_turn_state(inp, _binding())
    assert isinstance(state, _ConvState)
    assert state.conversation_history == ()


def test_build_turn_state_carries_history_from_previous_state() -> None:
    inp = _MinInput(message="turn2")
    t1 = _turn("turn1 q", "turn1 a", name="Bot")
    prev = _ConvState(message="turn1", conversation_history=(t1,))
    state = _CONV_AGENT.build_turn_state(inp, _binding(), previous_state=prev)
    assert isinstance(state, _ConvState)
    assert len(state.conversation_history) == 1
    assert state.conversation_history[0].user_message == "turn1 q"


def test_build_turn_state_plain_agent_unaffected_by_previous() -> None:
    inp = _MinInput(message="hello")
    prev = _PlainState(message="old")
    state = _PLAIN_AGENT.build_turn_state(inp, _binding(), previous_state=prev)
    assert isinstance(state, _PlainState)
    assert state.message == "hello"


def test_build_turn_state_plain_agent_unaffected_by_invocation_turns() -> None:
    inp = _MinInput(message="hello")
    turns = (_turn("q", "a"),)
    state = _PLAIN_AGENT.build_turn_state(inp, _binding(), invocation_turns=turns)
    assert isinstance(state, _PlainState)
    assert not hasattr(state, "conversation_history")


def test_build_turn_state_seeds_from_invocation_turns_when_no_previous() -> None:
    inp = _MinInput(message="follow-up")
    t = _turn("prior q", "prior a")
    state = _CONV_AGENT.build_turn_state(inp, _binding(), invocation_turns=(t,))
    assert isinstance(state, _ConvState)
    assert len(state.conversation_history) == 1
    assert state.conversation_history[0].user_message == "prior q"


def test_build_turn_state_depth_limit_truncates_oldest_first() -> None:
    _CONV_AGENT.__class__.conversation_history_max_turns = 3
    turns = tuple(_turn(f"q{i}", f"a{i}") for i in range(5))
    prev = _ConvState(message="x", conversation_history=turns)
    inp = _MinInput(message="next")
    state = _CONV_AGENT.build_turn_state(inp, _binding(), previous_state=prev)
    assert isinstance(state, _ConvState)
    assert len(state.conversation_history) == 3
    assert state.conversation_history[0].user_message == "q2"
    _CONV_AGENT.__class__.conversation_history_max_turns = 20


# ---------------------------------------------------------------------------
# A.3 GraphAgentDefinition.build_completed_state default is identity
# ---------------------------------------------------------------------------


def test_build_completed_state_identity_default() -> None:
    state = _ConvState(message="done", conversation_history=(_turn("q", "a"),))
    result = _CONV_AGENT.build_completed_state(state)
    assert result is state


# ---------------------------------------------------------------------------
# A.4 AgentInvocationRequest.prior_turns
# ---------------------------------------------------------------------------


def test_agent_invocation_request_prior_turns_defaults_empty() -> None:
    ctx = PortableContext(
        request_id="r",
        correlation_id="c",
        actor="alice",
        tenant="t",
        environment=PortableEnvironment.DEV,
    )
    req = AgentInvocationRequest(agent_id="ag", message="hi", context=ctx)
    assert req.prior_turns == ()


def test_agent_invocation_request_with_prior_turns() -> None:
    ctx = PortableContext(
        request_id="r",
        correlation_id="c",
        actor="alice",
        tenant="t",
        environment=PortableEnvironment.DEV,
    )
    t = _turn("q", "a", name="Bot")
    req = AgentInvocationRequest(
        agent_id="ag", message="hi", context=ctx, prior_turns=(t,)
    )
    assert len(req.prior_turns) == 1
    assert req.prior_turns[0].user_message == "q"


def test_agent_invocation_request_serialises_prior_turns() -> None:
    ctx = PortableContext(
        request_id="r",
        correlation_id="c",
        actor="alice",
        tenant="t",
        environment=PortableEnvironment.DEV,
    )
    t = _turn("q", "a")
    req = AgentInvocationRequest(
        agent_id="ag", message="hi", context=ctx, prior_turns=(t,)
    )
    data = req.model_dump(mode="json")
    assert len(data["prior_turns"]) == 1
    assert data["prior_turns"][0]["user_message"] == "q"


# ---------------------------------------------------------------------------
# A.4 ExecutionConfig.invocation_turns
# ---------------------------------------------------------------------------


def test_execution_config_invocation_turns_defaults_empty() -> None:
    cfg = ExecutionConfig(session_id="s-1")
    assert cfg.invocation_turns == ()


def test_execution_config_with_invocation_turns() -> None:
    t = _turn("q", "a")
    cfg = ExecutionConfig(session_id="s-1", invocation_turns=(t,))
    assert len(cfg.invocation_turns) == 1
    assert cfg.invocation_turns[0].user_message == "q"


def test_execution_config_serialises_invocation_turns() -> None:
    t = _turn("q", "a", name="Bot")
    cfg = ExecutionConfig(session_id="s-1", invocation_turns=(t,))
    data = cfg.model_dump(mode="json")
    assert len(data["invocation_turns"]) == 1
    assert data["invocation_turns"][0]["agent_name"] == "Bot"


# ---------------------------------------------------------------------------
# B.1 TeamState inherits ConversationalState
# ---------------------------------------------------------------------------


def test_team_state_has_conversation_history_field() -> None:
    state = TeamState(user_message="hi")
    assert state.conversation_history == ()


def test_team_state_accepts_conversation_history() -> None:
    t = _turn("q", "a", name="Specialist")
    state = TeamState(user_message="hi", conversation_history=(t,))
    assert len(state.conversation_history) == 1


# ---------------------------------------------------------------------------
# B.2 TeamAgent auto-generated build_completed_state
# ---------------------------------------------------------------------------


class _RouteTeam(TeamAgent):
    agent_id: str = "test.route_team"
    role: str = "test router"
    description: str = "test"
    mode = "route"
    coordinator_instructions = "pick one"
    members = (
        AgentSpec(name="Alpha", role="does alpha", agent_ref="v2.alpha"),
        AgentSpec(name="Beta", role="does beta", agent_ref="v2.beta"),
    )


_ROUTE_TEAM = _RouteTeam()


def test_team_agent_build_completed_state_appends_turn() -> None:
    state = TeamState(
        user_message="what is 4+4?",
        results=[TeamMemberResult(agent_name="Alpha", output="8")],
        final_text="8",
    )
    updated = _ROUTE_TEAM.build_completed_state(state)
    assert isinstance(updated, TeamState)
    assert len(updated.conversation_history) == 1
    turn = updated.conversation_history[0]
    assert turn.user_message == "what is 4+4?"
    assert turn.agent_response == "8"
    assert turn.agent_name == "Alpha"


def test_team_agent_build_completed_state_with_prior_history() -> None:
    t0 = _turn("turn0 q", "turn0 a", name="Beta")
    state = TeamState(
        user_message="turn1 q",
        results=[TeamMemberResult(agent_name="Beta", output="turn1 a")],
        final_text="turn1 a",
        conversation_history=(t0,),
    )
    updated = _ROUTE_TEAM.build_completed_state(state)
    assert isinstance(updated, TeamState)
    assert len(updated.conversation_history) == 2
    assert updated.conversation_history[0].user_message == "turn0 q"
    assert updated.conversation_history[1].user_message == "turn1 q"


def test_team_agent_build_completed_state_no_results_agent_name_is_none() -> None:
    state = TeamState(user_message="q", final_text="no one answered")
    updated = _ROUTE_TEAM.build_completed_state(state)
    assert isinstance(updated, TeamState)
    assert updated.conversation_history[-1].agent_name is None


# ---------------------------------------------------------------------------
# B.3 _format_conversation_history helper
# ---------------------------------------------------------------------------


def test_format_conversation_history_empty_returns_empty_string() -> None:
    assert _format_conversation_history(()) == ""


def test_format_conversation_history_single_turn_no_agent_name() -> None:
    t = _turn("hello", "world")
    result = _format_conversation_history((t,))
    assert "User: hello" in result
    assert "Assistant: world" in result
    assert "(" not in result


def test_format_conversation_history_single_turn_with_agent_name() -> None:
    t = _turn("hello", "world", name="Bot")
    result = _format_conversation_history((t,))
    assert "Assistant (Bot): world" in result


def test_format_conversation_history_multiple_turns_ordered() -> None:
    turns = (
        _turn("q1", "a1"),
        _turn("q2", "a2"),
    )
    result = _format_conversation_history(turns)
    q1_pos = result.index("q1")
    q2_pos = result.index("q2")
    assert q1_pos < q2_pos

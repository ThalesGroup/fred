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
Offline unit tests for the runtime execution contract models (RUNTIME-07 rev. 2).

Tests cover:
- ActorContext, TeamContext, ExecutionTarget, TraceContext
- RuntimeExecuteRequest: target validation, compatibility helpers
- TurnPersistedEvent inclusion in RuntimeEvent union

There is NO ExecutionGrant: the control-plane issues no signed capability;
identity is the Keycloak JWT and authorization is a pod-side OpenFGA check.
All tests run without any external services.
"""

from __future__ import annotations

import pytest

from fred_sdk.contracts.context import RuntimeContext
from fred_sdk.contracts.execution import (
    ActorContext,
    ExecutionTarget,
    RuntimeExecuteRequest,
    TeamContext,
    TeamType,
    TraceContext,
)
from fred_sdk.contracts.runtime import RuntimeEventKind, TurnPersistedEvent

# ---------------------------------------------------------------------------
# ActorContext
# ---------------------------------------------------------------------------


def test_actor_context_requires_user_id() -> None:
    with pytest.raises(Exception):
        ActorContext(user_id="")  # type: ignore[call-arg]


def test_actor_context_minimal() -> None:
    actor = ActorContext(user_id="u-1")
    assert actor.user_id == "u-1"
    assert actor.principal is None


def test_actor_context_with_principal() -> None:
    actor = ActorContext(user_id="u-1", principal="alice@example.com")
    assert actor.principal == "alice@example.com"


def test_actor_context_is_frozen() -> None:
    actor = ActorContext(user_id="u-1")
    with pytest.raises(Exception):
        actor.user_id = "u-2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TeamContext
# ---------------------------------------------------------------------------


def test_team_context_requires_team_id() -> None:
    with pytest.raises(Exception):
        TeamContext(team_id="")  # type: ignore[call-arg]


def test_team_context_minimal() -> None:
    team = TeamContext(team_id="t-1")
    assert team.team_id == "t-1"
    assert team.team_type is None


def test_team_context_with_type_personal() -> None:
    team = TeamContext(team_id="t-1", team_type=TeamType.PERSONAL)
    assert team.team_type == TeamType.PERSONAL


def test_team_context_with_type_collaborative() -> None:
    team = TeamContext(team_id="t-2", team_type=TeamType.COLLABORATIVE)
    assert team.team_type == TeamType.COLLABORATIVE


# ---------------------------------------------------------------------------
# ExecutionTarget
# ---------------------------------------------------------------------------


def test_execution_target_requires_agent_instance_id() -> None:
    with pytest.raises(Exception):
        ExecutionTarget(agent_instance_id="")  # type: ignore[call-arg]


def test_execution_target_minimal() -> None:
    target = ExecutionTarget(agent_instance_id="inst-42")
    assert target.agent_instance_id == "inst-42"
    assert target.underlying_agent_ref is None


def test_execution_target_with_agent_ref() -> None:
    target = ExecutionTarget(
        agent_instance_id="inst-42",
        underlying_agent_ref="v2.sample.react",
    )
    assert target.underlying_agent_ref == "v2.sample.react"


# ---------------------------------------------------------------------------
# TraceContext
# ---------------------------------------------------------------------------


def test_trace_context_requires_request_id_and_correlation_id() -> None:
    with pytest.raises(Exception):
        TraceContext(request_id="", correlation_id="c-1")  # type: ignore[call-arg]
    with pytest.raises(Exception):
        TraceContext(request_id="r-1", correlation_id="")  # type: ignore[call-arg]


def test_trace_context_minimal() -> None:
    trace = TraceContext(request_id="r-1", correlation_id="c-1")
    assert trace.request_id == "r-1"
    assert trace.correlation_id == "c-1"
    assert trace.trace_id is None
    assert trace.session_id is None
    assert trace.checkpoint_id is None


def test_trace_context_full() -> None:
    trace = TraceContext(
        request_id="r-1",
        correlation_id="c-1",
        trace_id="t-1",
        session_id="sess-abc",
        checkpoint_id="cp-xyz",
    )
    assert trace.trace_id == "t-1"
    assert trace.session_id == "sess-abc"
    assert trace.checkpoint_id == "cp-xyz"


# ---------------------------------------------------------------------------
# RuntimeExecuteRequest — construction and validation
# ---------------------------------------------------------------------------


def test_request_requires_exactly_one_target() -> None:
    # Both set → error
    with pytest.raises(ValueError, match="exactly one"):
        RuntimeExecuteRequest(
            agent_id="my-agent",
            agent_instance_id="inst-42",
            input="hello",
        )


def test_request_requires_at_least_one_target() -> None:
    # Neither set → error
    with pytest.raises(ValueError, match="exactly one"):
        RuntimeExecuteRequest(input="hello")


def test_request_requires_input_when_no_resume_payload() -> None:
    with pytest.raises(ValueError, match="input is required"):
        RuntimeExecuteRequest(agent_id="my-agent", input="")


def test_request_direct_template_minimal() -> None:
    req = RuntimeExecuteRequest(agent_id="my-agent", input="hello")
    assert req.agent_id == "my-agent"
    assert req.input == "hello"
    assert req.agent_instance_id is None
    assert req.session_id is None


def test_request_managed_execution_carries_team_in_runtime_context() -> None:
    # Managed execution: no signed grant. Identity/team travel in runtime_context;
    # the pod authorizes via OpenFGA on that team (RUNTIME-07 rev. 2).
    req = RuntimeExecuteRequest(
        agent_instance_id="inst-42",
        input="hello",
        session_id="sess-abc",
        runtime_context=RuntimeContext(user_id="u-1", team_id="t-1"),
    )
    assert req.agent_instance_id == "inst-42"
    assert req.session_id == "sess-abc"
    assert req.effective_team_id() == "t-1"


def test_request_resume_payload_allows_empty_input() -> None:
    req = RuntimeExecuteRequest(
        agent_id="my-agent",
        input="",
        resume_payload={"approved": True},
    )
    assert req.resume_payload == {"approved": True}


# ---------------------------------------------------------------------------
# RuntimeExecuteRequest — compatibility helpers
# ---------------------------------------------------------------------------


def test_effective_user_id_from_runtime_context() -> None:
    req = RuntimeExecuteRequest(
        agent_id="my-agent",
        input="hello",
        runtime_context=RuntimeContext(user_id="ctx-user"),
    )
    assert req.effective_user_id() == "ctx-user"


def test_effective_user_id_none_without_context() -> None:
    req = RuntimeExecuteRequest(agent_id="my-agent", input="hello")
    assert req.effective_user_id() is None


def test_effective_team_id_from_runtime_context() -> None:
    req = RuntimeExecuteRequest(
        agent_instance_id="inst-42",
        input="hello",
        runtime_context=RuntimeContext(user_id="u-1", team_id="t-ctx"),
    )
    assert req.effective_team_id() == "t-ctx"


def test_effective_session_id_prefers_top_level() -> None:
    req = RuntimeExecuteRequest(
        agent_id="my-agent",
        input="hello",
        session_id="top-level-session",
        runtime_context=RuntimeContext(session_id="ctx-session"),
    )
    assert req.effective_session_id() == "top-level-session"


def test_effective_session_id_falls_back_to_context() -> None:
    req = RuntimeExecuteRequest(
        agent_id="my-agent",
        input="hello",
        runtime_context=RuntimeContext(session_id="ctx-session"),
    )
    assert req.effective_session_id() == "ctx-session"


def test_message_property_alias() -> None:
    req = RuntimeExecuteRequest(agent_id="my-agent", input="the input text")
    assert req.message == "the input text"


def test_to_legacy_context_merges_runtime_context_fields() -> None:
    req = RuntimeExecuteRequest(
        agent_instance_id="inst-42",
        input="hello",
        session_id="sess-abc",
        checkpoint_id="cp-1",
        runtime_context=RuntimeContext(
            user_id="u-ctx",
            team_id="t-ctx",
            trace_id="trace-1",
            correlation_id="corr-1",
            language="fr",
        ),
    )
    ctx = req.to_legacy_context()
    assert ctx["session_id"] == "sess-abc"
    assert ctx["checkpoint_id"] == "cp-1"
    assert ctx["user_id"] == "u-ctx"
    assert ctx["team_id"] == "t-ctx"
    assert ctx["agent_instance_id"] == "inst-42"
    assert ctx["trace_id"] == "trace-1"
    assert ctx["correlation_id"] == "corr-1"
    assert ctx["execution_action"] == "execute"
    assert ctx["language"] == "fr"


def test_to_legacy_context_resume_action() -> None:
    req = RuntimeExecuteRequest(
        agent_id="my-agent",
        input="hello",
        session_id="sess-xyz",
        checkpoint_id="cp-ctx",
        resume_payload={"choice_id": "ok"},
        runtime_context=RuntimeContext(user_id="ctx-user"),
    )
    ctx = req.to_legacy_context()
    assert ctx["session_id"] == "sess-xyz"
    assert ctx["checkpoint_id"] == "cp-ctx"
    assert ctx["user_id"] == "ctx-user"
    assert ctx["execution_action"] == "resume"


# ---------------------------------------------------------------------------
# TurnPersistedEvent — included in RuntimeEvent union
# ---------------------------------------------------------------------------


def test_turn_persisted_event_construction() -> None:
    event = TurnPersistedEvent(session_id="sess-abc", sequence=99)
    assert event.session_id == "sess-abc"
    assert event.kind == RuntimeEventKind.TURN_PERSISTED
    assert event.exchange_id is None


def test_turn_persisted_event_with_exchange_id() -> None:
    event = TurnPersistedEvent(session_id="sess-abc", exchange_id="xchg-1", sequence=5)
    assert event.exchange_id == "xchg-1"


def test_turn_persisted_event_serialises_as_dict() -> None:
    event = TurnPersistedEvent(session_id="sess-abc", sequence=1)
    data = event.model_dump(mode="json")
    assert data["kind"] == "turn_persisted"
    assert data["session_id"] == "sess-abc"


def test_turn_persisted_event_discriminator_roundtrip() -> None:
    from pydantic import TypeAdapter

    from fred_sdk.contracts.runtime import RuntimeEvent

    raw = {"kind": "turn_persisted", "session_id": "sess-abc", "sequence": 0}
    ta = TypeAdapter(RuntimeEvent)
    event = ta.validate_python(raw)
    assert isinstance(event, TurnPersistedEvent)
    assert event.session_id == "sess-abc"

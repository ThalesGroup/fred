"""
Offline unit tests for the Phase 1 runtime execution contract models.

Tests cover:
- ActorContext, TeamContext, ExecutionTarget, TraceContext
- ExecutionGrant: construction, expiry checks, structural validation
- RuntimeExecuteRequest: validation, compatibility helpers
- validate_execution_grant helper
- TurnPersistedEvent inclusion in RuntimeEvent union

All tests run without any external services.
"""

from __future__ import annotations

import time
from typing import Any
from fred_sdk.contracts.eval import EvalStep, EvalTrace

import pytest

from fred_sdk.contracts.execution import (
    ActorContext,
    ExecutionGrant,
    ExecutionGrantAction,
    ExecutionGrantViolation,
    ExecutionTarget,
    RuntimeExecuteRequest,
    TeamContext,
    TeamType,
    TraceContext,
    validate_execution_grant,
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


def test_eval_step_minimal() -> None:
    step = EvalStep(kind="final")
    assert step.kind == "final"


def test_eval_trace_minimal() -> None:
    trace = EvalTrace(
        session_id="s-1",
        agent_id="agent-1",
        input="hello",
        latency_ms=42,
        steps=(EvalStep(kind="final", content="ok"),),
    )
    assert trace.session_id == "s-1"
    assert trace.steps[0].kind == "final"


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
# ExecutionGrant — construction
# ---------------------------------------------------------------------------

_FUTURE = int(time.time()) + 3600
_PAST = int(time.time()) - 3600
_NOW = int(time.time())


def _valid_grant(**overrides: Any) -> ExecutionGrant:
    return ExecutionGrant(
        user_id=overrides.get("user_id", "u-1"),
        team_id=overrides.get("team_id", "t-1"),
        agent_instance_id=overrides.get("agent_instance_id", "inst-42"),
        action=overrides.get("action", ExecutionGrantAction.EXECUTE),
        audience=overrides.get("audience", "https://runtime.example.com"),
        issued_at=overrides.get("issued_at", _NOW - 10),
        expires_at=overrides.get("expires_at", _FUTURE),
        scopes=overrides.get("scopes", ()),
        trace_id=overrides.get("trace_id"),
        correlation_id=overrides.get("correlation_id"),
        storage_scope=overrides.get("storage_scope"),
    )


def test_grant_minimal_construction() -> None:
    grant = _valid_grant()
    assert grant.user_id == "u-1"
    assert grant.team_id == "t-1"
    assert grant.agent_instance_id == "inst-42"
    assert grant.action == ExecutionGrantAction.EXECUTE
    assert grant.scopes == ()
    assert grant.storage_scope is None


def test_grant_with_scopes() -> None:
    grant = _valid_grant(scopes=("read", "execute"))
    assert "read" in grant.scopes
    assert "execute" in grant.scopes


def test_grant_resume_action() -> None:
    grant = _valid_grant(action=ExecutionGrantAction.RESUME)
    assert grant.action == ExecutionGrantAction.RESUME


# ---------------------------------------------------------------------------
# ExecutionGrant — expiry checks
# ---------------------------------------------------------------------------


def test_grant_is_not_expired_when_in_future() -> None:
    grant = _valid_grant(expires_at=_FUTURE)
    assert not grant.is_expired()


def test_grant_is_expired_when_in_past() -> None:
    grant = _valid_grant(expires_at=_PAST)
    assert grant.is_expired()


def test_grant_is_expired_at_boundary() -> None:
    # expires_at == now → expired (>= comparison)
    grant = _valid_grant(expires_at=_NOW)
    assert grant.is_expired(now=_NOW)


def test_grant_not_yet_valid_when_issued_in_future() -> None:
    grant = _valid_grant(issued_at=_FUTURE, expires_at=_FUTURE + 3600)
    assert grant.is_not_yet_valid()


def test_grant_is_valid_when_issued_in_past() -> None:
    grant = _valid_grant(issued_at=_NOW - 10, expires_at=_FUTURE)
    assert not grant.is_not_yet_valid()


# ---------------------------------------------------------------------------
# ExecutionGrant — structural validation
# ---------------------------------------------------------------------------


def test_grant_validate_no_violations_for_valid_grant() -> None:
    grant = _valid_grant()
    violations = grant.validate_for_execution(
        expected_action=ExecutionGrantAction.EXECUTE,
        expected_team_id="t-1",
        expected_agent_instance_id="inst-42",
    )
    assert violations == []


def test_grant_validate_detects_expired() -> None:
    grant = _valid_grant(expires_at=_PAST)
    violations = grant.validate_for_execution()
    assert any("expired" in v for v in violations)


def test_grant_validate_detects_action_mismatch() -> None:
    grant = _valid_grant(action=ExecutionGrantAction.RESUME)
    violations = grant.validate_for_execution(
        expected_action=ExecutionGrantAction.EXECUTE
    )
    assert any("action mismatch" in v for v in violations)


def test_grant_validate_detects_team_mismatch() -> None:
    grant = _valid_grant(team_id="t-wrong")
    violations = grant.validate_for_execution(expected_team_id="t-1")
    assert any("team_id mismatch" in v for v in violations)


def test_grant_validate_detects_agent_instance_mismatch() -> None:
    grant = _valid_grant(agent_instance_id="inst-other")
    violations = grant.validate_for_execution(expected_agent_instance_id="inst-42")
    assert any("agent_instance_id mismatch" in v for v in violations)


def test_grant_validate_multiple_violations_are_all_reported() -> None:
    grant = _valid_grant(
        expires_at=_PAST, team_id="t-wrong", agent_instance_id="inst-other"
    )
    violations = grant.validate_for_execution(
        expected_team_id="t-1",
        expected_agent_instance_id="inst-42",
    )
    assert len(violations) >= 2


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
    assert req.execution_grant is None


def test_request_managed_execution_with_grant() -> None:
    grant = _valid_grant()
    req = RuntimeExecuteRequest(
        agent_instance_id="inst-42",
        input="hello",
        session_id="sess-abc",
        execution_grant=grant,
    )
    assert req.agent_instance_id == "inst-42"
    assert req.session_id == "sess-abc"
    assert req.execution_grant is grant


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


def test_effective_user_id_from_grant() -> None:
    grant = _valid_grant(user_id="grant-user")
    req = RuntimeExecuteRequest(
        agent_instance_id="inst-42",
        input="hello",
        execution_grant=grant,
    )
    assert req.effective_user_id() == "grant-user"


def test_effective_user_id_from_runtime_context_fallback() -> None:
    req = RuntimeExecuteRequest(
        agent_id="my-agent",
        input="hello",
        runtime_context={"user_id": "ctx-user"},
    )
    assert req.effective_user_id() == "ctx-user"


def test_effective_team_id_from_grant() -> None:
    grant = _valid_grant(team_id="t-grant")
    req = RuntimeExecuteRequest(
        agent_instance_id="inst-42",
        input="hello",
        execution_grant=grant,
    )
    assert req.effective_team_id() == "t-grant"


def test_effective_session_id_prefers_top_level() -> None:
    req = RuntimeExecuteRequest(
        agent_id="my-agent",
        input="hello",
        session_id="top-level-session",
        runtime_context={"session_id": "ctx-session"},
    )
    assert req.effective_session_id() == "top-level-session"


def test_effective_session_id_falls_back_to_context() -> None:
    req = RuntimeExecuteRequest(
        agent_id="my-agent",
        input="hello",
        runtime_context={"session_id": "ctx-session"},
    )
    assert req.effective_session_id() == "ctx-session"


def test_message_property_alias() -> None:
    req = RuntimeExecuteRequest(agent_id="my-agent", input="the input text")
    assert req.message == "the input text"


def test_to_legacy_context_merges_fields() -> None:
    grant = _valid_grant(
        user_id="u-grant",
        team_id="t-grant",
        trace_id="trace-1",
        correlation_id="corr-1",
    )
    req = RuntimeExecuteRequest(
        agent_instance_id="inst-42",
        input="hello",
        session_id="sess-abc",
        checkpoint_id="cp-1",
        execution_grant=grant,
        runtime_context={"language": "fr"},
    )
    ctx = req.to_legacy_context()
    assert ctx["session_id"] == "sess-abc"
    assert ctx["checkpoint_id"] == "cp-1"
    assert ctx["user_id"] == "u-grant"
    assert ctx["team_id"] == "t-grant"
    assert ctx["agent_instance_id"] == "inst-42"
    assert ctx["trace_id"] == "trace-1"
    assert ctx["correlation_id"] == "corr-1"
    assert ctx["execution_action"] == "execute"
    assert ctx["language"] == "fr"


def test_to_legacy_context_without_grant() -> None:
    req = RuntimeExecuteRequest(
        agent_id="my-agent",
        input="hello",
        session_id="sess-xyz",
        checkpoint_id="cp-ctx",
        resume_payload={"choice_id": "ok"},
        runtime_context={
            "user_id": "ctx-user",
            "trace_id": "trace-ctx",
            "correlation_id": "corr-ctx",
        },
    )
    ctx = req.to_legacy_context()
    assert ctx["session_id"] == "sess-xyz"
    assert ctx["checkpoint_id"] == "cp-ctx"
    assert ctx["user_id"] == "ctx-user"
    assert ctx["trace_id"] == "trace-ctx"
    assert ctx["correlation_id"] == "corr-ctx"
    assert ctx["execution_action"] == "resume"


# ---------------------------------------------------------------------------
# validate_execution_grant helper
# ---------------------------------------------------------------------------


def test_validate_no_error_for_direct_template() -> None:
    req = RuntimeExecuteRequest(agent_id="my-agent", input="hello")
    # Direct template — no grant required, must not raise
    validate_execution_grant(req)


def test_validate_raises_when_managed_and_grant_missing() -> None:
    req = RuntimeExecuteRequest(
        agent_instance_id="inst-42",
        input="hello",
    )
    with pytest.raises(ExecutionGrantViolation, match="execution_grant is required"):
        validate_execution_grant(req)


def test_validate_raises_when_grant_expired() -> None:
    grant = _valid_grant(expires_at=_PAST)
    req = RuntimeExecuteRequest(
        agent_instance_id="inst-42",
        input="hello",
        execution_grant=grant,
    )
    with pytest.raises(ExecutionGrantViolation, match="expired"):
        validate_execution_grant(req)


def test_validate_raises_when_agent_instance_mismatches_grant() -> None:
    grant = _valid_grant(agent_instance_id="inst-other")
    req = RuntimeExecuteRequest(
        agent_instance_id="inst-42",
        input="hello",
        execution_grant=grant,
    )
    with pytest.raises(ExecutionGrantViolation, match="agent_instance_id mismatch"):
        validate_execution_grant(req)


def test_validate_passes_for_valid_managed_request() -> None:
    grant = _valid_grant()
    req = RuntimeExecuteRequest(
        agent_instance_id="inst-42",
        input="hello",
        execution_grant=grant,
    )
    validate_execution_grant(req, expected_action=ExecutionGrantAction.EXECUTE)


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

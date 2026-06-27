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

import pytest

from fred_sdk.contracts.context import RuntimeContext
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
        runtime_context=RuntimeContext(user_id="ctx-user"),
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
        runtime_context=RuntimeContext(language="fr"),
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
        runtime_context=RuntimeContext(
            user_id="ctx-user",
            trace_id="trace-ctx",
            correlation_id="corr-ctx",
        ),
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


# ---------------------------------------------------------------------------
# RUNTIME-07 Phase 0 — characterization of CURRENT (pre-hardening) behavior.
#
# These tests PIN today's grant-validation gaps so later phases get a
# red->green signal. They document holes, NOT the desired end state. When the
# named phase lands, UPDATE the assertion in place (do not delete) so the same
# test then proves the fix. See docs/swift/rfc/EXECUTION-GRANT-SECURITY-HARDENING-RFC.md.
#
#   F1 — grant is unsigned: nothing cryptographic exists to forge, and a fully
#        caller-fabricated grant passes validation.        (fixed in Phase 3)
#   F3 — audience is declared but never checked.            (fixed in Phase 1)
#   F4 — grant.team_id is never validated by the helper.    (fixed in Phase 1)
# ---------------------------------------------------------------------------


def test_char_f1_grant_envelope_supports_signing() -> None:
    """F1 — Phase 2a: the ExecutionGrant envelope now carries the signature
    fields (key_id/jti/signature). They default to None — an unsigned grant is
    still constructible — but `is_signed()` is False until control-plane signs
    it. Verification enforcement is wired in Phase 2c/2d."""
    grant = _valid_grant()
    assert hasattr(grant, "signature")
    assert hasattr(grant, "jti")
    assert hasattr(grant, "key_id")
    # Default (unsigned) grant: fields present but empty.
    assert grant.signature is None
    assert grant.is_signed() is False


def test_char_f1_fabricated_unsigned_grant_still_passes_structural_helper() -> None:
    """F1: structural validation alone still accepts a fabricated UNSIGNED grant
    (attacker-chosen user_id/team_id/audience). This is why signature
    verification (Phase 2c/2d) is required: once enforced, an unsigned or
    forged grant is rejected at the runtime regardless of structural validity."""
    forged = _valid_grant(
        user_id="attacker",
        team_id="victim-team",
        audience="https://any-runtime.example.com",
    )
    assert forged.is_signed() is False
    req = RuntimeExecuteRequest(
        agent_instance_id="inst-42",
        input="hello",
        execution_grant=forged,
    )
    # Structural helper does not verify signatures — it still passes today.
    validate_execution_grant(req)


def test_char_f3_audience_is_enforced_when_expected_audience_given() -> None:
    """F3 — FIXED (Phase 1). validate_for_execution / validate_execution_grant now
    reject a grant whose audience does not match the verifying runtime's own
    audience. When no expected_audience is supplied the check is skipped (opt-in
    per deployment)."""
    grant = _valid_grant(audience="/other-runtime/v1")

    # Mismatch is reported when an expected_audience is supplied.
    violations = grant.validate_for_execution(
        expected_agent_instance_id="inst-42",
        expected_audience="/fred/agents/v2",
    )
    assert any("audience mismatch" in v for v in violations)

    # Trailing-slash differences do not matter.
    ok = _valid_grant(audience="/fred/agents/v2/").validate_for_execution(
        expected_audience="/fred/agents/v2",
    )
    assert ok == []

    # Skipped when no expected_audience is given (backward-compatible).
    assert grant.validate_for_execution() == []

    req = RuntimeExecuteRequest(
        agent_instance_id="inst-42",
        input="hello",
        execution_grant=grant,
    )
    with pytest.raises(ExecutionGrantViolation, match="audience mismatch"):
        validate_execution_grant(req, expected_audience="/fred/agents/v2")
    # Still passes when audience is not enforced.
    validate_execution_grant(req)


def test_char_f4_team_binding_is_a_runtime_check_post_resolution() -> None:
    """F4 — FIXED (Phase 1) at the runtime layer. The sdk helper deliberately
    does NOT bind team_id (the authoritative owner_team_id is only known after
    control-plane resolution), but the contract DOES expose expected_team_id so
    the runtime can assert grant.team_id == resolved owner_team_id. The runtime
    wiring is verified in fred-runtime tests (_validate_grant_team_binding)."""
    grant = _valid_grant(team_id="some-unrelated-team")

    # The mechanism the runtime uses: validate_for_execution flags team mismatch.
    violations = grant.validate_for_execution(expected_team_id="owner-team")
    assert any("team_id mismatch" in v for v in violations)

    # The pre-resolution helper still accepts (binding happens at the runtime).
    req = RuntimeExecuteRequest(
        agent_instance_id="inst-42",
        input="hello",
        execution_grant=grant,
    )
    validate_execution_grant(req)


# ---------------------------------------------------------------------------
# RUNTIME-07 Phase 2a — signature envelope + resolution claims
# ---------------------------------------------------------------------------


def _rsa_signer():
    """Build a LocalKeypairSigner + matching GrantVerifier for tests."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fred_core.security.keyless_signer import GrantVerifier, LocalKeypairSigner

    pem = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    signer = LocalKeypairSigner(pem, key_id="cp-key-1")
    verifier = GrantVerifier.from_public_key_pem(
        signer.public_key_pem(), key_id="cp-key-1"
    )
    return signer, verifier


def test_grant_resolution_claims_roundtrip() -> None:
    from fred_sdk.contracts.models import AgentTuning

    tuning = AgentTuning(role="Sentinel", description="reports team scope")
    grant = _valid_grant().model_copy(
        update={
            "template_agent_id": "sentinel.react.v2",
            "owner_team_id": "fredlab",
            "tuning": tuning,
        }
    )
    restored = ExecutionGrant.model_validate(grant.model_dump(mode="json"))
    assert restored.template_agent_id == "sentinel.react.v2"
    assert restored.owner_team_id == "fredlab"
    assert restored.tuning is not None and restored.tuning.role == "Sentinel"


def test_canonical_payload_excludes_signature_and_is_deterministic() -> None:
    grant = _valid_grant().model_copy(update={"key_id": "cp-key-1", "jti": "g-1"})
    payload = grant.canonical_payload()

    # Stable across calls.
    assert grant.canonical_payload() == payload
    # Excludes the signature field — setting it does not change the signed bytes.
    signed = grant.model_copy(update={"signature": "AAAAdummy"})
    assert signed.canonical_payload() == payload
    # But DOES cover key_id / jti / resolution claims.
    assert b"cp-key-1" in payload and b"g-1" in payload


def test_is_signed_reflects_envelope() -> None:
    assert _valid_grant().is_signed() is False
    partial = _valid_grant().model_copy(update={"key_id": "cp-key-1"})
    assert partial.is_signed() is False  # needs both key_id AND signature
    full = _valid_grant().model_copy(update={"key_id": "cp-key-1", "signature": "sig"})
    assert full.is_signed() is True


def test_grant_sign_then_verify_end_to_end() -> None:
    """The canonical issue→verify flow: set key_id/jti, sign canonical_payload(),
    attach the signature, then verify it round-trips and tamper is detected."""
    from fred_core.security.keyless_signer import decode_signature, encode_signature

    signer, verifier = _rsa_signer()

    base = _valid_grant().model_copy(update={"key_id": signer.key_id, "jti": "g-1"})
    signature = signer.sign(base.canonical_payload())
    signed = base.model_copy(update={"signature": encode_signature(signature)})

    assert signed.is_signed()
    assert signed.signature is not None and signed.key_id is not None
    raw_sig = decode_signature(signed.signature)
    assert verifier.verify(signed.canonical_payload(), raw_sig, signed.key_id)

    # Tampering any signed field invalidates the signature.
    tampered = signed.model_copy(update={"team_id": "intruder"})
    assert not verifier.verify(tampered.canonical_payload(), raw_sig, signed.key_id)


def test_sign_grant_then_verify_helpers_roundtrip() -> None:
    """The control-plane / runtime glue: sign_grant() then verify_grant_signature()."""
    from fred_sdk.contracts.grant_signing import sign_grant, verify_grant_signature

    signer, verifier = _rsa_signer()
    signed = sign_grant(_valid_grant(), signer, jti="g-42")

    assert signed.is_signed()
    assert signed.key_id == signer.key_id
    assert signed.jti == "g-42"
    assert verify_grant_signature(signed, verifier) is True


def test_sign_grant_autogenerates_jti_when_absent() -> None:
    from fred_sdk.contracts.grant_signing import sign_grant

    signer, _ = _rsa_signer()
    signed = sign_grant(_valid_grant(), signer)
    assert signed.jti is not None and len(signed.jti) > 0


def test_verify_grant_signature_rejects_unsigned_and_tampered() -> None:
    from fred_sdk.contracts.grant_signing import sign_grant, verify_grant_signature

    signer, verifier = _rsa_signer()

    # Unsigned grant → False.
    assert verify_grant_signature(_valid_grant(), verifier) is False

    # Tampered after signing → False (any signed field).
    signed = sign_grant(_valid_grant(), signer)
    tampered = signed.model_copy(update={"agent_instance_id": "inst-evil"})
    assert verify_grant_signature(tampered, verifier) is False

    # A grant signed by a rogue key but claiming our key_id → False.
    rogue_signer, _ = _rsa_signer()
    rogue = sign_grant(_valid_grant(), rogue_signer).model_copy(
        update={"key_id": signer.key_id}
    )
    assert verify_grant_signature(rogue, verifier) is False

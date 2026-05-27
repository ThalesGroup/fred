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
Phase 1 runtime execution contract: identity, authorization, and request models.

Why this module exists:
- Establishes fred-sdk as the single authoritative source of truth for the
  frontend-facing runtime execution contract.
- Every execution is team-scoped and attributable to user_id + team_id +
  agent_instance_id.
- The ExecutionGrant is the authorization envelope issued by control-plane;
  runtime pods validate it but do not decide access.

Architectural boundary (MUST NOT cross):
- Fred code must NOT implement pod discovery, dynamic routing, in-app
  load-balancing, or topology-aware failover. Those concerns belong to:
  Kubernetes Service, Ingress/Gateway, DNS, namespace isolation, and Argo CD.
- Fred code is responsible for: endpoint protection, RBAC/REBAC checks,
  team-scoped managed agent authorization, grant issuance/validation, and
  runtime execution contracts.

How to use:
- Prefer managed execution: set agent_instance_id + execution_grant.
- Use agent_id (direct template) only for internal/dev compatibility.
- session_id is the primary continuity key across normal turns and HITL resumes.
- checkpoint_id enables precise resume from a specific graph snapshot.

Example::

    grant = ExecutionGrant(
        user_id="u-1",
        team_id="t-1",
        agent_instance_id="inst-42",
        action=ExecutionGrantAction.EXECUTE,
        audience="https://runtime.example.com",
        issued_at=1714000000,
        expires_at=1714003600,
    )
    req = RuntimeExecuteRequest(
        input="What is the status of project X?",
        session_id="sess-abc",
        agent_instance_id="inst-42",
        execution_grant=grant,
    )
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .context import ConversationTurn, RuntimeContext
from .models import TuningValue


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


# ---------------------------------------------------------------------------
# Execution identity
# ---------------------------------------------------------------------------


class ActorContext(FrozenModel):
    """
    Identity of the user performing the execution.

    Why this exists:
    - Every execution must be attributable to a concrete user.
    - principal carries optional subject metadata (e.g. username, email) for
      audit and diagnostics without coupling the contract to Keycloak internals.

    How to use:
    - Build from the JWT claims extracted by the runtime's OIDC middleware.
    - Do not store secrets or tokens in this model.
    """

    user_id: str = Field(
        ..., min_length=1, description="Stable user identifier (e.g. Keycloak sub)."
    )
    principal: str | None = Field(
        default=None,
        description="Optional human-readable subject identifier (username or email). Diagnostics only.",
    )


class TeamType(str, Enum):
    PERSONAL = "personal"
    COLLABORATIVE = "collaborative"


class TeamContext(FrozenModel):
    """
    Team scope for one execution.

    Why this exists:
    - All agent execution is team-scoped; team_id is mandatory and explicit.
    - team_type distinguishes personal workspaces from collaborative teams,
      enabling team-type-aware policy enforcement downstream.

    How to use:
    - Always set team_id. Never execute without a team context.
    - team_type is optional; set it when known from control-plane enrollment.
    """

    team_id: str = Field(..., min_length=1, description="Stable team identifier.")
    team_type: TeamType | None = Field(
        default=None,
        description="Optional team type distinguishing personal from collaborative teams.",
    )


class ExecutionTarget(FrozenModel):
    """
    The managed agent instance that will be executed.

    Why this exists:
    - agent_instance_id is the preferred primary execution target for the frontend.
    - underlying_agent_ref is for diagnostics only (e.g. the template agent_id
      that was instantiated); it must not influence routing or security decisions.

    How to use:
    - Set agent_instance_id when the frontend has a control-plane-managed instance.
    - Set underlying_agent_ref only when the template identity is needed for logging.
    """

    agent_instance_id: str = Field(
        ...,
        min_length=1,
        description="Managed agent instance identifier assigned by control-plane.",
    )
    underlying_agent_ref: str | None = Field(
        default=None,
        description=(
            "Optional template agent reference for diagnostics. "
            "MUST NOT influence routing or access-control decisions."
        ),
    )


class TraceContext(FrozenModel):
    """
    Traceability identifiers propagated through one execution.

    Why this exists:
    - Every execution turn must be traceable for observability and audit.
    - session_id and checkpoint_id are included here for correlation purposes;
      they are also present in RuntimeExecuteRequest as first-class fields.

    How to use:
    - Generate request_id and correlation_id at request ingress.
    - Propagate through all downstream calls and log entries.
    - session_id and checkpoint_id mirror the request-level values for
      structured log correlation.
    """

    request_id: str = Field(
        ..., min_length=1, description="Unique identifier for this HTTP request."
    )
    trace_id: str | None = Field(
        default=None, description="Distributed trace identifier (e.g. OpenTelemetry)."
    )
    correlation_id: str = Field(
        ...,
        min_length=1,
        description="Correlation identifier linking related operations across services.",
    )
    session_id: str | None = Field(
        default=None,
        description="Session identifier for multi-turn continuity correlation.",
    )
    checkpoint_id: str | None = Field(
        default=None,
        description="Checkpoint identifier for precise resume correlation.",
    )


# ---------------------------------------------------------------------------
# Authorization envelope
# ---------------------------------------------------------------------------


class ExecutionGrantAction(str, Enum):
    EXECUTE = "execute"
    RESUME = "resume"


class ExecutionGrant(FrozenModel):
    """
    Authorization envelope issued by control-plane for one execution.

    Architectural constraints:
    - Issued ONLY by control-plane; runtime pods validate but do not issue grants.
    - Authorizes access to a LOGICAL execution scope: (user, team, agent_instance).
    - MUST NOT contain infrastructure secrets, database credentials, or
      internal connection strings. Any such field is a contract violation.
    - audience identifies the intended runtime service/endpoint so the runtime
      can reject grants issued for a different target.
    - Runtime must reject: missing grant, expired grant, mismatched team/session/
      agent_instance, and invalid resume against non-waiting checkpoint state.

    How to use:
    - The frontend obtains this from control-plane before calling the runtime.
    - The runtime validates it before executing any agent turn.
    - storage_scope, when present, names the logical persistence namespace for
      session state — it must never be a raw connection string or secret.

    Example::

        grant = ExecutionGrant(
            user_id="u-1", team_id="t-1", agent_instance_id="inst-42",
            action=ExecutionGrantAction.EXECUTE,
            audience="https://runtime.fred.example.com",
            issued_at=1714000000, expires_at=1714003600,
        )
    """

    user_id: str = Field(..., min_length=1)
    team_id: str = Field(..., min_length=1)
    agent_instance_id: str = Field(..., min_length=1)
    action: ExecutionGrantAction
    audience: str = Field(
        ...,
        min_length=1,
        description="Intended runtime service/endpoint URL or identifier.",
    )
    issued_at: int = Field(..., description="Grant issuance time as a Unix timestamp.")
    expires_at: int = Field(..., description="Grant expiry time as a Unix timestamp.")
    scopes: tuple[str, ...] = Field(
        default=(),
        description="Optional permission scopes granted for this execution.",
    )
    trace_id: str | None = None
    correlation_id: str | None = None
    storage_scope: str | None = Field(
        default=None,
        description=(
            "Optional logical storage scope name for session state. "
            "MUST NOT be a raw connection string, secret, or infrastructure credential."
        ),
    )

    def is_expired(self, *, now: int | None = None) -> bool:
        """Return True when this grant has passed its expiry timestamp."""
        return (now if now is not None else int(time.time())) >= self.expires_at

    def is_not_yet_valid(self, *, now: int | None = None) -> bool:
        """Return True when this grant's issued_at is in the future (clock skew guard)."""
        return (now if now is not None else int(time.time())) < self.issued_at

    def validate_for_execution(
        self,
        *,
        expected_action: ExecutionGrantAction | None = None,
        expected_team_id: str | None = None,
        expected_agent_instance_id: str | None = None,
        now: int | None = None,
    ) -> list[str]:
        """
        Structural validation of the grant against execution-time expectations.

        Returns a list of violation strings (empty = valid).

        Why this is structural only:
        - Phase 1 freezes the contract and structural checks.
        - Cryptographic signature verification requires a public-key registry
          from control-plane and is added in a subsequent phase.

        How to use:
        - Call from the execute endpoints before running the agent.
        - Reject the request when the returned list is non-empty.

        Example::

            violations = grant.validate_for_execution(
                expected_action=ExecutionGrantAction.EXECUTE,
                expected_team_id="t-1",
                expected_agent_instance_id="inst-42",
            )
            if violations:
                raise HTTPException(403, detail=violations)
        """
        violations: list[str] = []
        t = now if now is not None else int(time.time())

        if self.is_expired(now=t):
            violations.append(f"grant expired at {self.expires_at} (now={t})")
        if self.is_not_yet_valid(now=t):
            violations.append(
                f"grant not yet valid: issued_at={self.issued_at} (now={t})"
            )

        if expected_action is not None and self.action != expected_action:
            violations.append(
                f"grant action mismatch: expected={expected_action.value} got={self.action.value}"
            )
        if expected_team_id is not None and self.team_id != expected_team_id:
            violations.append(
                f"grant team_id mismatch: expected={expected_team_id!r} got={self.team_id!r}"
            )
        if (
            expected_agent_instance_id is not None
            and self.agent_instance_id != expected_agent_instance_id
        ):
            violations.append(
                f"grant agent_instance_id mismatch: "
                f"expected={expected_agent_instance_id!r} got={self.agent_instance_id!r}"
            )
        return violations


# ---------------------------------------------------------------------------
# Runtime execution request
# ---------------------------------------------------------------------------


class RuntimeExecuteRequest(BaseModel):
    """
    Frontend-facing execution request for fred-runtime endpoints.

    This is the frozen Phase 1 contract between the frontend and runtime pods.
    It replaces the private _AgentExecuteRequest from earlier iterations.

    Execution paths:
    1. Managed (preferred frontend path):
       - Set agent_instance_id + execution_grant
       - control-plane resolved which pod and instance to use
       - Runtime validates the grant before executing

    2. Direct template (internal/dev only):
       - Set agent_id (the registered template agent_id)
       - No execution_grant required
       - Not suitable for production frontend calls

    Session/checkpoint semantics:
    - session_id is the primary continuity key — keep stable across turns and resumes
    - checkpoint_id enables precise resume from a specific graph snapshot
    - resume_payload carries HITL answer data; when present, input is ignored

    Architectural constraint:
    - This model must never grow fields for infrastructure routing (pod URLs,
      database DSNs, service endpoints). Those are Kubernetes concerns.
    """

    # Execution target — exactly one must be set
    agent_instance_id: str | None = Field(
        default=None,
        min_length=1,
        description="Managed agent instance ID (preferred). Requires execution_grant.",
    )
    agent_id: str | None = Field(
        default=None,
        min_length=1,
        description="Direct template agent_id. For internal/dev use only.",
    )

    # Turn input
    input: str = Field(
        default="",
        description="User turn input. Ignored when resume_payload is set (HITL resume).",
    )

    # Session / checkpoint continuity
    session_id: str | None = Field(
        default=None,
        description="Session identifier for multi-turn continuity. Keep stable across turns.",
    )
    checkpoint_id: str | None = Field(
        default=None,
        description="Checkpoint identifier for precise graph-state resume.",
    )

    # HITL resume
    resume_payload: Any | None = Field(
        default=None,
        description=(
            "HITL resume data returned by the user after an AwaitingHumanRuntimeEvent. "
            "When set, input is ignored and the graph resumes from its checkpointed state."
        ),
    )

    # Authorization (required for managed execution)
    execution_grant: ExecutionGrant | None = Field(
        default=None,
        description=(
            "Authorization envelope issued by control-plane. "
            "Required when agent_instance_id is set. "
            "Runtime MUST reject requests with a missing or invalid grant."
        ),
    )

    # Optional per-request runtime context (typed)
    runtime_context: RuntimeContext | None = Field(
        default=None,
        description=(
            "Per-request execution context carrying per-turn user retrieval selections "
            "(library IDs, search policy, context prompt text) and user auth delegation. "
            "Group A identity fields (user_id, team_id, session_id) in this model are "
            "superseded by execution_grant for managed execution — set them only in dev/direct mode. "
            "Group B auth fields (access_token, refresh_token) are required when the runtime "
            "calls knowledge-flow backend on behalf of the user."
        ),
    )

    # Multi-turn memory — agent-to-agent context seeding
    invocation_turns: tuple[ConversationTurn, ...] = Field(
        default=(),
        description=(
            "Prior conversation turns forwarded by the calling agent. "
            "Used to seed memory in sub-agents invoked via context.invoke_agent(). "
            "Graph sub-agents receive history through build_turn_state; "
            "ReAct sub-agents receive it as a leading SystemMessage."
        ),
    )

    # Dev / CLI — inline tuning for direct template execution
    inline_tuning: dict[str, TuningValue] | None = Field(
        default=None,
        description=(
            "Optional tuning value overrides for direct template execution (agent_id mode). "
            "Ignored when agent_instance_id is set. "
            "Intended for CLI and dev tooling — not for production frontend calls."
        ),
    )

    @model_validator(mode="after")
    def _validate_execution_target(self) -> "RuntimeExecuteRequest":
        """
        Enforce invariants for execution target and turn shape.

        - Exactly one of agent_id or agent_instance_id must be set.
        - When resume_payload is absent, input must have non-empty content.
        - When agent_instance_id is set, execution_grant should be provided
          (warning only at contract level; runtime enforces rejection).
        """
        has_instance = bool(self.agent_instance_id)
        has_template = bool(self.agent_id)
        if has_instance == has_template:
            raise ValueError("Provide exactly one of agent_id or agent_instance_id.")
        if self.resume_payload is None and not self.input.strip():
            raise ValueError("input is required when resume_payload is not set.")
        return self

    # ------------------------------------------------------------------
    # Compatibility helpers
    # ------------------------------------------------------------------

    def effective_user_id(self) -> str | None:
        """Return user_id from execution_grant or runtime_context, in that order."""
        if self.execution_grant is not None:
            return self.execution_grant.user_id
        return self.runtime_context.user_id if self.runtime_context else None

    def effective_team_id(self) -> str | None:
        """Return team_id from execution_grant or runtime_context, in that order."""
        if self.execution_grant is not None:
            return self.execution_grant.team_id
        return self.runtime_context.team_id if self.runtime_context else None

    def effective_session_id(self) -> str | None:
        """Return session_id, preferring the top-level field over runtime_context."""
        if self.session_id is not None:
            return self.session_id
        return self.runtime_context.session_id if self.runtime_context else None

    # Convenience alias used by internal callers that expect "message"
    @property
    def message(self) -> str:
        return self.input

    # Build a context dict compatible with the legacy internal plumbing
    def to_legacy_context(self) -> dict[str, Any]:
        """
        Produce a context dict compatible with the internal runtime plumbing.

        Why this exists:
        - The internal _iterate_runtime_event_payloads helper reads execution
          metadata from a flat dict for backward compatibility.
        - This helper centralises the projection so callers do not scatter
          .get() calls across the codebase.

        This method is intentionally INTERNAL and is not part of the frozen
        frontend-facing contract. It will be removed once all internal plumbing
        migrates to the typed contract fields.
        """
        ctx: dict[str, Any] = {}
        if self.runtime_context:
            ctx.update(self.runtime_context.model_dump(exclude_none=True))
        if self.session_id is not None:
            ctx["session_id"] = self.session_id
        if self.checkpoint_id is not None:
            ctx["checkpoint_id"] = self.checkpoint_id
        user_id = self.effective_user_id()
        if user_id:
            ctx["user_id"] = user_id
        team_id = self.effective_team_id()
        if team_id:
            ctx["team_id"] = team_id
        if self.agent_instance_id is not None:
            ctx["agent_instance_id"] = self.agent_instance_id
        trace_id = (
            self.execution_grant.trace_id
            if self.execution_grant is not None
            else (self.runtime_context.trace_id if self.runtime_context else None)
        )
        if trace_id:
            ctx["trace_id"] = trace_id
        correlation_id = (
            self.execution_grant.correlation_id
            if self.execution_grant is not None
            else (self.runtime_context.correlation_id if self.runtime_context else None)
        )
        if correlation_id:
            ctx["correlation_id"] = correlation_id
        ctx["execution_action"] = (
            ExecutionGrantAction.RESUME.value
            if self.resume_payload is not None
            else ExecutionGrantAction.EXECUTE.value
        )
        return ctx


# ---------------------------------------------------------------------------
# Grant validation helpers
# ---------------------------------------------------------------------------


class ExecutionGrantViolation(Exception):
    """Raised when ExecutionGrant validation fails at the execute endpoint."""

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__("; ".join(violations))


def validate_execution_grant(
    request: RuntimeExecuteRequest,
    *,
    expected_action: ExecutionGrantAction = ExecutionGrantAction.EXECUTE,
) -> None:
    """
    Validate the ExecutionGrant in a RuntimeExecuteRequest.

    Raises ExecutionGrantViolation when the grant is absent (for managed
    execution) or structurally invalid.

    Why this exists:
    - Centralises grant validation so every execute endpoint applies the same
      checks without duplicating logic.
    - Runtime pods must validate; control-plane decides access.

    How to use:
    - Call from execute route handlers before invoking the agent.
    - Catch ExecutionGrantViolation and convert to HTTP 403.

    Note on cryptographic verification:
    - Phase 1 performs structural validation only (expiry, field consistency).
    - Cryptographic signature verification (e.g. JWT signing key from
      control-plane) is out of scope for Phase 1 and will be added in a
      subsequent phase once the key distribution mechanism is defined.

    Example::

        try:
            validate_execution_grant(request)
        except ExecutionGrantViolation as exc:
            raise HTTPException(403, detail=str(exc))
    """
    if request.agent_instance_id is None:
        # Direct template execution — no grant required
        return

    if request.execution_grant is None:
        raise ExecutionGrantViolation(
            ["execution_grant is required for managed agent instance execution"]
        )

    grant = request.execution_grant
    violations = grant.validate_for_execution(
        expected_action=expected_action,
        expected_agent_instance_id=request.agent_instance_id,
    )
    if violations:
        raise ExecutionGrantViolation(violations)


# ---------------------------------------------------------------------------
# Checkpoint and history access semantics (documentation)
# ---------------------------------------------------------------------------

# Architectural note (Phase 1 — checkpoint/history access semantics):
#
# fred-runtime is a CONSUMER of persisted checkpoint state, not its ownership
# authority. Control-plane owns the mapping from session to checkpoint storage.
#
# Runtime MUST validate before resuming:
# - session_id is authorized by the ExecutionGrant
# - checkpoint_id (when provided) belongs to the authorized session_id
# - checkpoint_id is in a resumable state
# - if resuming HITL, the checkpoint is in a waiting state compatible with
#   the provided resume_payload
#
# Separation of concerns:
# - checkpoint state  = runtime-facing graph persistence (LangGraph checkpointer)
# - history state     = UI-facing / audit-facing typed interaction history
#
# Persistence infrastructure details (connection strings, credentials, table
# names) MUST remain runtime-environment concerns and must never appear in
# frontend-facing contracts.

# ---------------------------------------------------------------------------
# Kubernetes-native platform boundary (documentation)
# ---------------------------------------------------------------------------

# Fred code MUST NOT implement the following concerns — they are Kubernetes
# platform responsibilities:
# - Pod discovery or dynamic runtime pod listing
# - Service-to-pod resolution (use Kubernetes Service + DNS)
# - Custom in-app load balancing or traffic distribution
# - Topology-aware failover logic
# - Runtime endpoint topology management beyond a single configured URL
#
# Fred code IS responsible for:
# - Endpoint protection (Keycloak RBAC, OpenFGA REBAC)
# - Team-scoped managed agent authorization (ExecutionGrant validation)
# - Runtime execution contracts (this module)
# - History and checkpoint access validation
# - Managed execution semantics (agent_instance_id resolution via control-plane)
#
# Routing, exposure, and discovery belong to:
# - Kubernetes Service
# - Ingress / Gateway API
# - Namespace isolation and DNS stable names
# - Argo CD / GitOps deployment descriptors

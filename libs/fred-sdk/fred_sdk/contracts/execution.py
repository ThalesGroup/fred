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
Runtime execution contract: identity and request models (RUNTIME-07 rev. 2).

Why this module exists:
- Establishes fred-sdk as the single authoritative source of truth for the
  frontend-facing runtime execution contract.
- Every execution is team-scoped and attributable to user_id + team_id +
  agent_instance_id (carried in runtime_context).

Authorization model (RUNTIME-07 rev. 2):
- The control-plane issues NO signed grant or capability. Identity is the
  caller's Keycloak JWT (Authorization: Bearer); authorization is decided at the
  agent pod by an OpenFGA check on the caller's team, per request. The pod
  resolves a managed instance's template + tuning from the control-plane
  team-scoped binding (ReBAC-gated) — config, never a capability.

Architectural boundary (MUST NOT cross):
- Fred code must NOT implement pod discovery, dynamic routing, in-app
  load-balancing, or topology-aware failover. Those concerns belong to:
  Kubernetes Service, Ingress/Gateway, DNS, namespace isolation, and Argo CD.
- Fred code is responsible for: endpoint protection, RBAC/REBAC checks,
  team-scoped managed agent authorization, and runtime execution contracts.

How to use:
- Prefer managed execution: set agent_instance_id (team comes from runtime_context).
- Use agent_id (direct template) only for internal/dev compatibility.
- session_id is the primary continuity key across normal turns and HITL resumes.
- checkpoint_id enables precise resume from a specific graph snapshot (legacy
  Graph V2 only); interrupt_id is the ReAct V2 equivalent — mutually
  exclusive, never both set (see RuntimeExecuteRequest's own docstring).

Example::

    req = RuntimeExecuteRequest(
        input="What is the status of project X?",
        session_id="sess-abc",
        agent_instance_id="inst-42",
        runtime_context=RuntimeContext(user_id="u-1", team_id="t-1"),
    )
"""

from __future__ import annotations

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
# Execution action
# ---------------------------------------------------------------------------


class ExecutionGrantAction(str, Enum):
    EXECUTE = "execute"
    RESUME = "resume"


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
       - Set agent_instance_id + runtime_context.team_id
       - The pod authorizes the caller (Keycloak JWT + OpenFGA on team_id) and
         resolves the instance template+tuning from the control-plane (no grant)

    2. Direct template (internal/dev only):
       - Set agent_id (the registered template agent_id)
       - Not suitable for production frontend calls

    Session/checkpoint semantics:
    - session_id is the primary continuity key — keep stable across turns and resumes
    - checkpoint_id enables precise resume from a specific graph snapshot (legacy
      Graph V2 only) — interrupt_id is the ReAct V2 equivalent, mutually
      exclusive with checkpoint_id and only meaningful with resume_payload set
    - resume_payload carries HITL answer data; when present, input is ignored

    Architectural constraint:
    - This model must never grow fields for infrastructure routing (pod URLs,
      database DSNs, service endpoints). Those are Kubernetes concerns.
    """

    # Execution target — exactly one must be set
    agent_instance_id: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Managed agent instance ID (preferred). The pod authorizes the caller "
            "(Keycloak JWT + OpenFGA) on runtime_context.team_id."
        ),
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
        description=(
            "Real checkpointer-storage identifier for precise graph-state "
            "resume. Legacy Graph V2 runtime only — see interrupt_id for "
            "ReAct V2 HITL resume."
        ),
    )
    interrupt_id: str | None = Field(
        default=None,
        description=(
            "LangGraph's own Interrupt.id for the ReAct V2 HITL occurrence "
            "being resumed (#2216). Echoed back verbatim from the "
            "AwaitingHumanRuntimeEvent.request.interrupt_id the frontend "
            "received. Required (and validated against the currently "
            "pending interrupt) whenever resume_payload targets a ReAct V2 "
            "agent — never used for the legacy Graph V2 runtime, which uses "
            "checkpoint_id instead."
        ),
    )

    # HITL resume
    resume_payload: Any | None = Field(
        default=None,
        description=(
            "HITL resume data returned by the user after an AwaitingHumanRuntimeEvent. "
            "When set, input is ignored and the graph resumes from its checkpointed state."
        ),
    )

    # Optional per-request runtime context (typed)
    runtime_context: RuntimeContext | None = Field(
        default=None,
        description=(
            "Per-request execution context carrying per-turn user retrieval selections "
            "(library IDs, search policy, context prompt text) and user auth delegation. "
            "Group A identity fields (user_id, team_id, session_id): for managed execution "
            "the pod authorizes the caller against OpenFGA on team_id, so team_id MUST be set. "
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

    # Chat-time capability turn options (CAPAB-01 #1976, RFC §3.5)
    turn_options: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Per-capability typed chat-time values, keyed by capability id. Each "
            "slice is validated at turn start against the owning capability's "
            "TurnOptionsModel; an unknown capability id or an invalid slice is a "
            "typed 422 (RFC §3.5). The envelope is generic — the key is the "
            "discriminator — but every leaf is a typed model exported to OpenAPI, "
            "so each composer widget writes into turn_options[capability_id]."
        ),
    )

    @model_validator(mode="after")
    def _validate_execution_target(self) -> "RuntimeExecuteRequest":
        """
        Enforce invariants for execution target and turn shape.

        - Exactly one of agent_id or agent_instance_id must be set.
        - When resume_payload is absent, input must have non-empty content.
        - For managed (agent_instance_id) execution the pod authorizes the caller
          against OpenFGA on runtime_context.team_id (enforced at the runtime).
        - checkpoint_id (legacy Graph V2) and interrupt_id (ReAct V2) are
          mutually exclusive — never both set on the same request (#2216).
          Rejecting this at the wire boundary closes the gap where a runtime
          resume-validation lookup could otherwise be steered at a
          client-chosen checkpoint_id instead of the thread's actual latest
          checkpoint: with the two fields exclusive, a request carrying
          interrupt_id can never also carry checkpoint_id, so the runtime's
          checkpoint lookup always falls through to "the thread's latest
          checkpoint" for a ReAct V2 resume.
        - interrupt_id is only meaningful alongside resume_payload — it
          identifies WHICH pending interrupt a resume answers, so it has no
          purpose without a resume in flight.
        """
        has_instance = bool(self.agent_instance_id)
        has_template = bool(self.agent_id)
        if has_instance == has_template:
            raise ValueError("Provide exactly one of agent_id or agent_instance_id.")
        if self.resume_payload is None and not self.input.strip():
            raise ValueError("input is required when resume_payload is not set.")
        if self.checkpoint_id is not None and self.interrupt_id is not None:
            raise ValueError(
                "checkpoint_id and interrupt_id are mutually exclusive: "
                "checkpoint_id identifies a legacy Graph V2 resume, "
                "interrupt_id identifies a ReAct V2 resume — never both at "
                "once."
            )
        if self.interrupt_id is not None and self.resume_payload is None:
            raise ValueError("interrupt_id is only valid together with resume_payload.")
        return self

    # ------------------------------------------------------------------
    # Compatibility helpers
    # ------------------------------------------------------------------

    def effective_user_id(self) -> str | None:
        """Return user_id from runtime_context (the authenticated caller identity)."""
        return self.runtime_context.user_id if self.runtime_context else None

    def effective_team_id(self) -> str | None:
        """Return the team_id the caller is acting in, from runtime_context."""
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
        if self.interrupt_id is not None:
            ctx["interrupt_id"] = self.interrupt_id
        user_id = self.effective_user_id()
        if user_id:
            ctx["user_id"] = user_id
        team_id = self.effective_team_id()
        if team_id:
            ctx["team_id"] = team_id
        if self.agent_instance_id is not None:
            ctx["agent_instance_id"] = self.agent_instance_id
        trace_id = self.runtime_context.trace_id if self.runtime_context else None
        if trace_id:
            ctx["trace_id"] = trace_id
        correlation_id = (
            self.runtime_context.correlation_id if self.runtime_context else None
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
# Checkpoint and history access semantics (documentation)
# ---------------------------------------------------------------------------

# Architectural note (Phase 1 — checkpoint/history access semantics):
#
# fred-runtime is a CONSUMER of persisted checkpoint state, not its ownership
# authority. Control-plane owns the mapping from session to checkpoint storage.
#
# Runtime MUST validate before resuming:
# - the caller is authorized for the session's team (Keycloak JWT + OpenFGA)
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
# - Team-scoped managed agent authorization (pod-side OpenFGA check, no grant)
# - Runtime execution contracts (this module)
# - History and checkpoint access validation
# - Managed execution semantics (agent_instance_id resolution via control-plane)
#
# Routing, exposure, and discovery belong to:
# - Kubernetes Service
# - Ingress / Gateway API
# - Namespace isolation and DNS stable names
# - Argo CD / GitOps deployment descriptors

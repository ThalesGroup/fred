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

"""ToolObservabilityMiddleware — tool-call KPI timer + audit events for EVERY
tool call the graph executes (#2011).

Why this module exists:
- `ContextAwareTool` (`fred_runtime.common.context_aware_tool`) used to be the
  ONLY place emitting `agent.tool_latency_ms` / `agent.tool_failed_total` KPI
  and `agent.tool.invocation.{started,completed}` audit events. It is only
  ever instantiated by `mcp_toolkit.py`, i.e. only for MCP-catalog tools.
  Native capability tools (e.g. `DocumentAccessCapability`'s
  `search_documents_using_vectorization`, a plain `@tool`-decorated function
  shipped on the capability's own `AgentMiddleware.tools`) never passed
  through `ContextAwareTool` at all, so they produced zero KPI samples and
  zero audit events — a real gap in the "every tool invocation is audited"
  guarantee documented in `docs/swift/platform/OBSERVABILITY-AND-AUDIT.md`
  §9.
- `AgentMiddleware.awrap_tool_call` is the one chokepoint `create_agent`'s
  `ToolNode` routes every tool call through, regardless of whether the tool
  came from the MCP toolkit or a capability's own middleware. Centralizing
  here fixes the gap for every tool at once, instead of patching each tool
  source separately.

Semantics preserved from `ContextAwareTool` (do not drift from these):
- metric names `agent.tool_latency_ms` / `agent.tool_failed_total` are
  unchanged — Grafana dashboards built against them keep working, just with
  full coverage now
- audit outcome is one of `"succeeded"` | `"failed"` | `"cancelled"` — never
  `"refused"`. A HITL-refused proposal is turned back to the model by
  `FredHitlMiddleware.aafter_model` (via `jump_to: "model"`) before the tool
  node — and therefore this middleware — ever runs, so a refusal never
  produces a `"started"` event (a proposal is not an action, see
  `docs/swift/platform/OBSERVABILITY-AND-AUDIT.md`)
- never log tool arguments, tool results, or any raw content here — only
  identifiers and bounded outcome/error fields

Known gap NOT closed by this middleware (flagged, not fixed, here — see
#2011 follow-up discussion): `ContextAwareTool._run`/`_arun` deliberately
catches exceptions raised by the underlying MCP tool call and returns a
formatted error STRING instead of raising (see its "CRITICAL: Return error
as text to preserve chat history integrity" comment). LangChain's `BaseTool`
machinery only sets `ToolMessage.status="error"` when a `ToolException` (or
another exception `handle_tool_errors` catches) actually propagates out of
`_run`/`_arun` — since `ContextAwareTool` never raises, `awrap_tool_call`
here sees a normal, successful `handler(request)` return for these
already-caught MCP-adapter failures, and reports them as `"succeeded"`. This
narrow case regressed relative to `ContextAwareTool`'s own previous internal
instrumentation (which wrapped the raw underlying call directly and could
see the exception before it was swallowed). Fixing it would require either
raising `ToolException` from `ContextAwareTool` (a behavior change to the
"never orphan a tool call" design) or a structured error signal in the
returned content/artifact — out of scope for this change; see the
implementation report for #2011.

How to use:
- always part of the frame, positioned next to `TracingKpiMiddleware` (see
  `frame.py` for the exact slot and why)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import nullcontext
from typing import Any, Optional

from fred_core.common.team_id import is_personal_team_id
from fred_core.kpi import BaseKPIWriter, KPIActor
from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import RebacReference, TeamPermission
from fred_sdk.contracts.context import BoundRuntimeContext
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages.tool import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from fred_runtime.common.context_aware_tool import ContextAwareTool
from fred_runtime.runtime_context import get_runtime_context

logger = logging.getLogger(__name__)


class ToolObservabilityMiddleware(AgentMiddleware):
    """
    KPI timer + audit events around every tool call `create_agent`'s
    `ToolNode` executes (#2011).

    Why this exists:
    - see the module docstring for the full rationale; in short, this is the
      generic-tool-call equivalent of `TracingKpiMiddleware` (which does the
      same job for model calls) — one middleware, one chokepoint, covering
      MCP-catalog tools and capability-native tools alike

    How to use:
    - always part of the frame; KPI emission is a no-op when `kpi` is None
      (mirrors `TracingKpiMiddleware`'s own `kpi is None` handling)
    """

    def __init__(
        self,
        *,
        kpi: BaseKPIWriter | None,
        binding: BoundRuntimeContext,
    ) -> None:
        super().__init__()
        self._kpi = kpi
        self._binding = binding

    def _base_dims(self, *, tool_name: str, source: str) -> dict[str, Optional[str]]:
        """
        Identity/correlation dims shared by the KPI timer and both audit
        events for one tool call. Only identifiers — never tool arguments or
        results (mirrors `ContextAwareTool._kpi_base_dims`'s restraint).
        """
        portable = self._binding.portable_context
        dims: dict[str, Optional[str]] = {"tool_name": tool_name, "source": source}
        if portable.session_id:
            dims["session_id"] = portable.session_id
        if portable.user_id:
            dims["user_id"] = portable.user_id
        if portable.team_id:
            dims["team_id"] = portable.team_id
        agent_instance_id = portable.baggage.get("agent_instance_id")
        if agent_instance_id:
            dims["agent_instance_id"] = agent_instance_id
        template_agent_id = portable.baggage.get("template_agent_id")
        if template_agent_id:
            dims["template_agent_id"] = template_agent_id
        if portable.correlation_id:
            dims["correlation_id"] = portable.correlation_id
        if portable.trace_id:
            dims["trace_id"] = portable.trace_id
        return dims

    @staticmethod
    def _tool_name(request: ToolCallRequest) -> str:
        tool_call = request.tool_call
        name = tool_call.get("name") if isinstance(tool_call, dict) else None
        if not name:
            name = getattr(request.tool, "name", None)
        return str(name) if name else "unknown"

    @staticmethod
    async def _reverify_team_authorization(
        *, user_id: Optional[str], team_id: Optional[str], is_service_agent: bool
    ) -> None:
        """
        Per-tool-call ReBAC re-check (RUNTIME least-privilege gap, see
        docs/swift audit): `_authorize_execution_or_raise` (agent_app.py)
        verifies CAN_READ on the turn's team exactly once, at turn start.
        Every tool call after that — potentially many, in a long ReAct loop —
        ran unchecked, trusting that one decision for the rest of the turn.
        This re-runs the same OpenFGA check at the one chokepoint every tool
        call already passes through, so a stale/dropped team membership (or a
        tool call scoped to a different team than the one authorized at turn
        start) is caught here instead of silently trusted.

        Uses the low-level `check_permission_or_raise` primitive (subject/
        resource references, no `KeycloakUser`) because only the portable
        `user_id`/`team_id` strings are available at this layer — the
        personal-team self-heal and org-team bootstrap already ran once at
        turn start for this exact team_id, so skipping them here is safe.

        `is_service_agent` mirrors the *other* branch `_authorize_execution_or_raise`
        takes at turn start (RFC EVAL-AUTH, Solution A): the evaluation worker's
        service identity is authorized without any OpenFGA tuple, so re-running
        the ReBAC check here would reject an identity that was never meant to
        hold one. The flag is computed once from the trusted JWT at turn start
        and threaded through `PortableContext.baggage` — never re-derived from
        anything caller-suppliable at this layer.

        Scope: authorizes the *team* a call is scoped to, not any specific
        resource a tool argument may reference (e.g. a document_uid) — that
        remains each downstream service's own responsibility (several already
        do it, e.g. knowledge-flow-backend's per-document ReBAC checks).
        """
        try:
            rebac = get_runtime_context().config.rebac_engine
        except RuntimeError:
            # No pod-wide RuntimeContext set up (e.g. a unit test exercising
            # this middleware in isolation) — nothing to check against.
            return
        if rebac is None or not rebac.enabled:
            return  # dev/local (identity-only) or Noop engine — mirrors turn start
        if not team_id or is_personal_team_id(team_id):
            # Personal spaces aren't injected as a team_id into tool calls
            # (`ContextAwareTool._inject_context_if_needed`); nothing to recheck.
            return
        if not user_id:
            return
        if is_service_agent:
            return
        await rebac.check_permission_or_raise(
            RebacReference(Resource.USER, user_id),
            TeamPermission.CAN_READ,
            RebacReference(Resource.TEAM, team_id),
        )

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        tool_name = self._tool_name(request)
        # `ContextAwareTool` wraps every MCP-catalog tool (`mcp_toolkit.py`);
        # anything else reaching the tool node is a capability-native tool
        # (or a platform-builtin tool bound directly, e.g. filesystem tools).
        # A runtime `isinstance` check against a class from another module is
        # a little coupled, but it's the cheapest correct signal available —
        # no cleaner marker exists on `BaseTool` today.
        source = "mcp" if isinstance(request.tool, ContextAwareTool) else "capability"
        base_dims = self._base_dims(tool_name=tool_name, source=source)

        kpi = self._kpi
        timer_ctx = (
            kpi.timer(
                "agent.tool_latency_ms", dims=base_dims, actor=KPIActor(type="system")
            )
            if kpi is not None
            else nullcontext()
        )

        emit_audit_log("agent.tool.invocation.started", **base_dims)
        with timer_ctx as kpi_dims:
            try:
                await self._reverify_team_authorization(
                    user_id=base_dims.get("user_id"),
                    team_id=base_dims.get("team_id"),
                    is_service_agent=self._binding.portable_context.baggage.get(
                        "is_service_agent"
                    )
                    == "true",
                )
                result = await handler(request)
            except asyncio.CancelledError:
                # Never swallow cancellation — record it as its own terminal
                # outcome (distinct from "failed", see
                # docs/swift/platform/OBSERVABILITY-AND-AUDIT.md §5) and
                # re-raise so asyncio's cancellation semantics stay intact.
                emit_audit_log(
                    "agent.tool.invocation.completed", outcome="cancelled", **base_dims
                )
                raise
            except Exception as e:
                if kpi_dims is not None:
                    kpi_dims["status"] = "error"
                    kpi_dims["error_code"] = type(e).__name__
                    kpi_dims["exception_type"] = type(e).__name__
                if kpi is not None:
                    kpi.count(
                        "agent.tool_failed_total",
                        1,
                        dims={
                            **base_dims,
                            "status": "error",
                            "error_code": type(e).__name__,
                            "exception_type": type(e).__name__,
                        },
                        actor=KPIActor(type="system"),
                    )
                logger.exception(
                    "[TOOL][%s] Tool execution failed (captured)", tool_name
                )
                emit_audit_log(
                    "agent.tool.invocation.completed",
                    outcome="failed",
                    error_code=type(e).__name__,
                    exception_type=type(e).__name__,
                    **base_dims,
                )
                raise
            else:
                # A `Command` has no `.status` — LangGraph already ran the
                # tool and chose to redirect graph state, which is not a
                # failure signal, so it always counts as "succeeded".
                failed = isinstance(result, ToolMessage) and result.status == "error"
                if failed:
                    if kpi_dims is not None:
                        kpi_dims["status"] = "error"
                    if kpi is not None:
                        kpi.count(
                            "agent.tool_failed_total",
                            1,
                            dims={**base_dims, "status": "error"},
                            actor=KPIActor(type="system"),
                        )
                    emit_audit_log(
                        "agent.tool.invocation.completed",
                        outcome="failed",
                        **base_dims,
                    )
                else:
                    emit_audit_log(
                        "agent.tool.invocation.completed",
                        outcome="succeeded",
                        **base_dims,
                    )
                return result


__all__ = ["ToolObservabilityMiddleware"]

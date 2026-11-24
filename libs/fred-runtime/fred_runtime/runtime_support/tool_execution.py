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

"""Shared per-tool authorization, audit and KPI boundary for all agent runtimes."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import nullcontext, suppress
from typing import Optional, TypeVar

from fred_core.conversation_trace import TraceToolOutcome, TraceToolSource
from fred_core.history.history_schema import FailureOrigin, FailureReason
from fred_core.kpi import BaseKPIWriter
from fred_core.logs.audit_log import emit_audit_log
from fred_core.logs.context import operation_log_scope
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    ToolFailure,
    ToolFailureCode,
    ToolInvocationResult,
)
from fred_sdk.contracts.runtime import SpanPort
from langchain_core.messages.tool import ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.types import Command

from fred_runtime.common.outbound_credentials import delegation_enabled
from fred_runtime.execution_errors import localize
from fred_runtime.model_routing.turn import current_turn
from fred_runtime.runtime_support.authority import RunStopError
from fred_runtime.runtime_support.request_context_helpers import turn_kpi_actor
from fred_runtime.runtime_support.run_scope import RunScope
from fred_runtime.runtime_support.tool_capture import capture_tool, link_tool_span

logger = logging.getLogger(__name__)
_Result = TypeVar("_Result")
_UNEXPECTED = ToolFailure(code=ToolFailureCode.unexpected)

# What the person reads for each failure code: fixed text, never a tool's or a
# dependency's. `resource_unavailable` covers a 403 as well as a 404 or an
# identifier of the wrong kind, so it claims neither a refusal nor an absence.
_FAILURE_SENTENCES: dict[ToolFailureCode, dict[str, str]] = {
    ToolFailureCode.invalid_arguments: {
        "en": "The tool rejected the call arguments.",
        "fr": "L'outil a refusé les arguments de l'appel.",
    },
    ToolFailureCode.not_approved: {
        "en": "Call declined by the user.",
        "fr": "Appel refusé par l'utilisateur.",
    },
    ToolFailureCode.authentication_required: {
        "en": "The service refused the authentication of this call. Sign in "
        "again before retrying.",
        "fr": "Le service a refusé l'authentification de cet appel. "
        "Reconnectez-vous avant de réessayer.",
    },
    ToolFailureCode.resource_unavailable: {
        "en": "The requested document or resource could not be found or read.",
        "fr": "Le document ou la ressource demandés sont introuvables ou illisibles.",
    },
    ToolFailureCode.scope_refused: {
        "en": "This call targeted documents outside the selection of this "
        "conversation, so nothing was read.",
        "fr": "Cet appel visait des documents hors de la sélection de cette "
        "conversation : rien n'a été lu.",
    },
    ToolFailureCode.rate_limited: {
        "en": "The service is limiting the number of requests. Please try again "
        "in a moment.",
        "fr": "Le service limite le nombre de requêtes. Réessayez dans un instant.",
    },
    ToolFailureCode.misconfigured: {
        "en": "A dependency refused the platform configuration. This is a "
        "configuration problem, not a problem with your request: an "
        "administrator must correct it.",
        "fr": "Une dépendance a refusé la configuration de la plateforme. C'est "
        "un problème de configuration, pas de votre demande : un administrateur "
        "doit le corriger.",
    },
    ToolFailureCode.service_busy: {
        "en": "The service is temporarily unavailable or at capacity. Try again later.",
        "fr": "Le service est temporairement indisponible ou saturé. Réessayez "
        "plus tard.",
    },
    ToolFailureCode.timeout: {
        "en": "The operation exceeded its time budget. Narrow the request before "
        "retrying.",
        "fr": "L'opération a dépassé son délai maximal. Réduisez la demande avant "
        "de réessayer.",
    },
    ToolFailureCode.service_error: {
        "en": "The service could not complete this operation. Try again later; "
        "contact support if the problem persists.",
        "fr": "Le service n'a pas pu terminer cette opération. Réessayez plus "
        "tard ; contactez le support si le problème persiste.",
    },
    ToolFailureCode.unexpected: {
        "en": "This step failed unexpectedly. Try again; contact support if the "
        "problem persists.",
        "fr": "Cette étape a échoué de façon inattendue. Réessayez ; contactez le "
        "support si le problème persiste.",
    },
}
# A failure Knowledge Flow reports names the dependency to look at; these are
# the codes `ToolFailure.platform_explanation` tells the model about.
_PLATFORM_SENTENCES: dict[ToolFailureCode, dict[str, str]] = {
    ToolFailureCode.misconfigured: {
        "en": "{origin} refused the credentials of Knowledge Flow. This is a "
        "platform configuration problem, not a problem with your request: an "
        "administrator must correct the Knowledge Flow configuration.",
        "fr": "{origin} a refusé les identifiants de Knowledge Flow. C'est un "
        "problème de configuration de la plateforme, pas de votre demande : un "
        "administrateur doit corriger la configuration de Knowledge Flow.",
    },
    ToolFailureCode.service_busy: {
        "en": "{origin} is unreachable. This is a platform availability problem, "
        "not a problem with your request: try again later; if it persists, an "
        "administrator must check this service.",
        "fr": "{origin} est injoignable. C'est un problème de disponibilité de la "
        "plateforme, pas de votre demande : réessayez plus tard ; si le problème "
        "persiste, un administrateur doit vérifier ce service.",
    },
}
_ORIGINS: dict[FailureOrigin, dict[str, str]] = {
    FailureOrigin.knowledge_flow: {"en": "Knowledge Flow", "fr": "Knowledge Flow"},
    FailureOrigin.object_storage: {
        "en": "The document storage",
        "fr": "Le stockage de documents",
    },
    FailureOrigin.search_index: {
        "en": "The search index",
        "fr": "L'index de recherche",
    },
    FailureOrigin.database: {"en": "The database", "fr": "La base de données"},
}
# A reason names what the tool refused more precisely than its code.
_REASON_SENTENCES: dict[FailureReason, dict[str, str]] = {
    FailureReason.not_a_document_uid: {
        "en": "The agent gave a file name or another invalid value instead of a "
        "document identifier.",
        "fr": "L'agent a fourni un nom de fichier ou une autre valeur invalide au "
        "lieu d'un identifiant de document.",
    },
}
# Stamped on capability tools at assembly; tags tool KPIs with their capability.
CAPABILITY_ID_METADATA_KEY = "fred.capability_id"
TOOL_FAILURE_MARKER = "_fred_observed_tool_failure"


def _traced_result(result: object, call_id: str | None) -> object:
    # Some Deep tools return a graph update carrying their model-visible message.
    if isinstance(result, Command) and isinstance(result.update, dict):
        messages = result.update.get("messages")
        if isinstance(messages, (list, tuple)):
            return next(
                (
                    message
                    for message in messages
                    if isinstance(message, ToolMessage)
                    and message.tool_call_id == call_id
                ),
                result,
            )
    return result


def describe_failure(failure: ToolFailure, language: str | None) -> ToolFailure:
    """Write the person's sentence for one tool failure, in their language.

    Called once, where a tool result leaves the turn: the live event and the
    stored history then carry the same sentence, and any `message` a tool or a
    dependency set is replaced.
    """

    platform = _PLATFORM_SENTENCES.get(failure.code)
    if failure.origin is not None and platform is not None:
        origin = localize(_ORIGINS[failure.origin], language)
        message = localize(platform, language).format(origin=origin)
    elif failure.reason is not None:
        message = localize(_REASON_SENTENCES[failure.reason], language)
    else:
        message = localize(_FAILURE_SENTENCES[failure.code], language)
    return failure.model_copy(update={"message": message})


def result_failure(result: object) -> ToolFailure | None:
    """The failure one tool call reported, or ``None`` when it succeeded.

    A typed artifact's ``failure`` wins. A LangChain ``ToolMessage`` with
    ``status="error"`` and no typed failure carries no downstream status.
    """
    artifact = (
        result
        if isinstance(result, ToolInvocationResult)
        else getattr(result, "artifact", None)
    )
    if isinstance(artifact, ToolInvocationResult) and artifact.failure is not None:
        return artifact.failure
    if isinstance(artifact, dict) and artifact.get("failure"):
        return ToolFailure.model_validate(artifact["failure"])
    if isinstance(result, ToolMessage) and result.status == "error":
        return _UNEXPECTED
    return None


def capability_id_of(tool: object) -> str | None:
    metadata = getattr(tool, "metadata", None)
    value = (
        metadata.get(CAPABILITY_ID_METADATA_KEY) if isinstance(metadata, dict) else None
    )
    return value if isinstance(value, str) and value else None


class ToolExecution:
    """Run one authorized call without changing its return value or exceptions."""

    def __init__(
        self, *, kpi: BaseKPIWriter | None, binding: BoundRuntimeContext
    ) -> None:
        self._kpi = kpi
        self._binding = binding

    def _base_dims(self, *, tool_name: str, source: str) -> dict[str, Optional[str]]:
        portable = self._binding.portable_context
        dims: dict[str, Optional[str]] = {"tool_name": tool_name, "source": source}
        if portable.session_id:
            dims["session_id"] = portable.session_id
        if portable.user_id:
            dims["user_id"] = portable.user_id
        if portable.space_id:
            dims["space_id"] = portable.space_id
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

    async def run(
        self,
        invoke: Callable[[], Awaitable[_Result]],
        *,
        tool_name: str,
        source: str,
        span: SpanPort | None = None,
        capability_id: str | None = None,
        call_id: str | None = None,
        arguments: object = None,
    ) -> _Result:
        started = time.perf_counter()
        outcome = "failed"
        failure: ToolFailure | None = None
        with operation_log_scope(tool_name=tool_name):
            try:
                result = await self._run(
                    invoke,
                    tool_name=tool_name,
                    source=source,
                    span=span,
                    capability_id=capability_id,
                    call_id=call_id,
                    arguments=arguments,
                )
                failure = result_failure(result)
                outcome = "failed" if failure is not None else "succeeded"
                return result
            except GraphBubbleUp:
                outcome = "awaiting_human"
                raise
            except asyncio.CancelledError:
                outcome = "cancelled"
                raise
            finally:
                duration_ms = (time.perf_counter() - started) * 1000
                if failure is not None:
                    # Operations need the cause, never the content, arguments
                    # or downstream body; `tool_name` comes from the log scope.
                    logger.warning(
                        "Tool invocation failed",
                        extra={
                            "outcome": outcome,
                            "failure_code": failure.code.value,
                            "failure_status": failure.status,
                            "failure_origin": failure.origin.value
                            if failure.origin
                            else None,
                            "failure_setting": failure.setting,
                            "duration_ms": duration_ms,
                        },
                    )
                else:
                    logger.info(
                        "Tool invocation completed",
                        extra={"outcome": outcome, "duration_ms": duration_ms},
                    )

    async def _run(
        self,
        invoke: Callable[[], Awaitable[_Result]],
        *,
        tool_name: str,
        source: str,
        span: SpanPort | None = None,
        capability_id: str | None = None,
        call_id: str | None = None,
        arguments: object = None,
    ) -> _Result:
        base_dims = self._base_dims(tool_name=tool_name, source=source)
        # Keep latency labels stable; failure taxonomy belongs on the counter.
        kpi = self._kpi
        timer_ctx = (
            kpi.timer(
                "agent.tool_latency_ms",
                dims=base_dims,
                actor=turn_kpi_actor(self._binding),
            )
            if kpi is not None
            else nullcontext()
        )

        run_scope = RunScope.current()
        if run_scope is not None:
            run_scope.raise_if_stopped()

        confined = delegation_enabled()
        if confined:
            emit_audit_log(
                "agent.tool.invocation.started",
                outcome="started",
                reason="tool_invocation",
            )
        else:
            emit_audit_log("agent.tool.invocation.started", **base_dims)
        with timer_ctx as kpi_dims:
            try:
                # M4 resolves authority once per turn; tool calls enforce it locally.
                authority = current_turn()
                template_id = self._binding.portable_context.agent_id or ""
                authority.check_context(self._binding.portable_context, template_id)
                authority.check_context(self._binding.runtime_context, template_id)
                trace_source = (
                    TraceToolSource.MCP if source == "mcp" else TraceToolSource.NATIVE
                )
                async with capture_tool(
                    tool_name, call_id, trace_source, arguments
                ) as tool:
                    if tool is None:
                        result = await invoke()
                    else:
                        link_tool_span(span, tool)
                        try:
                            result = await invoke()
                        except GraphBubbleUp:
                            await tool.finish(TraceToolOutcome.PAUSED)
                            raise
                        except asyncio.CancelledError:
                            await tool.finish(TraceToolOutcome.CANCELLED)
                            raise
                        except Exception as exc:
                            await tool.finish(
                                TraceToolOutcome.ERROR,
                                {"exception": type(exc).__name__},
                            )
                            raise
                        else:
                            tool_result = _traced_result(result, call_id)
                            outcome = (
                                TraceToolOutcome.ERROR
                                if result_failure(result) is not None
                                else TraceToolOutcome.SUCCESS
                            )
                            await tool.finish(outcome, tool_result)
            except GraphBubbleUp:
                if kpi_dims is not None:
                    kpi_dims["status"] = "awaiting_human"
                raise
            except asyncio.CancelledError:
                if confined:
                    emit_audit_log(
                        "agent.tool.invocation.completed",
                        outcome="cancelled",
                        reason="cancelled",
                    )
                else:
                    emit_audit_log(
                        "agent.tool.invocation.completed",
                        outcome="cancelled",
                        **base_dims,
                    )
                raise
            except Exception as e:
                if not isinstance(e, RunStopError):
                    with suppress(Exception):
                        setattr(e, TOOL_FAILURE_MARKER, True)
                if kpi_dims is not None:
                    kpi_dims["status"] = "error"
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
                        actor=turn_kpi_actor(self._binding),
                    )
                reason = e.reason if isinstance(e, RunStopError) else type(e).__name__
                if isinstance(e, RunStopError):
                    logger.warning("event=tool_call outcome=stopped reason=%s", reason)
                elif confined:
                    logger.error("event=tool_call outcome=failed reason=%s", reason)
                else:
                    logger.exception("[%s] Tool execution failed (captured)", tool_name)
                if confined:
                    emit_audit_log(
                        "agent.tool.invocation.completed",
                        outcome="failed",
                        reason=reason,
                    )
                else:
                    emit_audit_log(
                        "agent.tool.invocation.completed",
                        outcome="failed",
                        error_code=type(e).__name__,
                        exception_type=type(e).__name__,
                        **base_dims,
                    )
                raise
            else:
                failure = result_failure(result)
                if failure is not None:
                    error_code = failure.code.value
                    if span is not None:
                        span.set_attribute("status", "error")
                        span.set_attribute("error_type", error_code)
                    if kpi_dims is not None:
                        kpi_dims["status"] = "error"
                    if kpi is not None:
                        kpi.count(
                            "agent.tool_failed_total",
                            1,
                            dims={
                                **base_dims,
                                "status": "error",
                                "error_code": error_code,
                                "exception_type": "none",
                            },
                            actor=turn_kpi_actor(self._binding),
                        )
                    if confined:
                        emit_audit_log(
                            "agent.tool.invocation.completed",
                            outcome="failed",
                            reason=error_code,
                        )
                    else:
                        emit_audit_log(
                            "agent.tool.invocation.completed",
                            outcome="failed",
                            error_code=error_code,
                            exception_type="none",
                            **base_dims,
                        )
                else:
                    if confined:
                        emit_audit_log(
                            "agent.tool.invocation.completed",
                            outcome="succeeded",
                            reason="tool_completed",
                        )
                    else:
                        emit_audit_log(
                            "agent.tool.invocation.completed",
                            outcome="succeeded",
                            **base_dims,
                        )
                return result

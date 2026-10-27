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
from contextlib import nullcontext
from typing import Optional, TypeVar

from fred_core.kpi import BaseKPIWriter, KPIActor
from fred_core.logs.audit_log import emit_audit_log
from fred_core.logs.context import operation_log_scope
from fred_sdk.contracts.context import BoundRuntimeContext, ToolInvocationResult
from fred_sdk.contracts.runtime import SpanPort
from langchain_core.messages.tool import ToolMessage
from langgraph.errors import GraphBubbleUp

from fred_runtime.common.outbound_credentials import delegation_enabled
from fred_runtime.model_routing.turn import current_turn
from fred_runtime.runtime_support.authority import RunStopError
from fred_runtime.runtime_support.run_scope import RunScope

logger = logging.getLogger(__name__)
_Result = TypeVar("_Result")


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
    ) -> _Result:
        started = time.perf_counter()
        outcome = "failed"
        with operation_log_scope(tool_name=tool_name):
            try:
                result = await self._run(
                    invoke, tool_name=tool_name, source=source, span=span
                )
                outcome = "failed" if self._result_is_error(result)[0] else "succeeded"
                return result
            except GraphBubbleUp:
                outcome = "awaiting_human"
                raise
            except asyncio.CancelledError:
                outcome = "cancelled"
                raise
            finally:
                logger.info(
                    "Tool invocation completed",
                    extra={
                        "outcome": outcome,
                        "duration_ms": (time.perf_counter() - started) * 1000,
                    },
                )

    @staticmethod
    def _result_is_error(result: object) -> tuple[bool, str]:
        artifact = (
            result
            if isinstance(result, ToolInvocationResult)
            else getattr(result, "artifact", None)
        )
        artifact_is_error = (
            bool(artifact.get("is_error"))
            if isinstance(artifact, dict)
            else bool(getattr(artifact, "is_error", False))
        )
        status_is_error = isinstance(result, ToolMessage) and result.status == "error"
        return (
            status_is_error or artifact_is_error,
            "tool_error_status" if status_is_error else "tool_error_artifact",
        )

    async def _run(
        self,
        invoke: Callable[[], Awaitable[_Result]],
        *,
        tool_name: str,
        source: str,
        span: SpanPort | None = None,
    ) -> _Result:
        base_dims = self._base_dims(tool_name=tool_name, source=source)
        # Keep latency labels stable; failure taxonomy belongs on the counter.
        kpi = self._kpi
        timer_ctx = (
            kpi.timer(
                "agent.tool_latency_ms", dims=base_dims, actor=KPIActor(type="system")
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
                result = await invoke()
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
                        actor=KPIActor(type="system"),
                    )
                reason = e.reason if isinstance(e, RunStopError) else type(e).__name__
                if isinstance(e, RunStopError):
                    logger.warning(
                        "[TOOL] event=tool_call outcome=stopped reason=%s", reason
                    )
                elif confined:
                    logger.error(
                        "[TOOL] event=tool_call outcome=failed reason=%s", reason
                    )
                else:
                    logger.exception(
                        "[TOOL][%s] Tool execution failed (captured)", tool_name
                    )
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
                failed, error_code = self._result_is_error(result)
                if failed:
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
                            actor=KPIActor(type="system"),
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

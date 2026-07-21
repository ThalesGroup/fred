# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

import asyncio
import logging
from typing import Any, Callable, Optional

import httpx  # ← we log/inspect HTTP errors coming from MCP adapters
from fred_core.common import OwnerFilter
from fred_core.common.team_id import is_personal_team_id
from fred_sdk.support.mcp_utils import normalize_mcp_content
from langchain_core.tools import BaseTool
from pydantic import Field

from fred_runtime.common.structures import AgentSettingsLike
from fred_runtime.common.token_expiry import (
    is_expired_httpx_status_error,
    unwrap_httpx_status_error,
)
from fred_runtime.runtime_support import (
    RuntimeContextProvider,
    get_document_library_tags_ids,
    get_document_uids,
    get_vector_search_scopes,
)

AgentSettingsProvider = Callable[[], AgentSettingsLike]

logger = logging.getLogger(__name__)


def _unwrap_httpx_status_error(exc: BaseException) -> Optional[httpx.HTTPStatusError]:
    # Backward compatibility for existing callers
    return unwrap_httpx_status_error(exc)


def _build_tool_error_message(
    exc: BaseException, inner: Optional[httpx.HTTPStatusError]
) -> str:
    """Return a user-facing error string that surfaces upstream HTTP detail when available.

    FastAPI services return ``{"detail": "..."}`` on errors; we extract that field so
    the agent (and ultimately the user) sees the root cause rather than the HTTP status
    line.  Falls back to ``str(exc)`` when no HTTP response is present.
    """
    if inner is None:
        return f"Error: {exc}"
    code = inner.response.status_code if inner.response else "?"
    detail: str = str(inner)
    try:
        if inner.response:
            raw = inner.response.text
            try:
                body = inner.response.json()
                if isinstance(body, dict) and "detail" in body:
                    detail = str(body["detail"])
                else:
                    detail = raw[:300] if raw else str(inner)
            except Exception:
                detail = raw[:300] if raw else str(inner)
    except httpx.ResponseNotRead:
        logger.debug(
            "HTTP response body not read (streamed response); using default error message"
        )
    except Exception:
        logger.warning(
            "Failed to extract HTTP response body for error message", exc_info=True
        )
    return f"Error: HTTP {code}: {detail}"


def _log_http_error(tool_name: str, err: httpx.HTTPStatusError) -> None:
    """
    Fred rationale:
    Give ops-grade traces that directly point to auth/token problems, with enough
    context (method, URL, body snippet) to debug quickly.
    """
    req = getattr(err, "request", None)
    resp = getattr(err, "response", None)

    method = getattr(req, "method", "?")
    url = str(getattr(req, "url", "?"))
    code = getattr(resp, "status_code", None)

    body_preview = ""
    try:
        if resp is not None:
            txt = resp.text
            # keep logs short; we only need a hint
            body_preview = f" | body: {txt[:300].replace(chr(10), ' ')}"
    except httpx.ResponseNotRead:
        logger.debug(
            "HTTP response body not read (streamed response); skipping body preview"
        )
    except Exception:
        logger.warning("Failed to extract HTTP response body", exc_info=True)

    if code == 401:
        expired_flag = " (expired token)" if is_expired_httpx_status_error(err) else ""
        logger.error(
            "[MCP][%s] 401 Unauthorized%s (likely expired/invalid token) on %s %s%s",
            tool_name,
            expired_flag,
            method,
            url,
            body_preview,
            exc_info=True,
        )
    else:
        logger.error(
            "[MCP][%s] HTTP %s on %s %s%s",
            tool_name,
            code,
            method,
            url,
            body_preview,
            exc_info=True,
        )


class ContextAwareTool(BaseTool):
    """
    Developer intent (Fred):
    - This wrapper injects **runtime context** (e.g., doc library tags) into MCP tools.
    - It also **traces auth failures** cleanly: if the MCP call returns 401, we log
      an explicit message so ops/devs see token expiry immediately.

    Why here?
    - Tool execution happens inside LangGraph's ToolNode; catching here guarantees we
      see the *real* tool failure (including wrapped httpx errors) without changing
      your graph or agent code.
    """

    base_tool: BaseTool = Field(..., description="The underlying tool to wrap")
    context_provider: RuntimeContextProvider = Field(
        ..., description="Function that provides runtime context"
    )
    agent_settings_provider: AgentSettingsProvider = Field(
        ..., description="Function that provides agent settings"
    )

    def __init__(
        self,
        base_tool: BaseTool,
        context_provider: RuntimeContextProvider,
        agent_settings_provider: AgentSettingsProvider,
    ):
        # Preserve tool identity (name/description) so LLM can pick it properly.
        super().__init__(
            **base_tool.__dict__,
            base_tool=base_tool,
            context_provider=context_provider,
            agent_settings_provider=agent_settings_provider,
        )

    def _inject_context_if_needed(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """
        Fred rationale:
        Keep injection conservative + schema-aware. For now we only add "tags" if the
        tool supports it and caller didn't pass it.
        """
        context = self.context_provider()
        settings = self.agent_settings_provider()
        if not context:
            return kwargs

        tool_properties = self._get_tool_properties()

        # Snapshot what the agent (or LLM) explicitly requested, so every decision
        # below can be logged as "requested -> applied" with no ambiguity. The
        # picker selection (RuntimeContext) is a default scope an agent may NARROW;
        # an explicit per-call scope is respected, never silently overwritten.
        caller_document_uids = kwargs.get("document_uids")
        caller_library_ids = kwargs.get("document_library_tags_ids")
        picker_document_uids = get_document_uids(context)
        picker_library_ids = get_document_library_tags_ids(context)

        # Document scope is the most specific selector. If the agent passed it,
        # keep it verbatim; otherwise fill from the picker selection.
        if "document_uids" in tool_properties:
            if caller_document_uids:
                logger.info(
                    "ContextAwareTool(%s) document_uids: agent-scoped=%s (picker=%s NOT applied)",
                    self.name,
                    caller_document_uids,
                    picker_document_uids,
                )
            elif picker_document_uids:
                kwargs["document_uids"] = picker_document_uids
                logger.info(
                    "ContextAwareTool(%s) document_uids: applied picker selection=%s",
                    self.name,
                    picker_document_uids,
                )

        # Library scope is broader than document scope. Inject the picker libraries
        # only when the agent did not scope by library AND did not scope by document
        # (a per-call document scope must not be widened back to whole libraries).
        if "document_library_tags_ids" in tool_properties:
            if caller_library_ids:
                logger.info(
                    "ContextAwareTool(%s) library: agent-scoped=%s (picker=%s NOT applied)",
                    self.name,
                    caller_library_ids,
                    picker_library_ids,
                )
            elif caller_document_uids:
                logger.info(
                    "ContextAwareTool(%s) library: NOT injected — agent scoped by document_uids=%s",
                    self.name,
                    caller_document_uids,
                )
            elif picker_library_ids:
                kwargs["document_library_tags_ids"] = picker_library_ids
                logger.info(
                    "ContextAwareTool(%s) library: applied picker selection=%s",
                    self.name,
                    picker_library_ids,
                )

        session_id = context.session_id
        if (
            session_id
            and "session_id" in tool_properties
            and not kwargs.get("session_id")
        ):
            kwargs["session_id"] = session_id
            logger.info(
                "ContextAwareTool(%s) injecting session_id: %s",
                self.name,
                session_id,
            )

        # Force team_id depending on agent settings.
        # Personal-space IDs ("personal-<uuid>") are not real ReBAC teams;
        # don't forward them to tools that look up team membership.
        effective_team_id = (
            settings.team_id if not is_personal_team_id(settings.team_id) else None
        )
        if "team_id" in tool_properties and effective_team_id:
            kwargs["team_id"] = effective_team_id
            logger.info(
                "ContextAwareTool(%s) injecting team_id: %s",
                self.name,
                effective_team_id,
            )

        # Force owner_filter depending on agent settings
        if "owner_filter" in tool_properties:
            owner_filter = (
                OwnerFilter.TEAM if effective_team_id else OwnerFilter.PERSONAL
            )
            kwargs["owner_filter"] = owner_filter.value
            logger.info(
                "ContextAwareTool(%s) injecting owner_filter: %s",
                self.name,
                owner_filter.value,
            )

        include_session_scope, include_corpus_scope = get_vector_search_scopes(context)
        if (
            "include_session_scope" in tool_properties
            and "include_session_scope" not in kwargs
        ):
            kwargs["include_session_scope"] = include_session_scope
            logger.info(
                "ContextAwareTool(%s) injecting include_session_scope=%s",
                self.name,
                include_session_scope,
            )
        if (
            "include_corpus_scope" in tool_properties
            and "include_corpus_scope" not in kwargs
        ):
            kwargs["include_corpus_scope"] = include_corpus_scope
            logger.info(
                "ContextAwareTool(%s) injecting include_corpus_scope=%s",
                self.name,
                include_corpus_scope,
            )

        return kwargs

    def _get_tool_properties(self) -> dict[str, Any]:
        """
        Best-effort extraction of tool input schema properties.
        """
        tool_properties: dict[str, Any] = {}
        if not self.base_tool.args_schema:
            return tool_properties

        try:
            # Pydantic v2 first, v1 fallback, else assume dict-like
            schema_method = getattr(
                self.base_tool.args_schema, "model_json_schema", None
            )
            if schema_method:
                tool_schema = schema_method()
            else:
                schema_method = getattr(self.base_tool.args_schema, "schema", None)
                tool_schema = (
                    schema_method() if schema_method else self.base_tool.args_schema
                )

            if isinstance(tool_schema, dict):
                props = tool_schema.get("properties", {})
                if isinstance(props, dict):
                    tool_properties = props
        except Exception as e:
            logger.warning(
                "ContextAwareTool(%s): could not extract tool schema: %s",
                self.name,
                e,
            )

        return tool_properties

    def _sanitize_tool_kwargs(self, kwargs: Optional[dict[str, Any]]) -> dict[str, Any]:
        """Ensure mapping input and drop explicit null values."""
        return {k: v for k, v in (kwargs or {}).items() if v is not None}

    def _run(self, **kwargs: Any) -> Any:
        """Sync execution with context injection + robust HTTP(401) tracing.

        KPI timing (`agent.tool_latency_ms`) and the
        `agent.tool.invocation.{started,completed}` audit events used to be
        emitted from here directly; they now come from the platform-wide
        `ToolObservabilityMiddleware` (`react/middleware/tool_observability.py`,
        #2011), which wraps every tool call — MCP-catalog tools AND
        capability-native tools alike — through `awrap_tool_call`. Emitting
        them here too would double-count every MCP tool call.
        """
        kwargs = self._inject_context_if_needed(kwargs)
        kwargs = self._sanitize_tool_kwargs(kwargs)
        try:
            result = self.base_tool._run(**kwargs)
        except Exception as e:
            # Check for HTTP status in the exception chain for better logs
            inner = _unwrap_httpx_status_error(e)

            if inner:
                _log_http_error(self.name, inner)
            else:
                logger.exception(
                    "[MCP][%s] Tool execution failed (captured)", self.name
                )

            # CRITICAL: Return error as text to preserve chat history integrity.
            # This ensures every ToolCall gets a ToolResult, preventing "orphan" calls.
            msg = _build_tool_error_message(e, inner)
            if getattr(self, "response_format", None) == "content_and_artifact":
                return msg, None
            return msg
        else:
            return normalize_mcp_content(result)

    async def _arun(self, config=None, **kwargs: Any) -> Any:
        """Async execution with context injection + robust HTTP(401) tracing.

        See `_run`'s docstring: KPI/audit emission moved to
        `ToolObservabilityMiddleware` (#2011).
        """
        kwargs = self._inject_context_if_needed(kwargs)
        kwargs = self._sanitize_tool_kwargs(kwargs)
        try:
            result = await self.base_tool._arun(config=config, **kwargs)
        except asyncio.CancelledError:
            # Never swallow cancellation — re-raise so asyncio's cancellation
            # semantics stay intact. `ToolObservabilityMiddleware` records the
            # "cancelled" outcome around the whole call, including this one.
            raise
        except Exception as e:
            # Check for HTTP status in the exception chain for better logs
            inner = _unwrap_httpx_status_error(e)

            if inner:
                _log_http_error(self.name, inner)
            else:
                logger.exception(
                    "[MCP][%s] Tool execution failed (captured)", self.name
                )

            # CRITICAL: Return error as text to preserve chat history integrity.
            msg = _build_tool_error_message(e, inner)
            if getattr(self, "response_format", None) == "content_and_artifact":
                return msg, None
            return msg
        else:
            return normalize_mcp_content(result)

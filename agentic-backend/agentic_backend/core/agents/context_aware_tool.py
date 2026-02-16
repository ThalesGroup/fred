# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

import logging
from typing import Any, Optional

import httpx  # ← we log/inspect HTTP errors coming from MCP adapters
from fred_core.kpi import KPIActor
from langchain_core.tools import BaseTool
from pydantic import Field

from agentic_backend.application_context import get_app_context
from agentic_backend.common.token_expiry import (
    is_expired_httpx_status_error,
    unwrap_httpx_status_error,
)
from agentic_backend.common.tool_node_utils import normalize_mcp_content
from agentic_backend.core.agents.runtime_context import (
    RuntimeContextProvider,
    get_document_library_tags_ids,
    get_vector_search_scopes,
)

logger = logging.getLogger(__name__)


def _unwrap_httpx_status_error(exc: BaseException) -> Optional[httpx.HTTPStatusError]:
    # Backward compatibility for existing callers
    return unwrap_httpx_status_error(exc)


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
        pass
    except Exception:
        logger.warning("Failed to extract HTTP response body", exc_info=True)
        pass

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

    def __init__(self, base_tool: BaseTool, context_provider: RuntimeContextProvider):
        # Preserve tool identity (name/description) so LLM can pick it properly.
        super().__init__(
            **base_tool.__dict__,
            base_tool=base_tool,
            context_provider=context_provider,
        )

    def _inject_context_if_needed(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """
        Fred rationale:
        Keep injection conservative + schema-aware. For now we only add "tags" if the
        tool supports it and caller didn't pass it.
        """
        context = self.context_provider()
        if not context:
            return kwargs

        tool_properties = {}
        if self.base_tool.args_schema:
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
                    tool_properties = tool_schema.get("properties", {})
            except Exception as e:
                logger.warning(
                    "ContextAwareTool(%s): could not extract tool schema: %s",
                    self.name,
                    e,
                )
                tool_properties = {}

        library_ids = get_document_library_tags_ids(context)
        if library_ids and "document_library_tags_ids" in tool_properties:
            kwargs["document_library_tags_ids"] = library_ids
            logger.info(
                "ContextAwareTool(%s) injecting library filter: %s",
                self.name,
                library_ids,
            )

        session_id = getattr(context, "session_id", None)
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

    def _kpi_base_dims(self, *, context) -> dict[str, Optional[str]]:
        dims: dict[str, Optional[str]] = {"tool_name": self.name, "source": "mcp"}
        session_id = getattr(context, "session_id", None) if context else None
        if session_id:
            dims["session_id"] = str(session_id)
        user_id = getattr(context, "user_id", None) if context else None
        if user_id:
            dims["user_id"] = str(user_id)
        return dims

    def _kpi_timer(
        self, *, context
    ) -> tuple[Any, Any, dict[str, Optional[str]], list[str] | None]:
        kpi = get_app_context().get_kpi_writer()
        dims = self._kpi_base_dims(context=context)
        groups = getattr(context, "user_groups", None) if context else None
        timer = kpi.timer(
            "agent.tool_latency_ms",
            dims=dims,
            actor=KPIActor(type="system", groups=groups),
        )
        return kpi, timer, dims, groups

    def _run(self, **kwargs: Any) -> Any:
        """Sync execution with context injection + robust HTTP(401) tracing."""
        context = self.context_provider()
        kwargs = self._inject_context_if_needed(kwargs)
        kpi, timer, base_dims, groups = self._kpi_timer(context=context)
        with timer as kpi_dims:
            try:
                result = self.base_tool._run(**kwargs)
                return normalize_mcp_content(result)
            except Exception as e:
                # 1. Metrics & Logging
                kpi_dims["error_code"] = type(e).__name__
                kpi_dims["exception_type"] = type(e).__name__

                # Check for HTTP status in the exception chain for better logs
                inner = _unwrap_httpx_status_error(e)
                status_code = (
                    inner.response.status_code if inner and inner.response else None
                )

                if status_code:
                    kpi_dims["http_status"] = str(status_code)

                kpi.count(
                    "agent.tool_failed_total",
                    1,
                    dims={
                        **base_dims,
                        "status": "error",
                        "error_code": type(e).__name__,
                        "exception_type": type(e).__name__,
                        "http_status": str(status_code) if status_code else None,
                    },
                    actor=KPIActor(type="system", groups=groups),
                )

                # 2. Logging
                if inner:
                    _log_http_error(self.name, inner)
                else:
                    logger.exception(
                        "[MCP][%s] Tool execution failed (captured)", self.name
                    )

                # 3. CRITICAL: Return error as text to preserve chat history integrity.
                # This ensures every ToolCall gets a ToolResult, preventing "orphan" calls.
                msg = f"Error: {str(e)}"
                if getattr(self, "response_format", None) == "content_and_artifact":
                    return msg, None
                return msg

    async def _arun(self, config=None, **kwargs: Any) -> Any:
        """Async execution with context injection + robust HTTP(401) tracing."""
        context = self.context_provider()
        kwargs = self._inject_context_if_needed(kwargs)
        kpi, timer, base_dims, groups = self._kpi_timer(context=context)
        with timer as kpi_dims:
            try:
                result = await self.base_tool._arun(config=config, **kwargs)
                return normalize_mcp_content(result)
            except Exception as e:
                # 1. Metrics & Logging
                kpi_dims["error_code"] = type(e).__name__
                kpi_dims["exception_type"] = type(e).__name__

                # Check for HTTP status in the exception chain for better logs
                inner = _unwrap_httpx_status_error(e)
                status_code = (
                    inner.response.status_code if inner and inner.response else None
                )

                if status_code:
                    kpi_dims["http_status"] = str(status_code)

                kpi.count(
                    "agent.tool_failed_total",
                    1,
                    dims={
                        **base_dims,
                        "status": "error",
                        "error_code": type(e).__name__,
                        "exception_type": type(e).__name__,
                        "http_status": str(status_code) if status_code else None,
                    },
                    actor=KPIActor(type="system", groups=groups),
                )

                # 2. Logging
                if inner:
                    _log_http_error(self.name, inner)
                else:
                    logger.exception(
                        "[MCP][%s] Tool execution failed (captured)", self.name
                    )

                # 3. CRITICAL: Return error as text to preserve chat history integrity.
                msg = f"Error: {str(e)}"
                if getattr(self, "response_format", None) == "content_and_artifact":
                    return msg, None
                return msg

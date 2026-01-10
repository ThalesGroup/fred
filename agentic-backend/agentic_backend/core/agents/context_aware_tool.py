# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

import logging
from typing import Any, Optional

import httpx  # ← we log/inspect HTTP errors coming from MCP adapters
from fred_core import KPIActor
from langchain_core.tools import BaseTool
from pydantic import Field

from agentic_backend.application_context import get_app_context
from agentic_backend.core.agents.runtime_context import (
    RuntimeContextProvider,
    get_document_library_tags_ids,
)

logger = logging.getLogger(__name__)


def _unwrap_httpx_status_error(exc: BaseException) -> Optional[httpx.HTTPStatusError]:
    """
    Fred rationale:
    MCP adapters sometimes re-wrap httpx exceptions. We walk the cause/context chain
    to find the underlying HTTPStatusError so we can extract status code & URL.
    """
    seen: set[int] = set()
    cur: Optional[BaseException] = exc  # type: ignore[assignment]
    while cur and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, httpx.HTTPStatusError):
            return cur
        cur = (
            getattr(cur, "__cause__", None)  # exception chaining
            or getattr(cur, "__context__", None)
        )
    return None


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
        if resp is not None and resp.text:
            txt = resp.text
            # keep logs short; we only need a hint
            body_preview = f" | body: {txt[:300].replace(chr(10), ' ')}"
    except Exception:
        logger.warning("Failed to extract HTTP response body", exc_info=True)
        pass

    if code == 401:
        logger.error(
            "[MCP][%s] 401 Unauthorized (likely expired/invalid token) on %s %s%s",
            tool_name,
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
        if (
            library_ids
            and "tags" in tool_properties
            and ("tags" not in kwargs or kwargs["tags"] is None)
        ):
            kwargs["tags"] = library_ids
            logger.info(
                "ContextAwareTool(%s) injecting library filter: %s",
                self.name,
                library_ids,
            )

        return kwargs

    def _kpi_timer(self, *, context) -> Any:
        kpi = get_app_context().get_kpi_writer()
        dims: dict[str, Optional[str]] = {"tool_name": self.name, "source": "mcp"}
        session_id = getattr(context, "session_id", None) if context else None
        if session_id:
            dims["session_id"] = str(session_id)
        user_id = getattr(context, "user_id", None) if context else None
        if user_id:
            dims["user_id"] = str(user_id)
        return kpi.timer(
            "agent.tool_latency_ms",
            dims=dims,
            actor=KPIActor(type="system"),
        )

    def _run(self, **kwargs: Any) -> Any:
        """Sync execution with context injection + robust HTTP(401) tracing."""
        context = self.context_provider()
        kwargs = self._inject_context_if_needed(kwargs)
        try:
            with self._kpi_timer(context=context):
                return self.base_tool._run(**kwargs)
        except httpx.RequestError as e:
            # Network / DNS / TLS issues before we even get an HTTP status code
            logger.error(
                "[MCP][%s] HTTP request error: %s", self.name, e, exc_info=True
            )
            raise
        except httpx.HTTPStatusError as e:
            _log_http_error(self.name, e)
            raise
        except Exception as e:
            # Catch wrapped httpx errors (common in adapters)
            inner = _unwrap_httpx_status_error(e)
            if inner is not None:
                _log_http_error(self.name, inner)
            else:
                logger.exception("[MCP][%s] Tool error", self.name)
            raise

    async def _arun(self, config=None, **kwargs: Any) -> Any:
        """Async execution with context injection + robust HTTP(401) tracing."""
        context = self.context_provider()
        kwargs = self._inject_context_if_needed(kwargs)
        try:
            with self._kpi_timer(context=context):
                return await self.base_tool._arun(config=config, **kwargs)
        except httpx.RequestError as e:
            logger.error(
                "[MCP][%s] HTTP request error: %s", self.name, e, exc_info=True
            )
            raise
        except httpx.HTTPStatusError as e:
            _log_http_error(self.name, e)
            raise
        except Exception as e:
            inner = _unwrap_httpx_status_error(e)
            if inner is not None:
                _log_http_error(self.name, inner)
            else:
                logger.exception("[MCP][%s] Tool error", self.name)
            raise

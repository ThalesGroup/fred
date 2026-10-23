# Copyright Thales 2025
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


import asyncio
import json
import logging
from copy import deepcopy
from typing import Any, Callable, Optional, cast
from urllib.parse import quote

import httpx  # ← we log/inspect HTTP errors coming from MCP adapters
from fred_core.common import OwnerFilter
from fred_core.common.team_id import is_personal_team_id
from fred_core.security.delegation import scrub_grant_text
from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.runtime import unwrap_run_stop_error
from fred_sdk.support.mcp_utils import normalize_mcp_content
from langchain_core.tools import BaseTool
from pydantic import Field

from fred_runtime.common.kf_base_client import KfBaseClient, KnowledgeFlowAgentContext
from fred_runtime.common.mcp_utils import MCP_DELEGATED_METADATA_KEY
from fred_runtime.common.structures import AgentSettingsLike
from fred_runtime.common.token_expiry import (
    is_expired_httpx_status_error,
    unwrap_httpx_status_error,
)
from fred_runtime.runtime_context import get_runtime_context
from fred_runtime.runtime_support import (
    RuntimeContextProvider,
    get_document_library_tags_ids,
    get_document_uids,
    get_rag_knowledge_scope,
    get_vector_search_scopes,
)
from fred_runtime.runtime_support.authority import AuthorityLostError

AgentSettingsProvider = Callable[[], AgentSettingsLike]

logger = logging.getLogger(__name__)

_READ_QUERY_TOOL_NAME = "read_query"


def _unwrap_httpx_status_error(exc: BaseException) -> Optional[httpx.HTTPStatusError]:
    # Backward compatibility for existing callers
    return unwrap_httpx_status_error(exc)


def _build_tool_error_message(
    exc: BaseException,
    inner: Optional[httpx.HTTPStatusError],
    *,
    tool_name: str | None = None,
) -> str:
    """Return a user-facing error string that surfaces upstream HTTP detail when available.

    FastAPI services return ``{"detail": "..."}`` on errors; we extract that field so
    the agent (and ultimately the user) sees the root cause rather than the HTTP status
    line.  Falls back to ``str(exc)`` when no HTTP response is present.
    """
    if inner is None:
        parsed = _parse_fastapi_mcp_http_error(exc, tool_name=tool_name)
        if parsed is not None and tool_name == _READ_QUERY_TOOL_NAME:
            status_code, detail = parsed
            if status_code == 400:
                return scrub_grant_text(f"Error: {detail}")
        return scrub_grant_text(f"Error: {exc}")
    code = inner.response.status_code if inner.response is not None else "?"
    detail = _http_error_detail(inner)
    if tool_name == _READ_QUERY_TOOL_NAME and code == 400:
        return scrub_grant_text(f"Error: {detail}")
    return scrub_grant_text(f"Error: HTTP {code}: {detail}")


def _http_error_detail(inner: httpx.HTTPStatusError) -> str:
    """Extract the upstream service detail without its HTTP transport wrapper."""
    detail: str = str(inner)
    try:
        if inner.response is not None:
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
    return detail


def _parse_fastapi_mcp_http_error(
    exc: BaseException, *, tool_name: str | None
) -> tuple[int, str] | None:
    """Parse FastApiMCP's bounded HTTP-error envelope.

    FastApiMCP currently serializes route failures into the MCP exception
    message instead of preserving an ``httpx.HTTPStatusError`` cause. Accept
    only its exact tool-specific prefix and a JSON object with a string
    ``detail`` field; malformed or unrelated provider text remains untrusted.
    """
    if not tool_name:
        return None
    prefix = f"Error calling {tool_name}. Status code: "
    message = str(exc)
    if not message.startswith(prefix):
        return None
    status_text, separator, response_text = message[len(prefix) :].partition(
        ". Response: "
    )
    if not separator:
        return None
    try:
        status_code = int(status_text)
        body = json.loads(response_text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(body, dict):
        return None
    detail = body.get("detail")
    if not isinstance(detail, str) or not detail:
        return None
    return status_code, detail


def _build_tool_error_artifact(
    tool_name: str,
    kwargs: dict[str, Any],
    exc: BaseException,
    inner: Optional[httpx.HTTPStatusError],
) -> ToolInvocationResult:
    """Return Fred's trusted failure signal for one caught MCP exception.

    Raw provider text stays out of generic user-facing errors. The sole curated
    exception is Knowledge Flow's ``read_query`` HTTP 400 contract: its ``detail``
    has already been classified and redacted by Knowledge Flow. The SQL remains
    in the paired tool-call arguments; the frontend joins those two trusted
    fields only for its dedicated ``read_query`` failure view.
    """
    is_read_query = (
        tool_name == _READ_QUERY_TOOL_NAME
        and isinstance(kwargs.get("sql"), str)
        and bool(str(kwargs["sql"]).strip())
    )
    detail: str | None = None
    if is_read_query and inner is not None and inner.response is not None:
        if inner.response.status_code == 400:
            try:
                body = inner.response.json()
            except (ValueError, httpx.ResponseNotRead):
                body = None
            if isinstance(body, dict) and isinstance(body.get("detail"), str):
                detail = body["detail"]
    elif is_read_query:
        parsed = _parse_fastapi_mcp_http_error(exc, tool_name=tool_name)
        if parsed is not None and parsed[0] == 400:
            detail = parsed[1]

    if detail:
        return ToolInvocationResult(
            tool_ref=tool_name,
            is_error=True,
            blocks=(
                ToolContentBlock(
                    kind=ToolContentKind.TEXT,
                    text=scrub_grant_text(detail),
                ),
            ),
        )

    # An empty error artifact carries the failure bit through LangChain while
    # forcing the shared trust boundary to use Fred's fixed generic message.
    return ToolInvocationResult(tool_ref=tool_name, is_error=True)


def _log_http_error(tool_name: str, err: httpx.HTTPStatusError) -> None:
    """
    Fred rationale:
    Give ops-grade traces that directly point to auth/token problems, with enough
    context (method, URL, body snippet) to debug quickly.
    """
    req = getattr(err, "request", None)
    resp = getattr(err, "response", None)

    method = getattr(req, "method", "?")
    raw_url = str(getattr(req, "url", "?"))
    url = scrub_grant_text(raw_url)
    # The failure's own text repeats the endpoint, so the traceback is kept
    # exactly when that endpoint had no grant on it to repeat.
    with_traceback = url == raw_url
    code = getattr(resp, "status_code", None)

    body_preview = ""
    try:
        if resp is not None:
            txt = resp.text
            # keep logs short; we only need a hint
            body_preview = scrub_grant_text(
                f" | body: {txt[:300].replace(chr(10), ' ')}"
            )
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
            exc_info=with_traceback,
        )
    else:
        logger.error(
            "[MCP][%s] HTTP %s on %s %s%s",
            tool_name,
            code,
            method,
            url,
            body_preview,
            exc_info=with_traceback,
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

    agent_context: object | None = Field(default=None, exclude=True)

    def __init__(
        self,
        base_tool: BaseTool,
        context_provider: RuntimeContextProvider,
        agent_settings_provider: AgentSettingsProvider,
        agent_context: object | None = None,
    ) -> None:
        # Preserve tool identity (name/description) so LLM can pick it properly.
        super().__init__(
            **base_tool.__dict__,
            base_tool=base_tool,
            context_provider=context_provider,
            agent_settings_provider=agent_settings_provider,
            agent_context=agent_context,
        )

        if "attachment_uids" in self._get_tool_properties():
            if isinstance(base_tool.args_schema, dict):
                schema = deepcopy(base_tool.args_schema)
            else:
                input_model = base_tool.get_input_schema()
                schema_factory = getattr(
                    input_model, "model_json_schema", None
                ) or getattr(input_model, "schema")
                schema = deepcopy(schema_factory())
            private_fields = {
                "attachment_uids",
                "corpus_document_uids",
                "include_session_scope",
                "include_corpus_scope",
                "owner_filter",
                "team_id",
                "session_id",
                "document_library_tags_ids",
            }
            for key in private_fields:
                schema.get("properties", {}).pop(key, None)
            schema["required"] = [
                key for key in schema.get("required", []) if key not in private_fields
            ]
            self.args_schema = schema

    async def _inject_tabular_scope(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Bind tabular calls to enabled sources and the persisted conversation."""
        context = self.context_provider()
        if context is None:
            raise ValueError("Tabular discovery requires a runtime context")
        settings = self.agent_settings_provider()
        sources = getattr(self.agent_context, "document_access_config", None) or {}
        session, corpus = get_vector_search_scopes(context)
        session = session and bool(sources.get("attachments", True))
        corpus = corpus and bool(sources.get("team_documents", True))
        if get_rag_knowledge_scope(context) == "general_only":
            session = corpus = False
        kwargs["include_corpus_scope"] = corpus
        kwargs["corpus_document_uids"] = get_document_uids(context)
        bound_documents = sources.get("document_uids")
        if bound_documents:
            selected = kwargs["corpus_document_uids"]
            kwargs["corpus_document_uids"] = [
                uid for uid in bound_documents if selected is None or uid in selected
            ]
        libraries = get_document_library_tags_ids(context)
        bound = (
            sources.get("library_tag_ids") if sources.get("bind_libraries") else None
        )
        if bound:
            libraries = [uid for uid in bound if libraries is None or uid in libraries]
        kwargs["document_library_tags_ids"] = libraries
        documents = kwargs["corpus_document_uids"]
        if (
            (libraries is not None or documents is not None)
            and not libraries
            and not documents
        ):
            kwargs["include_corpus_scope"] = False
        kwargs["owner_filter"] = (
            "personal"
            if is_personal_team_id(settings.team_id) or not settings.team_id
            else "team"
        )
        kwargs["team_id"] = (
            None if kwargs["owner_filter"] == "personal" else settings.team_id
        )
        # The model cannot supply a conversation or expand its attachment set.
        kwargs.pop("session_id", None)
        kwargs["attachment_uids"] = []
        if session and context.session_id:
            if self.agent_context is None or not context.team_id:
                raise ValueError(
                    "Conversation attachment discovery requires an authenticated team context"
                )
            config = get_runtime_context().config
            if not config.control_plane_url or config.control_plane_http_client is None:
                raise ValueError(
                    "Conversation attachment discovery requires the control-plane client"
                )
            client = KfBaseClient(
                frozenset({"GET"}),
                agent=cast(KnowledgeFlowAgentContext, self.agent_context),
            )
            client.base_url = config.control_plane_url.rstrip("/")
            client.client = config.control_plane_http_client
            response = await client._request_with_token_refresh(
                "GET",
                f"/teams/{quote(context.team_id, safe='')}/sessions/{quote(context.session_id, safe='')}/attachments",
                phase_name="tabular_attachment_scope",
            )
            inventory = response.json()
            if not isinstance(inventory, list) or len(inventory) > 1000:
                raise ValueError(
                    "Invalid or oversized conversation attachment inventory"
                )
            kwargs["attachment_uids"] = list(
                dict.fromkeys(
                    entry["document_uid"]
                    for entry in inventory
                    if isinstance(entry, dict)
                    and isinstance(entry.get("document_uid"), str)
                )
            )
        kwargs["include_session_scope"] = bool(session and kwargs["attachment_uids"])
        return kwargs

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

    def _check_delegated_result(self, result: Any) -> None:
        if not (self.base_tool.metadata or {}).get(MCP_DELEGATED_METADATA_KEY):
            return
        if not isinstance(result, tuple) or len(result) != 2:
            return
        artifact = result[1]
        if not isinstance(artifact, dict):
            return
        structured = artifact.get("structured_content")
        if isinstance(structured, dict) and structured.get("cause") == "authority_lost":
            raise AuthorityLostError() from None

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
            if "attachment_uids" in self._get_tool_properties():
                raise ValueError(
                    "Conversation-scoped tabular tools require async invocation"
                )
            result = self.base_tool._run(**kwargs)
            self._check_delegated_result(result)
        except Exception as e:
            run_stop = unwrap_run_stop_error(e)
            if run_stop is not None:
                # Raised before any logging: a refused call's body is not ours
                # to preview, and the run ends rather than answering the model.
                raise run_stop
            if (self.base_tool.metadata or {}).get(MCP_DELEGATED_METADATA_KEY) and str(
                e
            ) == "Tool access was refused.":
                raise AuthorityLostError() from None
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
            msg = _build_tool_error_message(e, inner, tool_name=self.name)
            if getattr(self, "response_format", None) == "content_and_artifact":
                return msg, _build_tool_error_artifact(self.name, kwargs, e, inner)
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
            if "attachment_uids" in self._get_tool_properties():
                kwargs = await self._inject_tabular_scope(kwargs)
                kwargs = self._sanitize_tool_kwargs(kwargs)
            result = await self.base_tool._arun(config=config, **kwargs)
            self._check_delegated_result(result)
        except asyncio.CancelledError:
            # Never swallow cancellation — re-raise so asyncio's cancellation
            # semantics stay intact. `ToolObservabilityMiddleware` records the
            # "cancelled" outcome around the whole call, including this one.
            raise
        except Exception as e:
            run_stop = unwrap_run_stop_error(e)
            if run_stop is not None:
                # Same rule as `_run`: a run-stopping error is not a tool result.
                raise run_stop
            if (self.base_tool.metadata or {}).get(MCP_DELEGATED_METADATA_KEY) and str(
                e
            ) == "Tool access was refused.":
                raise AuthorityLostError() from None
            # Check for HTTP status in the exception chain for better logs
            inner = _unwrap_httpx_status_error(e)

            if inner:
                _log_http_error(self.name, inner)
            else:
                logger.exception(
                    "[MCP][%s] Tool execution failed (captured)", self.name
                )

            # CRITICAL: Return error as text to preserve chat history integrity.
            msg = _build_tool_error_message(e, inner, tool_name=self.name)
            if getattr(self, "response_format", None) == "content_and_artifact":
                return msg, _build_tool_error_artifact(self.name, kwargs, e, inner)
            return msg
        else:
            return normalize_mcp_content(result)

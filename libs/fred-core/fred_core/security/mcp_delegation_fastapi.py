# pyright: reportMissingImports=false
"""Public HTTP customization for first-party MCP, plus the authority result shim.

Only this module needs the optional tool-server package. Request mapping and
ordinary MCP results/errors belong to the pinned upstream executor.
"""

from __future__ import annotations

import json
import logging
import re
from contextlib import suppress
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI
from fastapi.routing import APIRoute

from fred_core.common.fastapi_handlers import (
    ACCOUNT_STATUS_UNAVAILABLE_CAUSE,
    DENIAL_CAUSE_HEADER,
)
from fred_core.logs.propagation import CONTEXT_HEADER, outbound_context_headers
from fred_core.security.delegation import GRANT_PARAM_NAMES
from fred_core.security.mcp_delegation import apply_verified_grant, verified_grant

try:
    from fastapi_mcp import FastApiMCP
    from fastapi_mcp.types import HTTPRequestInfo
except ImportError as exc:  # pragma: no cover - exercised by the import test
    raise ImportError(
        "Delegated tool mounts need the tool-server package. "
        "Install fred-core with the 'mcp' extra."
    ) from exc

from mcp import types
from starlette.types import Receive, Scope, Send

logger = logging.getLogger(__name__)
_REFERENCE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_OPERATION_EXTENSION = "fred.mcp.operation"
# Each transport dispatch owns its bag, including when ASGI creates child tasks.
_operation: ContextVar[dict[str, str] | None] = ContextVar(
    "fred_mcp_operation", default=None
)


class _AuthorityRefused(Exception):
    """No body, path or credentials may escape through this exception."""


class DelegatedMCPTransport(httpx.AsyncBaseTransport):
    """Rewrite only reserved wire fields using invocation-local verified state."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app
        self._transport = httpx.ASGITransport(
            app=self._dispatch, raise_app_exceptions=False
        )

    async def _dispatch(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await self._app(scope, receive, send)
        finally:
            route = scope.get("route")
            metadata = _operation.get()
            if isinstance(route, APIRoute) and metadata is not None:
                metadata.update(
                    upstream_route=route.path,
                    tool_name=route.operation_id or route.unique_id,
                )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        content = await request.aread()
        headers = httpx.Headers(request.headers)
        headers.pop(CONTEXT_HEADER, None)
        if verified_grant() is not None:
            headers.update(outbound_context_headers())
        params = [
            (name, value)
            for name, value in request.url.params.multi_items()
            if name not in GRANT_PARAM_NAMES
        ]
        params.extend(apply_verified_grant({}).items())
        media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media_type == "application/json" or media_type.endswith("+json"):
            try:
                body = json.loads(content)
            except (ValueError, UnicodeError):
                body = None
            if isinstance(body, dict) and any(
                name in body for name in GRANT_PARAM_NAMES
            ):
                body = {
                    name: value
                    for name, value in body.items()
                    if name not in GRANT_PARAM_NAMES
                }
                content = json.dumps(
                    body, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
                headers.pop("transfer-encoding", None)
                headers["content-length"] = str(len(content))
        inner = httpx.Request(
            request.method,
            request.url.copy_with(query=urlencode(params).encode("ascii")),
            headers=headers,
            content=content,
            extensions=request.extensions,
        )
        metadata: dict[str, str] = {}
        token = _operation.set(metadata)
        try:
            response = await self._transport.handle_async_request(inner)
            response.extensions[_OPERATION_EXTENSION] = metadata
            return response
        finally:
            _operation.reset(token)

    async def aclose(self) -> None:
        await self._transport.aclose()


async def _inner_response(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    # HTTPX hooks run before automatic body reading; upstream must still read it.
    await response.aread()
    fields: dict[str, object] = {
        "method": response.request.method,
        "upstream_http_status": response.status_code,
        **response.extensions.get(_OPERATION_EXTENSION, {}),
    }
    for name in ("request", "correlation"):
        value = response.headers.get(f"X-{name}-ID", "")
        if _REFERENCE.fullmatch(value):
            fields[f"upstream_{name}_id"] = value
    # A diagnostic sink must not replace the operation's original failure.
    with suppress(Exception):
        logger.log(
            logging.ERROR if response.status_code >= 500 else logging.WARNING,
            "mcp.inner_http_failure",
            extra=fields,
        )
    if response.status_code in (401, 403) or (
        response.status_code == 503
        and response.headers.get(DENIAL_CAUSE_HEADER)
        == ACCOUNT_STATUS_UNAVAILABLE_CAUSE
    ):
        raise _AuthorityRefused("Tool access was refused.")


def delegated_mcp_http_client(app: FastAPI) -> httpx.AsyncClient:
    """The application owns this dedicated client and closes it in its lifespan."""
    return httpx.AsyncClient(
        transport=DelegatedMCPTransport(app),
        base_url="http://apiserver",
        timeout=10.0,
        follow_redirects=False,
        event_hooks={"response": [_inner_response]},
    )


class DelegatedFastApiMCP(FastApiMCP):
    """Translate only the typed authority refusal into the runtime stop contract."""

    async def _execute_api_tool(
        self,
        client: httpx.AsyncClient,
        tool_name: str,
        arguments: dict[str, Any],
        operation_map: dict[str, dict[str, Any]],
        http_request_info: HTTPRequestInfo | None = None,
    ) -> (
        list[types.TextContent | types.ImageContent | types.EmbeddedResource]
        | types.CallToolResult
    ):
        try:
            return await super()._execute_api_tool(
                client, tool_name, arguments, operation_map, http_request_info
            )
        except _AuthorityRefused:
            return types.CallToolResult(
                content=[
                    types.TextContent(type="text", text="Tool access was refused.")
                ],
                structuredContent={"cause": "authority_lost"},
                isError=True,
            )

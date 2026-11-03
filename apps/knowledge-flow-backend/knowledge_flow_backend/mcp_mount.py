"""Mount Knowledge Flow's FastAPI routes as authenticated MCP tools."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlencode

import httpx2
from fastapi import FastAPI, HTTPException, Request
from fastapi.routing import APIRoute
from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.providers.openapi import MCPType, RouteMap
from fastmcp.tools import ToolResult
from fastmcp.utilities.lifespan import combine_lifespans
from fred_core.common.fastapi_handlers import (
    ACCOUNT_STATUS_UNAVAILABLE_CAUSE,
    DENIAL_CAUSE_HEADER,
)
from fred_core.logs.propagation import CONTEXT_HEADER, outbound_context_headers
from fred_core.security.delegation import GRANT_PARAM_NAMES
from fred_core.security.mcp_delegation import mcp_mount_auth, verified_grant
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)
_REFERENCE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
_OPERATION_EXTENSION = "fred.mcp.operation"
# Each transport dispatch owns its bag, including when ASGI creates child tasks.
_operation: ContextVar[dict[str, str] | None] = ContextVar("fred_mcp_operation", default=None)


class _DelegatedMCPTransport(httpx2.AsyncBaseTransport):
    """Rewrite only reserved wire fields using invocation-local verified state."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app
        self._transport = httpx2.ASGITransport(app=self._dispatch, raise_app_exceptions=False)

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

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        content = await request.aread()
        headers = httpx2.Headers(request.headers)
        headers.pop(CONTEXT_HEADER, None)
        if verified_grant() is not None:
            headers.update(outbound_context_headers())
        params = [(name, value) for name, value in request.url.params.multi_items() if name not in GRANT_PARAM_NAMES]
        grant = verified_grant()
        if grant is not None:
            params.extend((("person", grant.person), ("run", grant.run), ("agent", grant.agent)))
        media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media_type == "application/json" or media_type.endswith("+json"):
            try:
                body = json.loads(content)
            except (ValueError, UnicodeError):
                body = None
            if isinstance(body, dict) and any(name in body for name in GRANT_PARAM_NAMES):
                body = {name: value for name, value in body.items() if name not in GRANT_PARAM_NAMES}
                content = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                headers.pop("transfer-encoding", None)
                headers["content-length"] = str(len(content))
        inner = httpx2.Request(
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


async def _inner_response(response: httpx2.Response) -> None:
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


class _MountAuthentication:
    """Run the existing FastAPI principal check for each MCP HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        token = token if scheme.lower() == "bearer" else ""
        auth = mcp_mount_auth(request=request, token=token)
        try:
            await anext(auth)
        except HTTPException as exc:
            response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
            await response(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            await auth.aclose()


async def _forward_verified_identity(request: httpx2.Request) -> None:
    """Carry only the identity already checked on the outer MCP request."""

    from fastmcp.server.dependencies import get_http_request

    outer = get_http_request()
    authorization = outer.headers.get("authorization")
    if authorization:
        request.headers["Authorization"] = authorization


def _curate_tool(route: Any, tool: Any) -> None:
    """Keep grants out of schemas shown to a model."""

    if route.summary and route.description and route.summary != route.description:
        tool.description = f"{route.summary}\n\n{route.description}"

    properties = tool.parameters.get("properties")
    if isinstance(properties, dict):
        for name in GRANT_PARAM_NAMES:
            properties.pop(name, None)
    required = tool.parameters.get("required")
    if isinstance(required, list):
        tool.parameters["required"] = [name for name in required if name not in GRANT_PARAM_NAMES]


class _ToolErrorPolicy(Middleware):
    async def on_call_tool(self, context: MiddlewareContext, call_next: Any) -> ToolResult:
        try:
            return await call_next(context)
        except Exception as exc:
            http_error = exc
            while not isinstance(http_error, httpx2.HTTPStatusError):
                http_error = http_error.__cause__
                if http_error is None:
                    return ToolResult(content="Tool request failed.", is_error=True)
            response = http_error.response
            status = response.status_code
            if status in (401, 403) or (status == 503 and response.headers.get(DENIAL_CAUSE_HEADER) == ACCOUNT_STATUS_UNAVAILABLE_CAUSE):
                return ToolResult(
                    content="Tool access was refused.",
                    structured_content={"cause": "authority_lost"},
                    is_error=True,
                )
            return ToolResult(
                content=f"Error calling {context.message.name}. Status code: {status}. Response: {response.text}",
                is_error=True,
            )


def _mcp_http_client(app: FastAPI) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        transport=_DelegatedMCPTransport(app),
        base_url="http://fastapi",
        timeout=10.0,
        follow_redirects=False,
        event_hooks={"response": [_inner_response]},
    )


def mount_fastapi_tools(
    app: FastAPI,
    *,
    path: str,
    name: str,
    description: str,
    tags: set[str],
) -> FastMCP:
    """Project selected routes using FastMCP's maintained FastAPI integration."""

    client = _mcp_http_client(app)
    client.event_hooks["request"].append(_forward_verified_identity)

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
        async with client:
            yield

    mcp = FastMCP.from_openapi(
        app.openapi(),
        client=client,
        lifespan=lifespan,
        name=name,
        instructions=description,
        route_maps=[
            *(RouteMap(tags={tag}, mcp_type=MCPType.TOOL) for tag in sorted(tags)),
            RouteMap(mcp_type=MCPType.EXCLUDE),
        ],
        mcp_component_fn=_curate_tool,
        cache_ttl=300,
        cache_scope="private",
        mask_error_details=True,
    )
    mcp.add_middleware(_ToolErrorPolicy())
    mcp_app = mcp.http_app(path=path, stateless_http=True, json_response=True)
    app.router.routes.append(Route(path, endpoint=_MountAuthentication(mcp_app), methods=["GET", "POST", "DELETE"]))
    app.router.lifespan_context = combine_lifespans(app.router.lifespan_context, mcp_app.lifespan)
    return mcp

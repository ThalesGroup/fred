"""Mount Knowledge Flow's FastAPI routes as authenticated MCP tools."""

from __future__ import annotations

import json
from typing import Any

import httpx2
from fastapi import FastAPI, HTTPException, Request
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
    request.headers.pop(CONTEXT_HEADER, None)

    query = [(name, value) for name, value in request.url.params.multi_items() if name not in GRANT_PARAM_NAMES]
    grant = verified_grant()
    if grant is not None:
        query.extend((("person", grant.person), ("run", grant.run), ("agent", grant.agent)))
        request.headers.update(outbound_context_headers())
    request.url = request.url.copy_with(query=str(httpx2.QueryParams(tuple(query))).encode())


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
            if status == 400 and context.message.name == "read_query":
                try:
                    detail = response.json().get("detail")
                except (ValueError, AttributeError):
                    detail = None
                if isinstance(detail, str) and detail:
                    return ToolResult(
                        content=("Error calling read_query. Status code: 400. Response: " + json.dumps({"detail": detail}, ensure_ascii=False)),
                        is_error=True,
                    )
            return ToolResult(content="Tool request failed.", is_error=True)


def mount_fastapi_tools(
    app: FastAPI,
    *,
    path: str,
    name: str,
    description: str,
    tags: set[str],
) -> FastMCP:
    """Project selected routes using FastMCP's maintained FastAPI integration."""

    mcp = FastMCP.from_fastapi(
        app,
        name=name,
        instructions=description,
        route_maps=[
            *(RouteMap(tags={tag}, mcp_type=MCPType.TOOL) for tag in sorted(tags)),
            RouteMap(mcp_type=MCPType.EXCLUDE),
        ],
        mcp_component_fn=_curate_tool,
        cache_ttl=300,
        cache_scope="private",
        httpx_client_kwargs={
            "follow_redirects": False,
            "event_hooks": {"request": [_forward_verified_identity]},
        },
        mask_error_details=True,
    )
    mcp.add_middleware(_ToolErrorPolicy())
    mcp_app = mcp.http_app(path=path, stateless_http=True, json_response=True)
    app.router.routes.append(Route(path, endpoint=_MountAuthentication(mcp_app), methods=["GET", "POST", "DELETE"]))
    app.router.lifespan_context = combine_lifespans(app.router.lifespan_context, mcp_app.lifespan)
    return mcp

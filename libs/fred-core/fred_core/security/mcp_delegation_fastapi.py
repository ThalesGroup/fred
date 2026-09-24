# pyright: reportMissingImports=false
"""The tool-mount subclass that places a verified grant on an inner call.

Separate from `mcp_delegation` because only this needs the tool-server package,
which services that mount no tools should not be made to install.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from fred_core.common.fastapi_handlers import (
    DENIAL_CAUSE_HEADER,
    STANDING_UNAVAILABLE_CAUSE,
)
from fred_core.security.mcp_delegation import apply_verified_grant

try:
    from fastapi_mcp import FastApiMCP
    from fastapi_mcp.types import HTTPRequestInfo
except ImportError as exc:  # pragma: no cover - exercised by the import test
    raise ImportError(
        "Delegated tool mounts need the tool-server package. "
        "Install fred-core with the 'mcp' extra."
    ) from exc

from mcp import types


class DelegatedFastApiMCP(FastApiMCP):
    """Place only the grant verified at the mount on the inner route call."""

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
        operation = operation_map[tool_name]
        path = operation["path"]
        method = operation["method"]
        values = apply_verified_grant(arguments)
        query: dict[str, Any] = {}
        headers: dict[str, str] = {}
        for parameter in operation.get("parameters", []):
            name = parameter.get("name")
            if name not in values:
                continue
            location = parameter.get("in")
            if location == "path":
                path = path.replace("{" + name + "}", str(values.pop(name)))
            elif location == "query":
                query[name] = values.pop(name)
            elif location == "header":
                headers[name] = values.pop(name)
        if http_request_info and http_request_info.headers:
            for name, value in http_request_info.headers.items():
                if name.lower() in self._forward_headers:
                    headers[name] = value
        response = await self._request(
            client, method, path, query, headers, values or None
        )
        if response.status_code in (401, 403) or (
            response.status_code == 503
            and response.headers.get(DENIAL_CAUSE_HEADER) == STANDING_UNAVAILABLE_CAUSE
        ):
            return types.CallToolResult(
                content=[
                    types.TextContent(type="text", text="Tool access was refused.")
                ],
                structuredContent={"cause": "authority_lost"},
                isError=True,
            )
        if response.status_code >= 400:
            raise RuntimeError("Tool request failed.") from None
        try:
            content = json.dumps(response.json(), indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            content = response.text
        return [types.TextContent(type="text", text=content)]

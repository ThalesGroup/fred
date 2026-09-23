# pyright: reportMissingImports=false
"""The tool-mount subclass that places a verified grant on an inner call.

Separate from `mcp_delegation` because only this needs the tool-server package,
which services that mount no tools should not be made to install.
"""

from __future__ import annotations

from typing import Any

import httpx

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
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        return await super()._execute_api_tool(
            client,
            tool_name,
            apply_verified_grant(arguments),
            operation_map,
            http_request_info,
        )

# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Execute admitted MCP bindings using the existing FastMCP/LangChain adapter.

Every client belongs to one turn. There is no registry mutation, local catalogue
fallback, shared cache, Fred credential forwarding or business authorization here.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Sequence

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fred_sdk.contracts.managed_mcp import McpBinding, McpCredentialBinding, McpTool
from langchain.mcp import as_langchain_tool
from langchain_core.tools import BaseTool, StructuredTool

from .mcp_utils import _mcp_http_client_factory, MCP_SERVER_ID_METADATA_KEY


class ManagedMcpError(ValueError):
    """Stable diagnostic, safe for logs and user-facing execution errors."""


def credential_headers(
    binding: McpBinding, credentials: Sequence[McpCredentialBinding]
) -> dict[str, str]:
    auth = binding.configuration.authentication
    if auth.kind == "none":
        return {}
    matches = [
        c for c in credentials if c.credential_binding == auth.credential_binding
    ]
    if len(matches) != 1 or matches[0].url != binding.configuration.url:
        raise ManagedMcpError("mcp_credential_destination_mismatch")
    secret = os.environ.get(matches[0].secret_env)
    if not secret:
        raise ManagedMcpError("mcp_credential_missing")
    if "\n" in secret or "\r" in secret:
        raise ManagedMcpError("mcp_credential_invalid")
    return (
        {"Authorization": f"Bearer {secret}"}
        if auth.kind == "bearer"
        else {auth.header: secret}
    )


def validate_admission(
    selected: Sequence[str],
    bindings: Sequence[McpBinding],
    *,
    compatible: bool,
    credentials: Sequence[McpCredentialBinding],
) -> None:
    expected = {key for key in selected if key.startswith("managed-mcp:")}
    actual = {binding.capability_id for binding in bindings}
    if (
        expected != actual
        or len(actual) != len(bindings)
        or (actual and not compatible)
    ):
        raise ManagedMcpError("mcp_binding_mismatch")
    for binding in bindings:
        credential_headers(binding, credentials)


def _contract(tool) -> McpTool:
    return McpTool(
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema,
        output_schema=tool.output_schema,
        annotations=tool.annotations.model_dump(by_alias=True, exclude_none=True)
        if tool.annotations
        else None,
    )


def _guard_call(call, secrets=()):
    async def guarded(**arguments):
        try:
            result = await call(**arguments)
            serialized = json.dumps(result, default=str) if secrets else ""
            if not any(
                secret in serialized or json.dumps(secret)[1:-1] in serialized
                for secret in secrets
            ):
                return result
        except Exception:
            pass
        # Raise outside the handler: legacy error unwrappers inspect __context__
        # even when Python suppresses its display with `from None`.
        raise ManagedMcpError("mcp_tool_unavailable")

    return guarded


def _client_factory(credential_headers):
    def factory(headers=None, **kwargs):
        return _mcp_http_client_factory(
            headers={**(headers or {}), **credential_headers}, **kwargs
        )

    return factory


async def connect(
    bindings: Sequence[McpBinding], credentials: Sequence[McpCredentialBinding]
) -> list[BaseTool]:
    tools: list[BaseTool] = []
    for binding in bindings:
        headers = credential_headers(binding, credentials)
        client = Client(
            StreamableHttpTransport(
                binding.configuration.url, httpx_client_factory=_client_factory(headers)
            ),
            init_timeout=5,
            timeout=30,
            cache=False,
        )
        try:
            async with asyncio.timeout(20), client:
                remote = {}
                cursors: set[str] = set()
                cursor = None
                total_bytes = 0
                for _ in range(16):
                    page = await client.list_tools_mcp(
                        cursor=cursor, cache_mode="bypass"
                    )
                    total_bytes += len(page.model_dump_json().encode())
                    if total_bytes > 1024 * 1024:
                        raise ManagedMcpError("mcp_inventory_limit")
                    for tool in page.tools:
                        if tool.name in remote or len(remote) >= 256:
                            raise ManagedMcpError("mcp_inventory_limit")
                        remote[tool.name] = tool
                    cursor = page.next_cursor
                    if cursor is None:
                        break
                    if cursor in cursors:
                        raise ManagedMcpError("mcp_invalid_pagination")
                    cursors.add(cursor)
                else:
                    raise ManagedMcpError("mcp_inventory_limit")
                # Additions are ignored; removals and contract changes fail closed.
                for published in binding.tools:
                    candidate = remote.get(published.name)
                    if candidate is None or _contract(candidate) != published:
                        raise ManagedMcpError("mcp_published_tool_changed")
                    tool = await as_langchain_tool(candidate, client)
                    if not isinstance(tool, StructuredTool):
                        raise ManagedMcpError("mcp_adapter_incompatible")
                    suffix = hashlib.sha256(published.name.encode()).hexdigest()[:16]
                    tool = tool.model_copy(
                        update={
                            "name": f"mcp_{binding.connection_id.hex}_{suffix}",
                            # Preserve the exact business name even without a remote
                            # description; the opaque execution identity stays stable.
                            "description": f"MCP tool: {published.name}."
                            + (
                                f"\n{published.description}"
                                if published.description
                                else ""
                            ),
                            "coroutine": _guard_call(
                                tool.coroutine,
                                tuple(
                                    value.removeprefix("Bearer ")
                                    for value in headers.values()
                                ),
                            ),
                            "metadata": {
                                **(tool.metadata or {}),
                                MCP_SERVER_ID_METADATA_KEY: binding.capability_id,
                            },
                        }
                    )
                    tools.append(tool)
            # Adapter tools reopen/close their client per invocation, as native MCP does.
        except ManagedMcpError:
            raise
        except Exception:
            raise ManagedMcpError("mcp_connection_unavailable") from None
    return tools

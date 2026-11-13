# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Execute admitted MCP bindings using the existing FastMCP/LangChain adapter.

Every client belongs to one turn. There is no registry mutation, local catalogue
fallback or shared cache. Fred credentials are restricted to the configured trusted service.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Callable, Sequence
from urllib.parse import urlsplit

import httpx2
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fred_sdk.authoring.knowledge_flow_mcp import MCP_SERVER_KNOWLEDGE_FLOW_TABULAR
from fred_sdk.contracts.managed_mcp import (
    McpBinding,
    McpConnectionBinding,
    McpCredentialBinding,
    McpTabularBinding,
    McpTool,
)
from fred_sdk.contracts.runtime import unwrap_run_stop_error
from fred_sdk.contracts.services import FredService
from langchain.mcp import as_langchain_tool
from langchain_core.tools import BaseTool, StructuredTool

from .mcp_http_auth import MCPHTTPAuth
from .mcp_utils import (
    MCP_DELEGATED_METADATA_KEY,
    MCP_SERVER_ID_METADATA_KEY,
    MCP_SERVICE_METADATA_KEY,
    MCP_TOOL_DISPLAY_NAME_METADATA_KEY,
    _mcp_http_client_factory,
)
from .outbound_credentials import (
    DelegatedCredentialProvider,
    OutboundCredentialProvider,
    grant_query_url,
)


class ManagedMcpError(ValueError):
    """Stable diagnostic, safe for logs and user-facing execution errors."""


def credential_headers(
    binding: McpConnectionBinding, credentials: Sequence[McpCredentialBinding]
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
    knowledge_flow_url: str | None = None,
    included: Sequence[str] | None = None,
) -> None:
    expected = {
        key
        for key in selected
        if key.startswith("managed-mcp:") or key == MCP_SERVER_KNOWLEDGE_FLOW_TABULAR
    }
    actual = {binding.capability_id for binding in bindings}
    if (
        expected != actual
        or len(actual) != len(bindings)
        or (actual and not compatible)
    ):
        raise ManagedMcpError("mcp_binding_mismatch")
    if included is not None and (
        len(selected) != len(included) or set(selected) != set(included)
    ):
        raise ManagedMcpError("mcp_included_dependency_mismatch")
    for binding in bindings:
        trusted_destination(binding, knowledge_flow_url)
        if isinstance(binding, McpConnectionBinding):
            credential_headers(binding, credentials)


def trusted_destination(binding: McpBinding, base: str | None) -> bool:
    if not isinstance(binding, McpTabularBinding):
        return False
    expected = f"{base.rstrip('/')}/mcp/tabular" if base else None
    parsed = urlsplit(base or "")
    if (
        not expected
        or binding.url != expected
        or parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ManagedMcpError("mcp_service_destination_mismatch")
    return True


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


def _guard_call(call, secrets=(), *, trusted_tool: str | None = None):
    async def guarded(**arguments):
        try:
            result = await call(**arguments)
            serialized = json.dumps(result, default=str) if secrets else ""
            safe_to_return = not any(
                secret in serialized or json.dumps(secret)[1:-1] in serialized
                for secret in secrets
            )
        except Exception as exc:
            if trusted_tool is not None:
                from fred_runtime.runtime_support.authority import AuthorityLostError

                from .context_aware_tool import _parse_fastapi_mcp_http_error

                stop = unwrap_run_stop_error(exc)
                if stop is not None:
                    raise stop from None
                if str(exc) == "Tool access was refused.":
                    raise AuthorityLostError() from None
                if (
                    _parse_fastapi_mcp_http_error(exc, tool_name=trusted_tool)
                    is not None
                ):
                    raise
            result = None
            safe_to_return = False
        if safe_to_return:
            return result
        # Raise outside the handler: legacy error unwrappers inspect __context__
        # even when Python suppresses its display with `from None`.
        raise ManagedMcpError("mcp_tool_unavailable")

    return guarded


def _client_factory(credential_headers: dict[str, str]):
    def factory(
        headers: dict[str, str] | None = None,
        timeout: httpx2.Timeout | None = None,
        auth: httpx2.Auth | None = None,
        follow_redirects: bool = False,
    ) -> httpx2.AsyncClient:
        return _mcp_http_client_factory(
            headers={**(headers or {}), **credential_headers},
            timeout=timeout,
            auth=auth,
            follow_redirects=follow_redirects,
        )

    return factory


async def connect(
    bindings: Sequence[McpBinding],
    credentials: Sequence[McpCredentialBinding],
    *,
    knowledge_flow_url: str | None = None,
    provider: OutboundCredentialProvider | None = None,
    document_context: Callable[[], str] | None = None,
) -> list[BaseTool]:
    tools: list[BaseTool] = []
    for binding in bindings:
        trusted = trusted_destination(binding, knowledge_flow_url)
        headers = (
            credential_headers(binding, credentials)
            if isinstance(binding, McpConnectionBinding)
            else {}
        )
        url = (
            binding.configuration.url
            if isinstance(binding, McpConnectionBinding)
            else binding.url
        )
        auth = None
        if trusted:
            if (
                not isinstance(provider, DelegatedCredentialProvider)
                or document_context is None
            ):
                raise ManagedMcpError("mcp_delegated_context_required")
            grant = await provider.credentials()
            url = grant_query_url(url, grant.parameters)
            auth = MCPHTTPAuth(
                provider, document_context=document_context, destination=url
            )
        client = Client(
            StreamableHttpTransport(
                url, auth=auth, httpx_client_factory=_client_factory(headers)
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
                # External tools require their reviewed contracts. Internal tools
                # belong to the trusted Fred service and need no publication.
                contracts = (
                    binding.tools
                    if isinstance(binding, McpConnectionBinding)
                    else tuple(_contract(tool) for tool in remote.values())
                )
                if not contracts:
                    raise ManagedMcpError("mcp_inventory_empty")
                for contract in contracts:
                    candidate = remote.get(contract.name)
                    if candidate is None or _contract(candidate) != contract:
                        raise ManagedMcpError("mcp_published_tool_changed")
                    tool = await as_langchain_tool(candidate, client)
                    if not isinstance(tool, StructuredTool):
                        raise ManagedMcpError("mcp_adapter_incompatible")
                    suffix = hashlib.sha256(contract.name.encode()).hexdigest()[:16]
                    tool = tool.model_copy(
                        update={
                            "name": f"mcp_{binding.connection_id.hex}_{suffix}"
                            if isinstance(binding, McpConnectionBinding)
                            else contract.name,
                            # Preserve the exact business name even without a remote
                            # description; the opaque execution identity stays stable.
                            "description": f"MCP tool: {contract.name}."
                            + (
                                f"\n{contract.description}"
                                if contract.description
                                else ""
                            ),
                            "coroutine": _guard_call(
                                tool.coroutine,
                                tuple(
                                    value.removeprefix("Bearer ")
                                    for value in headers.values()
                                ),
                                trusted_tool=contract.name if trusted else None,
                            ),
                            "metadata": {
                                **(tool.metadata or {}),
                                MCP_SERVER_ID_METADATA_KEY: MCP_SERVER_KNOWLEDGE_FLOW_TABULAR
                                if trusted
                                else binding.capability_id,
                                MCP_SERVICE_METADATA_KEY: FredService.KNOWLEDGE_FLOW
                                if trusted
                                else None,
                                MCP_DELEGATED_METADATA_KEY: trusted,
                                "mcp_trusted_service": "knowledge_flow_tabular"
                                if trusted
                                else None,
                                "mcp_tool_name": contract.name,
                                MCP_TOOL_DISPLAY_NAME_METADATA_KEY: (
                                    f"{binding.display_name} · {contract.name}"
                                    if isinstance(binding, McpConnectionBinding)
                                    and binding.display_name.strip()
                                    else contract.name
                                ),
                                "mcp_connection_id": str(binding.connection_id)
                                if isinstance(binding, McpConnectionBinding)
                                else None,
                            },
                        }
                    )
                    tools.append(tool)
            # Adapter tools reopen/close their client per invocation, as native MCP does.
        except ManagedMcpError:
            raise
        except Exception as exc:
            stop = unwrap_run_stop_error(exc)
            if stop is not None:
                raise stop from None
            raise ManagedMcpError("mcp_connection_unavailable") from None
    return tools

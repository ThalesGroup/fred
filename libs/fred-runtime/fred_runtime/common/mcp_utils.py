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

"""Discover MCP tools through LangChain's first-party FastMCP adapter."""

from __future__ import annotations

import hashlib
import logging
import time
from functools import partial
from typing import Final

import httpx2
from fastmcp import Client
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport
from fred_core.common.fastapi_handlers import (
    ACCOUNT_STATUS_UNAVAILABLE_CAUSE,
    DENIAL_CAUSE_HEADER,
)
from fred_core.security.delegation import scrub_grant_text
from fred_sdk.contracts.context import RuntimeContext
from fred_sdk.contracts.models import MCPServerConfiguration
from fred_sdk.contracts.runtime import unwrap_run_stop_error
from langchain.mcp import MCPAdapter
from langchain_core.tools import BaseTool
from mcp.client.caching import CacheConfig, InMemoryResponseCacheStore

from fred_runtime.common.mcp_http_auth import MCPHTTPAuth
from fred_runtime.common.outbound_credentials import (
    OutboundCredentialProvider,
    OutboundCredentials,
    grant_query_url,
    resolve_credential_provider,
)
from fred_runtime.common.structures import TokenRefreshCallback
from fred_runtime.runtime_support.authority import (
    AuthorityLostError,
    DelegationUnavailableError,
)

logger = logging.getLogger(__name__)

SUPPORTED_TRANSPORTS = ["streamable_http", "stdio"]
AUTH_MODE_NO_TOKEN: Final[str] = "no_token"
AUTH_MODE_USER_TOKEN: Final[str] = "user_token"
AUTH_MODE_DELEGATED: Final[str] = "delegated"
GRANT_CARRYING_TRANSPORTS: Final[tuple[str, ...]] = ("streamable_http",)
MCP_SERVER_ID_METADATA_KEY: Final[str] = "mcp_server_id"
MCP_DELEGATED_METADATA_KEY: Final[str] = "mcp_delegated"
CONNECT_TIMEOUT_SECS = 5.0
SSE_READ_TIMEOUT_SECS = 30.0
_tool_catalog_cache = InMemoryResponseCacheStore(max_entries=1024)


class MCPConnectionError(Exception):
    """Raised when one or more configured servers fail discovery."""

    def __init__(self, message: str, exceptions: list[Exception]):
        super().__init__(message)
        self.exceptions = exceptions
        self.reason = message


class UnsupportedTransportError(ValueError):
    """The catalog accepts this transport, but the runtime cannot execute it."""


def _normalize_transport(transport: str | None) -> str:
    return (transport or "streamable_http").lower()


def _normalize_auth_mode(auth_mode: object) -> str:
    return str(getattr(auth_mode, "value", auth_mode) or AUTH_MODE_USER_TOKEN)


async def _runtime_context_token(runtime_context: RuntimeContext) -> str | None:
    return runtime_context.access_token


def _server_connection_auth(
    server: MCPServerConfiguration,
    credentials: OutboundCredentials,
    transport: str,
) -> tuple[dict[str, str], dict[str, str], str | None]:
    auth_mode = _normalize_auth_mode(server.auth_mode)
    if auth_mode == AUTH_MODE_NO_TOKEN:
        return {}, {}, server.url
    if credentials.delegated:
        if auth_mode != AUTH_MODE_DELEGATED:
            raise DelegationUnavailableError(
                "A tool server this agent uses cannot be activated under delegation."
            )
        if transport not in GRANT_CARRYING_TRANSPORTS:
            raise DelegationUnavailableError(
                "A tool server this agent uses cannot carry a delegation grant."
            )
        return {}, {}, grant_query_url(server.url or "", credentials.parameters)
    authorization = credentials.authorization
    env = (
        {"MCP_AUTHORIZATION": authorization, "AUTHORIZATION": authorization}
        if authorization
        else {}
    )
    return {}, env, server.url


def _mcp_http_client_factory(
    headers: dict[str, str] | None = None,
    timeout: httpx2.Timeout | None = None,
    auth: httpx2.Auth | None = None,
    follow_redirects: bool = False,
) -> httpx2.AsyncClient:
    # httpx2 counts one auth retry in redirect history even when redirects are off.
    # The MCP SDK also follows redirects itself, so reject them before it can.
    return httpx2.AsyncClient(
        headers=headers,
        auth=auth,
        timeout=timeout,
        follow_redirects=False,
        max_redirects=1,
        event_hooks={"response": [_reject_mcp_redirect]},
    )


async def _reject_mcp_redirect(response: httpx2.Response) -> None:
    if response.has_redirect_location:
        raise httpx2.TooManyRedirects(
            "MCP HTTP redirect refused.", request=response.request
        )


def _refusal_status(error: BaseException) -> int | None:
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, httpx2.HTTPStatusError):
            response = current.response
            if response.status_code in (401, 403) or (
                response.status_code == 503
                and response.headers.get(DENIAL_CAUSE_HEADER)
                == ACCOUNT_STATUS_UNAVAILABLE_CAUSE
            ):
                return response.status_code
        pending.extend(
            member
            for member in getattr(current, "exceptions", ())
            if isinstance(member, BaseException)
        )
        pending.extend(
            nested
            for nested in (current.__cause__, current.__context__)
            if nested is not None
        )
    return None


def _catalog_cache_config(
    server: MCPServerConfiguration, credentials: OutboundCredentials
) -> CacheConfig | None:
    if credentials.delegated:
        return None
    # Cache only protocol responses; each run still owns fresh callable tools and auth.
    partition = hashlib.sha256(
        (credentials.authorization or "anonymous").encode()
    ).hexdigest()
    target_id = hashlib.sha256(server.model_dump_json().encode()).hexdigest()
    return CacheConfig(
        store=_tool_catalog_cache,
        partition=partition,
        target_id=target_id,
        default_ttl_ms=0,
    )


async def get_connected_mcp_client_for_agent(
    agent_id: str,
    mcp_servers: list[MCPServerConfiguration],
    runtime_context: RuntimeContext,
    *,
    credentials: OutboundCredentialProvider | None = None,
    refresh_token_cb: TokenRefreshCallback | None = None,
    refresh_owner: object | None = None,
) -> tuple[list[MCPAdapter], list[BaseTool]]:
    """List tools once per server and retain the adapter's callable tools."""

    provider = resolve_credential_provider(
        explicit=credentials,
        person_token_getter=partial(_runtime_context_token, runtime_context),
    )
    for server in mcp_servers:
        transport = _normalize_transport(server.transport)
        if transport not in SUPPORTED_TRANSPORTS:
            raise UnsupportedTransportError(
                f"Unsupported transport '{server.transport}'. Supported: {', '.join(SUPPORTED_TRANSPORTS)}"
            )

    needs_credentials = any(
        _normalize_auth_mode(server.auth_mode) != AUTH_MODE_NO_TOKEN
        for server in mcp_servers
    )
    call_credentials = (
        await provider.credentials() if needs_credentials else OutboundCredentials()
    )

    adapters: list[MCPAdapter] = []
    fetched_tools: list[BaseTool] = []
    exceptions: list[Exception] = []
    for server in mcp_servers:
        transport = _normalize_transport(server.transport)
        _, env, url = _server_connection_auth(server, call_credentials, transport)
        try:
            if transport == "streamable_http":
                if not url:
                    raise ValueError(f"{server.name}: missing URL for streamable_http")
                auth = (
                    MCPHTTPAuth(
                        provider,
                        refresh=refresh_token_cb if not provider.delegated else None,
                        refresh_owner=refresh_owner,
                    )
                    if _normalize_auth_mode(server.auth_mode) != AUTH_MODE_NO_TOKEN
                    else None
                )
                mcp_transport = StreamableHttpTransport(
                    url,
                    auth=auth,
                    httpx_client_factory=_mcp_http_client_factory,
                )
            else:
                if not server.command:
                    raise ValueError(
                        f"{server.name}: missing command for stdio transport"
                    )
                merged_env = {**env, **(server.env or {})}
                mcp_transport = StdioTransport(
                    command=server.command,
                    args=list(server.args or []),
                    env=merged_env or None,
                    keep_alive=False,
                )

            adapter = MCPAdapter(
                Client(
                    mcp_transport,
                    init_timeout=CONNECT_TIMEOUT_SECS,
                    timeout=SSE_READ_TIMEOUT_SECS,
                    cache=_catalog_cache_config(server, call_credentials),
                )
            )
            started = time.perf_counter()
            tools = await adapter.list_tools()
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "[MCP] event=connection_validation outcome=succeeded tools=%d dur_ms=%.0f",
                len(tools),
                elapsed_ms,
            )
            tagged = [
                tool.model_copy(
                    update={
                        "metadata": {
                            **(tool.metadata or {}),
                            MCP_SERVER_ID_METADATA_KEY: server.id,
                            MCP_DELEGATED_METADATA_KEY: bool(
                                call_credentials.delegated
                                and _normalize_auth_mode(server.auth_mode)
                                == AUTH_MODE_DELEGATED
                            ),
                        }
                    }
                )
                for tool in tools
            ]
            adapters.append(adapter)
            fetched_tools.extend(tagged)
        except Exception as exc:
            run_stop = unwrap_run_stop_error(exc)
            if run_stop is not None:
                raise run_stop from None
            if call_credentials.delegated and _refusal_status(exc) is not None:
                raise AuthorityLostError() from None
            logger.warning(
                "[MCP] event=connection_validation outcome=failed server=%s error=%s",
                server.id,
                type(exc).__name__,
            )
            exceptions.append(exc)

    if exceptions:
        reason = "Some MCP connections failed. Check the configured tool servers."
        if not call_credentials.delegated:
            reason += " " + "; ".join(
                scrub_grant_text(f"{type(exc).__name__}: {str(exc).splitlines()[0]}")
                for exc in exceptions
            )
        raise MCPConnectionError(reason, exceptions)
    return adapters, fetched_tools

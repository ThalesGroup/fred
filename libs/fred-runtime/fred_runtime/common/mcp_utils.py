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

"""
mcp_utils
=========

Single-responsibility module that **creates and connects** a `MultiServerMCPClient`
for a given agent, using the **end-user's identity token** for outbound auth.

This module enforces user identity propagation and **removes M2M fallback**.

Contract
--------
- Requires an `access_token_provider` (a callable) to fetch the user's token
  before connecting to any MCP server.
- Returns a connected `MultiServerMCPClient` plus the tools already fetched
  while validating each server (see `get_connected_mcp_client_for_agent`).
- Raises `ExceptionGroup` if **any** server fails to connect.

"""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from functools import partial
from typing import Dict, Final, List, Tuple

import httpx
from fred_core.security.delegation import scrub_grant_text
from fred_sdk.contracts.context import RuntimeContext
from fred_sdk.contracts.models import MCPServerConfiguration
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import Connection, StreamableHttpConnection

from fred_runtime.common.outbound_credentials import (
    OutboundCredentialProvider,
    OutboundCredentials,
    grant_query_url,
    resolve_credential_provider,
)
from fred_runtime.runtime_support.authority import (
    AuthorityLostError,
    DelegationUnavailableError,
)

logger = logging.getLogger(__name__)

# ✅ Only allow transports that Fred knows how to configure safely.
SUPPORTED_TRANSPORTS = ["sse", "stdio", "streamable_http", "websocket"]

# Client auth modes, as strings: the `delegated` value is read from configuration
# and compared here, so this module needs no enum member that may not exist yet.
AUTH_MODE_NO_TOKEN: Final[str] = "no_token"
AUTH_MODE_USER_TOKEN: Final[str] = "user_token"
AUTH_MODE_DELEGATED: Final[str] = "delegated"

# Transports whose endpoint can carry the grant beside the tool call. A grant
# cannot ride a pipe, and dropping it would make the call act for nobody.
GRANT_CARRYING_TRANSPORTS: Final[tuple[str, ...]] = ("streamable_http", "sse")

# What a receiver answers when it will not act for this run's person any more.
_REFUSAL_STATUSES: Final[tuple[int, ...]] = (401, 403)

# Key under which a fetched tool's originating MCP catalog server id is stashed
# in `BaseTool.metadata` (issue #2455) — the one generic, already-present field
# that survives `ContextAwareTool` wrapping and every merge/dedupe step
# downstream untouched, so no new constructor parameter needs threading
# through `MCPRuntime`/`McpToolkit`/`FredMcpToolProvider`. Consumed by
# `react_tool_resolution.py` to group the ReAct prompt's tool listing by
# server (`react_tool_binding.build_runtime_tool_prompt_suffix`).
MCP_SERVER_ID_METADATA_KEY: Final[str] = "mcp_server_id"


class MCPConnectionError(Exception):
    """Raised when one or more MCP servers fail to connect."""

    def __init__(self, message, exceptions):
        super().__init__(message)
        self.exceptions = exceptions
        self.reason = message


class UnsupportedTransportError(ValueError):
    """
    Raised when an MCP server uses a transport the runtime does not support.

    Why this exists:
    - surface configuration errors early with a clear, typed exception

    How to use it:
    - raise when a server transport is not in `SUPPORTED_TRANSPORTS`

    Example:
        >>> raise UnsupportedTransportError("Unsupported transport 'grpc'.")
    """


def _mask_auth_value(v: str | None) -> str:
    """Return a non-sensitive label for Authorization header values."""
    if not v:
        return "none"
    if v.lower().startswith("bearer "):
        # Never leak token fragments in logs.
        return "present:Bearer"
    return "present"


def _auth_headers(authorization: str | None) -> Dict[str, str]:
    """Build HTTP Authorization headers from a ready header value.

    If there is no credential, returns an empty dict (connection will fail 401).
    """
    if authorization:
        return {"Authorization": authorization}
    return {}


def _auth_stdio_env(authorization: str | None) -> Dict[str, str]:
    """Build env vars used to pass auth to stdio transports.

    Mirrors the Authorization header as environment variables.
    """
    hdrs = _auth_headers(authorization)
    if not hdrs:
        return {}
    val = hdrs["Authorization"]
    return {"MCP_AUTHORIZATION": val, "AUTHORIZATION": val}


def _loggable_url(url: str | None) -> str:
    return scrub_grant_text(url) if url else ""


def _refusal_status(error: BaseException) -> int | None:
    """The 401 or 403 a receiver answered with, anywhere in the failure.

    The tool listing's HTTP failure reaches us wrapped by the adapter and its
    task group, so the refusal is only visible by walking causes and members.
    """
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if (
            isinstance(current, httpx.HTTPStatusError)
            and current.response.status_code in _REFUSAL_STATUSES
        ):
            return current.response.status_code
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


def _normalize_auth_mode(auth_mode: object) -> str:
    """Read a catalog entry's auth mode as a plain string."""
    return str(getattr(auth_mode, "value", auth_mode) or AUTH_MODE_USER_TOKEN)


async def _runtime_context_token(runtime_context: RuntimeContext) -> str | None:
    return runtime_context.access_token


def _server_connection_auth(
    server: MCPServerConfiguration,
    credentials: OutboundCredentials,
    transport: str,
) -> tuple[Dict[str, str], Dict[str, str], str | None]:
    """Decide what one server's connection carries: headers, stdio env, endpoint.

    Under delegation the mode is an activation decision, not a hint: only a
    server declared `delegated` is activated, and its grant travels on the
    endpoint so it can never be mistaken for a tool argument.
    """
    auth_mode = _normalize_auth_mode(server.auth_mode)
    if auth_mode == AUTH_MODE_NO_TOKEN:
        return {}, {}, server.url

    if credentials.delegated:
        if auth_mode != AUTH_MODE_DELEGATED:
            logger.error(
                "[MCP] event=server_activation outcome=refused "
                "reason=incompatible_auth_mode"
            )
            raise DelegationUnavailableError(
                "A tool server this agent uses cannot be activated under delegation."
            )
        if transport not in GRANT_CARRYING_TRANSPORTS:
            logger.error(
                "[MCP] event=server_activation outcome=refused "
                "reason=unsupported_grant_transport"
            )
            raise DelegationUnavailableError(
                "A tool server this agent uses cannot carry a delegation grant."
            )
        return (
            _auth_headers(credentials.authorization),
            {},
            grant_query_url(server.url or "", credentials.parameters),
        )

    if not credentials.authorization:
        logger.warning(
            "[MCP] event=server_activation outcome=degraded reason=missing_user_token"
        )
    return (
        _auth_headers(credentials.authorization),
        _auth_stdio_env(credentials.authorization),
        server.url,
    )


# --- small, clear constants (Fred rationale: fast-fail, let retry loop recover) ---
CONNECT_TIMEOUT_SECS = 5.0
SSE_READ_TIMEOUT_SECS = 30.0
CONNECT_TIMEOUT_TD = timedelta(seconds=CONNECT_TIMEOUT_SECS)
SSE_READ_TIMEOUT_TD = timedelta(seconds=SSE_READ_TIMEOUT_SECS)


def _build_streamable_http_kwargs(
    server, headers: dict[str, str], env: dict[str, str], url: str | None = None
) -> StreamableHttpConnection:
    """
    Fred rationale: build explicit, inspectable kwargs for one server.
    Only supports streamable_http here (narrow & simple).
    """
    endpoint = url or server.url
    if not endpoint:
        raise ValueError(f"{server.name}: missing URL for streamable_http")

    # We only use streamable_http here. Only headers are relevant.
    kw: StreamableHttpConnection = {
        "transport": "streamable_http",
        "url": endpoint,
        "timeout": CONNECT_TIMEOUT_TD,  # adapter expects timedelta
        "sse_read_timeout": SSE_READ_TIMEOUT_TD,  # adapter expects timedelta
    }
    if headers:
        kw["headers"] = dict(headers)
    return kw


async def _cleanup_client_quiet(client: MultiServerMCPClient) -> None:
    """No-op cleanup for MultiServerMCPClient (no persistent contexts).

    Newer langchain-mcp-adapters does not expose an exit_stack or aclose on the
    client; sessions are opened and closed per-call. Kept for API parity.
    """
    logger.debug("[MCP] event=connection_cleanup outcome=skipped")


def _normalize_transport(transport: str | None) -> str:
    """Return a lower-case transport with a sensible default."""
    if not transport:
        return "streamable_http"
    return transport.lower()


def _build_stdio_kwargs(
    server: MCPServerConfiguration, _headers: dict[str, str], env: dict[str, str]
) -> Connection:
    """
    Build stdio transport kwargs.

    The langchain MCP adapter expects a command/args/env payload. We merge auth
    env with any server-specific env, allowing the server config to override.
    """
    if not server.command:
        raise ValueError(f"{server.name}: missing command for stdio transport")

    merged_env: dict[str, str] = {}
    if env:
        merged_env.update(env)
    if server.env:
        merged_env.update(server.env)

    conn: Connection = {
        "transport": "stdio",
        "command": server.command,
        "args": list(server.args or []),
    }
    if merged_env:
        conn["env"] = merged_env
    return conn


async def get_connected_mcp_client_for_agent(
    agent_id: str,
    mcp_servers: List[MCPServerConfiguration],
    runtime_context: RuntimeContext,
    *,
    tool_interceptors: list | None = None,
    credentials: OutboundCredentialProvider | None = None,
    # -----------------------------------------------
) -> Tuple[MultiServerMCPClient, List[BaseTool]]:
    """
    Creates and connects the MultiServerMCPClient using the token provided by
    `access_token_provider`. Supports `streamable_http` and `stdio` transports.

    Also returns the tools fetched per server during connection validation, so
    callers don't have to pay for a second `get_tools()` round trip against
    every server just to populate their toolkit (see mcp_runtime.py).
    """

    provider = resolve_credential_provider(
        explicit=credentials,
        person_token_getter=partial(_runtime_context_token, runtime_context),
    )
    confined = provider.delegated

    for s in mcp_servers:
        transport = _normalize_transport(s.transport)
        if transport not in SUPPORTED_TRANSPORTS:
            if confined:
                logger.info(
                    "[MCP] event=connection_init outcome=refused "
                    "reason=unsupported_transport"
                )
            else:
                logger.info(
                    "[MCP][%s] connect init: Unsupported transport '%s' found. "
                    "Supported transports: %s",
                    agent_id,
                    s.transport,
                    SUPPORTED_TRANSPORTS,
                )
            raise UnsupportedTransportError(
                f"Unsupported transport '{s.transport}'. Supported: {', '.join(SUPPORTED_TRANSPORTS)}"
            )

    # --- Ask the provider ONCE for this connection attempt ---
    # Flag off it answers with the person's bearer, flag on with the runtime's
    # own workload bearer plus the grant this run acts under.
    needs_credentials = any(
        _normalize_auth_mode(server.auth_mode) != AUTH_MODE_NO_TOKEN
        for server in mcp_servers
    )
    if needs_credentials:
        call_credentials = await provider.credentials()
    else:
        call_credentials = OutboundCredentials()
    # --------------------------------------------------

    if not call_credentials.authorization:
        if confined:
            logger.warning("[MCP] event=credential_resolution outcome=empty")
        else:
            logger.warning("MCP connect init: no outbound credential was supplied.")

    auth_label = _mask_auth_value(call_credentials.authorization)
    # 🟢 LOG 5: Auth status
    if confined:
        logger.info(
            "[MCP] event=credential_resolution outcome=completed auth=%s delegated=%s",
            auth_label,
            call_credentials.delegated,
        )
    else:
        logger.info(
            "[MCP] connect init: credential retrieved. Auth status: %s delegated=%s",
            auth_label,
            call_credentials.delegated,
        )
    # ----------------------------------------------------------------

    # Build connection map for the new client API
    connections: dict[str, Connection] = {}
    for server in mcp_servers:
        transport = _normalize_transport(server.transport)
        headers, env, url = _server_connection_auth(server, call_credentials, transport)
        try:
            if transport == "streamable_http":
                conn_cfg = _build_streamable_http_kwargs(server, headers, env, url)
            elif transport == "stdio":
                conn_cfg = _build_stdio_kwargs(server, headers, env)
            else:
                # Explicit guard for transports we list but do not yet wire
                raise UnsupportedTransportError(
                    f"Transport '{transport}' is not yet implemented."
                )
        except Exception as error:
            if confined:
                logger.warning(
                    "[MCP] event=connection_config outcome=failed "
                    "reason=invalid_configuration"
                )
            else:
                logger.warning(
                    "[MCP][%s] connect pre-fail for server=%s: Failed to build "
                    "connection config: %s",
                    agent_id,
                    server.id,
                    error,
                )
            raise
        connections[server.id] = conn_cfg

    client = MultiServerMCPClient(
        connections, tool_interceptors=tool_interceptors or []
    )

    # Validate connections by attempting to load tools per server. This is also
    # the ONLY tool-fetch round trip we make per server — the fetched tools are
    # returned to the caller so `MCPRuntime._run_lifecycle` doesn't need to call
    # `client.get_tools()` again across all servers right after this returns.
    exceptions: list[Exception] = []
    failure_messages: list[str] = []
    fetched_tools: list[BaseTool] = []
    for server in mcp_servers:
        conn_entry = connections.get(server.id) or {}
        transport = conn_entry.get("transport", "unknown")
        url_for_log = _loggable_url(conn_entry.get("url", "")) or conn_entry.get(
            "command", ""
        )
        auth_label = _mask_auth_value(
            (conn_entry.get("headers") or {}).get("Authorization")
        )
        start = time.perf_counter()
        try:
            if confined:
                logger.debug("[MCP] event=connection_validation outcome=started")
            else:
                logger.debug(
                    "[MCP][%s] validate name=%s transport=%s endpoint=%s auth=%s",
                    agent_id,
                    server.id,
                    transport,
                    url_for_log,
                    auth_label,
                )
            tools = await client.get_tools(server_name=server.id)
            duration_ms = (time.perf_counter() - start) * 1000
            if confined:
                logger.info("[MCP] event=connection_validation outcome=succeeded")
            else:
                logger.info(
                    "[MCP][%s] connected name=%s transport=%s endpoint=%s "
                    "tools=%d dur_ms=%.0f",
                    agent_id,
                    server.id,
                    transport,
                    url_for_log,
                    len(tools),
                    duration_ms,
                )
            # Tag each tool with its originating server id so the ReAct prompt
            # can group the tool listing later (#2455). `_get_or_connect_mcp_client`
            # caches and reuses this exact tool-object list across concurrent
            # requests (see its docstring), so tagging must be non-mutating —
            # `model_copy` returns a new object, never touching the cached one.
            tagged_tools = [
                tool.model_copy(
                    update={
                        "metadata": {
                            **(tool.metadata or {}),
                            MCP_SERVER_ID_METADATA_KEY: server.id,
                        }
                    }
                )
                for tool in tools
            ]
            fetched_tools.extend(tagged_tools)
        except Exception as e:
            refusal = _refusal_status(e) if call_credentials.delegated else None
            if refusal is not None:
                # The receiver refused this run's authority. Nothing upstream is
                # logged or retried: both the endpoint and the failure's own text
                # carry the grant, and a second attempt asks for what was denied.
                logger.error(
                    "[MCP] event=connection_validation outcome=stopped "
                    "reason=authority_refused status=%d",
                    refusal,
                )
                raise AuthorityLostError() from None
            duration_ms = (time.perf_counter() - start) * 1000
            if confined:
                logger.warning(
                    "[MCP] event=connection_validation outcome=failed "
                    "reason=connection_error"
                )
            else:
                logger.warning(
                    "[MCP][%s] connect fail name=%s url=%s err=%s dur_ms=%.0f: %s",
                    agent_id,
                    server.id,
                    url_for_log,
                    e.__class__.__name__,
                    duration_ms,
                    scrub_grant_text(str(e).split("\n")[0]),
                )
                failure_messages.append(
                    f"{server.id} ({transport}): {url_for_log}): "
                    f"{e.__class__.__name__}: "
                    f"{scrub_grant_text(str(e).splitlines()[0])}\n"
                )
            exceptions.extend(getattr(e, "exceptions", [e]))

    if exceptions:
        if confined:
            logger.error(
                "[MCP] event=connection_summary outcome=failed reason=connection_error"
            )
            reason = "Some MCP connections failed. Check the configured tool servers."
        else:
            logger.error(
                "MCP summary: %d server(s) failed to connect.", len(exceptions)
            )
            for index, exc in enumerate(exceptions, 1):
                logger.error(
                    "  [%d] %s: %s",
                    index,
                    exc.__class__.__name__,
                    scrub_grant_text(str(exc)),
                )
            reason = (
                "Some MCP connections failed.\nDetails:\n"
                + "; ".join(failure_messages)
                + "Ensure the matching Knowledge Flow controllers are enabled "
                "or disable the MCP server in Agentic configuration."
            )
            logger.error("[MCP][%s] connection summary: %s", agent_id, reason)
        # Nothing to cleanup on the client instance
        raise MCPConnectionError(reason, exceptions)

    if confined:
        logger.debug("[MCP] event=connection_summary outcome=succeeded")
    else:
        logger.debug(
            "[MCP][%s] summary: all servers validated, total tools=%d",
            agent_id,
            len(fetched_tools),
        )
    return client, fetched_tools

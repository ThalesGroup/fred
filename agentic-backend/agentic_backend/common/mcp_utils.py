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
- Returns a connected `MultiServerMCPClient`.
- Raises `ExceptionGroup` if **any** server fails to connect.

"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import Connection, StreamableHttpConnection

from agentic_backend.common.error import UnsupportedTransportError
from agentic_backend.core.agents.agent_spec import MCPServerConfiguration
from agentic_backend.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)

# ✅ Only allow transports that Fred knows how to configure safely.
SUPPORTED_TRANSPORTS = ["sse", "stdio", "streamable_http", "websocket"]


class MCPConnectionError(Exception):
    """Raised when one or more MCP servers fail to connect."""

    def __init__(self, message, exceptions):
        super().__init__(message)
        self.exceptions = exceptions
        self.reason = message


def _mask_auth_value(v: str | None) -> str:
    """Return a non-sensitive label for Authorization header values."""
    if not v:
        return "none"
    if v.lower().startswith("bearer "):
        # Always mask the bulk of the token
        return "present:Bearer " + v[7:15] + "…"
    return "present"


def _auth_headers(access_token: str | None) -> Dict[str, str]:
    """Build HTTP Authorization headers using the provided access token.

    If the token is missing, returns an empty dict (connection will fail 401).
    """
    if access_token:
        return {"Authorization": f"Bearer {access_token}"}
    return {}


def _auth_stdio_env(access_token: str | None) -> Dict[str, str]:
    """Build env vars used to pass auth to stdio transports.

    Mirrors the Authorization header as environment variables.
    """
    hdrs = _auth_headers(access_token)
    if not hdrs:
        return {}
    val = hdrs["Authorization"]
    return {"MCP_AUTHORIZATION": val, "AUTHORIZATION": val}


# --- small, clear constants (Fred rationale: fast-fail, let retry loop recover) ---
CONNECT_TIMEOUT_SECS = 5.0
SSE_READ_TIMEOUT_SECS = 30.0
CONNECT_TIMEOUT_TD = timedelta(seconds=CONNECT_TIMEOUT_SECS)
SSE_READ_TIMEOUT_TD = timedelta(seconds=SSE_READ_TIMEOUT_SECS)
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_BASE_DELAY_SECS = 2.0
DEFAULT_MAX_DELAY_SECS = 10.0


def _safe_int_env(name: str, default: int) -> int:
    """Read an env var as int while guarding against invalid values."""
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(1, value)


def _safe_float_env(name: str, default: float, minimum: float = 0.0) -> float:
    """Read an env var as float while guarding against invalid values."""
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


CONNECT_MAX_ATTEMPTS = _safe_int_env(
    "MCP_CONNECT_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS
)
CONNECT_RETRY_BASE_DELAY_SECS = _safe_float_env(
    "MCP_CONNECT_RETRY_BASE_SECONDS", DEFAULT_BASE_DELAY_SECS
)
CONNECT_RETRY_MAX_DELAY_SECS = max(
    CONNECT_RETRY_BASE_DELAY_SECS,
    _safe_float_env(
        "MCP_CONNECT_MAX_DELAY_SECONDS", DEFAULT_MAX_DELAY_SECS, DEFAULT_BASE_DELAY_SECS
    ),
)


def _retry_delay(attempt_number: int) -> float:
    """Compute exponential backoff delay for the given attempt number (1-based)."""
    if CONNECT_RETRY_BASE_DELAY_SECS <= 0:
        return 0.0
    delay = CONNECT_RETRY_BASE_DELAY_SECS * (2 ** max(0, attempt_number - 1))
    return min(delay, CONNECT_RETRY_MAX_DELAY_SECS)


def _build_streamable_http_kwargs(
    server, headers: dict[str, str], env: dict[str, str]
) -> StreamableHttpConnection:
    """
    Fred rationale: build explicit, inspectable kwargs for one server.
    Only supports streamable_http here (narrow & simple).
    """
    if not server.url:
        raise ValueError(f"{server.name}: missing URL for streamable_http")

    # We only use streamable_http here. Only headers are relevant.
    kw: StreamableHttpConnection = {
        "transport": "streamable_http",
        "url": server.url,
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
    logger.debug("[MCP] _cleanup_client_quiet: nothing to close on client.")


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
    agent_name: str,
    mcp_servers: List[MCPServerConfiguration],
    runtime_context: RuntimeContext,
    optional_server_ids: Optional[Set[str]] = None,
    # -----------------------------------------------
) -> Tuple[MultiServerMCPClient, List[Any]]:
    """
    Creates and connects the MultiServerMCPClient using the token provided by
    `access_token_provider`. Supports `streamable_http` and `stdio` transports.
    """

    for s in mcp_servers:
        transport = _normalize_transport(s.transport)
        if transport not in SUPPORTED_TRANSPORTS:
            logger.info(
                "[MCP][%s] connect init: Unsupported transport '%s' found. Supported transports: %s",
                agent_name,
                s.transport,
                SUPPORTED_TRANSPORTS,
            )
            raise UnsupportedTransportError(
                f"Unsupported transport '{s.transport}'. Supported: {', '.join(SUPPORTED_TRANSPORTS)}"
            )

    # --- Fetch the user token ONCE from the context ---
    # This token is the candidate for all OAuth connections.
    access_token = runtime_context.access_token
    # --------------------------------------------------

    if not access_token:
        # 🟢 LOG 4: Missing token failure
        logger.warning(
            "MCP connect init: Access token provider did not supply a token."
        )

    # Build auth once for all servers
    base_headers = _auth_headers(access_token)
    auth_label = _mask_auth_value(base_headers.get("Authorization"))
    # 🟢 LOG 5: Auth status
    logger.info(
        "[MCP] connect init: Token retrieved successfully. Auth status: %s", auth_label
    )
    # ----------------------------------------------------------------

    # Build connection map for the new client API
    connections: dict[str, Connection] = {}
    for server in mcp_servers:
        auth_mode = server.auth_mode
        should_send_client_token = auth_mode != "no_token"
        token_to_use = access_token if should_send_client_token else None
        if should_send_client_token and not token_to_use:
            logger.warning(
                "[MCP] server=%s: Auth mode is '%s', but no user token is available. Connection may fail 401.",
                server.id,
                auth_mode,
            )
        headers = _auth_headers(token_to_use)
        env = _auth_stdio_env(token_to_use)
        transport = _normalize_transport(server.transport)
        try:
            if transport == "streamable_http":
                conn_cfg = _build_streamable_http_kwargs(server, headers, env)
            elif transport == "stdio":
                conn_cfg = _build_stdio_kwargs(server, headers, env)
            else:
                # Explicit guard for transports we list but do not yet wire
                raise UnsupportedTransportError(
                    f"Transport '{transport}' is not yet implemented."
                )
        except Exception as e:
            logger.warning(
                "[MCP][%s] connect pre-fail for server=%s: Failed to build connection config: %s",
                agent_name,
                server.id,
                e,
            )
            raise
        connections[server.id] = conn_cfg

    client = MultiServerMCPClient(connections)

    # Validate connections by attempting to load tools per server
    exceptions: list[Exception] = []
    failure_messages: list[str] = []
    optional_failures: list[str] = []
    prefetched_tools: List[Any] = []
    total_tools = 0
    optional_server_ids = optional_server_ids or set()
    for server in mcp_servers:
        conn_entry = connections.get(server.id) or {}
        transport = conn_entry.get("transport", "unknown")
        url_for_log = conn_entry.get("url", "") or conn_entry.get("command", "")
        auth_label = _mask_auth_value(
            (conn_entry.get("headers") or {}).get("Authorization")
        )
        is_optional = server.id in optional_server_ids
        last_error: Optional[BaseException] = None
        for attempt in range(1, CONNECT_MAX_ATTEMPTS + 1):
            start = time.perf_counter()
            try:
                logger.debug(
                    "[MCP][%s] validate name=%s transport=%s endpoint=%s auth=%s attempt=%d/%d",
                    agent_name,
                    server.id,
                    transport,
                    url_for_log,
                    auth_label,
                    attempt,
                    CONNECT_MAX_ATTEMPTS,
                )
                tools = await client.get_tools(server_name=server.id)
                # Tag tools with their origin server for downstream telemetry/UI.
                for t in tools or []:
                    try:
                        setattr(t, "_mcp_server_id", server.id)
                        setattr(t, "_mcp_server_name", server.name or server.id)
                    except Exception:
                        logger.debug("[MCP][%s] Could not tag tool origin for %s", agent_name, server.id)
                dur_ms = (time.perf_counter() - start) * 1000
                logger.info(
                    "[MCP][%s] connected name=%s transport=%s endpoint=%s tools=%d dur_ms=%.0f attempt=%d/%d",
                    agent_name,
                    server.id,
                    transport,
                    url_for_log,
                    len(tools),
                    dur_ms,
                    attempt,
                    CONNECT_MAX_ATTEMPTS,
                )
                total_tools += len(tools)
                if tools:
                    prefetched_tools.extend(tools)
                last_error = None
                break
            except BaseException as e:
                last_error = e
                dur_ms = (time.perf_counter() - start) * 1000
                logger.warning(
                    "[MCP][%s] connect fail name=%s url=%s err=%s dur_ms=%.0f attempt=%d/%d: %s",
                    agent_name,
                    server.id,
                    url_for_log,
                    e.__class__.__name__,
                    dur_ms,
                    attempt,
                    CONNECT_MAX_ATTEMPTS,
                    str(e).split("\n")[0],
                )
                if attempt < CONNECT_MAX_ATTEMPTS:
                    delay = _retry_delay(attempt)
                    if delay > 0:
                        logger.info(
                            "[MCP][%s] retrying name=%s after %.1fs (attempt %d/%d).",
                            agent_name,
                            server.id,
                            delay,
                            attempt + 1,
                            CONNECT_MAX_ATTEMPTS,
                        )
                        await asyncio.sleep(delay)
                else:
                    break

        if last_error:
            failure_entry = (
                f"{server.id} ({transport}): {url_for_log}): "
                f"{last_error.__class__.__name__}: {str(last_error).splitlines()[0]}\n"
            )
            if is_optional:
                optional_failures.append(failure_entry)
                continue
            exceptions.extend(getattr(last_error, "exceptions", [last_error]))
            failure_messages.append(failure_entry)

    if exceptions:
        logger.error("MCP summary: %d server(s) failed to connect.", len(exceptions))
        for i, exc in enumerate(exceptions, 1):
            logger.error("  [%d] %s: %s", i, exc.__class__.__name__, str(exc))
        reason = (
            "Some MCP connections failed.\nDetails:\n"
            + "; ".join(failure_messages)
            + "Ensure the matching Knowledge Flow controllers are enabled "
            "or disable the MCP server in Agentic configuration."
        )
        logger.error("[MCP][%s] connection summary: %s", agent_name, reason)
        # Nothing to cleanup on the client instance
        raise MCPConnectionError(reason, exceptions)

    if optional_failures:
        logger.warning(
            "[MCP][%s] optional servers unavailable: %s",
            agent_name,
            "; ".join(optional_failures),
        )

    logger.debug(
        "[MCP][%s] summary: all servers validated, total tools=%d",
        agent_name,
        total_tools,
    )
    return client, prefetched_tools

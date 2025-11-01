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

import logging
import time
from datetime import timedelta
from typing import Any, Dict, List

from langchain_mcp_adapters.client import MultiServerMCPClient

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


def _build_streamable_http_kwargs(
    server, headers: dict[str, str], env: dict[str, str]
) -> dict[str, Any]:
    """
    Fred rationale: build explicit, inspectable kwargs for one server.
    Only supports streamable_http here (narrow & simple).
    """
    if not server.url:
        raise ValueError(f"{server.name}: missing URL for streamable_http")

    # We only use streamable_http, so only headers are relevant here.
    # The `env` parameter is included for completeness for other transports.
    kw: dict[str, Any] = {
        "server_name": server.name,
        "transport": "streamable_http",
        "url": server.url,
        "timeout": CONNECT_TIMEOUT_TD,  # adapter expects timedelta
        "sse_read_timeout": SSE_READ_TIMEOUT_TD,  # adapter expects timedelta
    }
    if headers:
        kw["headers"] = dict(headers)
    if env:
        kw["env"] = dict(env)
    return kw


async def _cleanup_client_quiet(client: MultiServerMCPClient) -> None:
    try:
        # 🟢 LOG 1: Attempting client cleanup
        logger.info(
            "[MCP] _cleanup_client_quiet: attempting to close client via exit_stack."
        )
        await client.exit_stack.aclose()
        # 🟢 LOG 1: Client cleanup complete
        logger.info("[MCP] _cleanup_client_quiet: client successfully closed.")
    except BaseException:
        # 🟢 LOG 1: Client cleanup failed
        logger.info("[MCP] _cleanup_client_quiet: client close ignored.", exc_info=True)


async def get_connected_mcp_client_for_agent(
    agent_name: str,
    mcp_servers: List[MCPServerConfiguration],
    runtime_context: RuntimeContext,
    # -----------------------------------------------
) -> MultiServerMCPClient:
    """
    Streamable HTTP ONLY. Creates and connects the MultiServerMCPClient using
    the token provided by `access_token_provider`.
    """

    # Enforce streamable_http-only for this slim version
    for s in mcp_servers:
        if s.transport != "streamable_http":
            # 🟢 LOG 3: Unsupported transport failure
            logger.info(
                "[MCP][%s] connect init: Unsupported transport '%s' found. Only 'streamable_http' is allowed.",
                agent_name,
                s.transport,
            )
            raise UnsupportedTransportError(
                "This build supports only 'streamable_http'."
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
    stdio_env = _auth_stdio_env(access_token)
    auth_label = _mask_auth_value(base_headers.get("Authorization"))
    # 🟢 LOG 5: Auth status
    logger.info(
        "[MCP] connect init: Token retrieved successfully. Auth status: %s", auth_label
    )
    # ----------------------------------------------------------------

    client = MultiServerMCPClient()
    exceptions: list[Exception] = []

    for server in mcp_servers:
        auth_mode = server.auth_mode
        should_send_client_token = auth_mode != "no_token"
        token_to_use = None
        if should_send_client_token:
            # If the server requires a user token, use the fetched access_token (which might still be None).
            token_to_use = access_token
        # Log a warning if a server requires a token, but none is available.
        if should_send_client_token and not token_to_use:
            logger.warning(
                "[MCP] server=%s: Auth mode is '%s', but no user token is available. Connection may fail 401.",
                server.name,
                auth_mode,
            )

        # Build AUTH for this specific connection
        base_headers = _auth_headers(token_to_use)
        stdio_env = _auth_stdio_env(token_to_use)
        auth_label = _mask_auth_value(base_headers.get("Authorization"))

        # 🟢 LOG A: Per-server auth status
        logger.info(
            "[MCP] connect server=%s: Auth mode='%s', Auth status: %s (Client token used: %s)",
            server.name,
            auth_mode,
            auth_label,
            "Yes" if token_to_use else "No",
        )
        try:
            connect_kwargs = _build_streamable_http_kwargs(
                server, base_headers, stdio_env
            )
        except Exception as e:
            # 🟢 LOG 6: Kwargs build failure
            logger.warning(
                "[MCP][%s] connect pre-fail for server=%s: Failed to build connection kwargs: %s",
                agent_name,
                server.name,
                e,
            )
            exceptions.append(e)
            continue

        url_for_log = connect_kwargs.get("url", "")
        start = time.perf_counter()

        # ---- first (and only) attempt --------------------------------------
        try:
            # 🟢 LOG 7: Connection attempt start
            logger.debug(
                "[MCP][%s] connect attempt name=%s transport=streamable_http url=%s auth=%s timeout=%.0fs",
                agent_name,
                server.name,
                url_for_log,
                auth_label,
                CONNECT_TIMEOUT_SECS,
            )
            await client.connect_to_server(**connect_kwargs)

            # This log is redundant but kept for clarity/flow inspection:
            logger.debug(
                "[MCP][%s] connect established name=%s transport=streamable_http url=%s auth=%s",
                agent_name,
                server.name,
                url_for_log,
                auth_label,
            )
            client.__dict__.setdefault("_conn_specs", {})[server.name] = dict(
                connect_kwargs
            )

            dur_ms = (time.perf_counter() - start) * 1000
            tools = client.server_name_to_tools.get(server.name, [])
            # 🟢 LOG 8: Connection success
            logger.info(
                "[MCP][%s] connected name=%s transport=streamable_http url=%s tools=%d dur_ms=%.0f",
                agent_name,
                server.name,
                url_for_log,
                len(tools),
                dur_ms,
            )
            continue  # Success

        except BaseException as e1:
            dur_ms = (time.perf_counter() - start) * 1000
            # 🟢 LOG 9: Connection failure
            logger.warning(
                "[MCP][%s] connect fail name=%s url=%s err=%s dur_ms=%.0f: %s",
                agent_name,
                server.name,
                url_for_log,
                e1.__class__.__name__,
                dur_ms,
                str(e1).split("\n")[
                    0
                ],  # Only take the first line of the error message for the summary log
            )
            # Since we removed the auth retry logic, any failure is final for this server
            exceptions.extend(getattr(e1, "exceptions", [e1]))
            continue

    # ---- finalize ---------------------------------------------------------
    if exceptions:
        # 🟢 LOG 10: Summary failure
        logger.error("MCP summary: %d server(s) failed to connect.", len(exceptions))
        for i, exc in enumerate(exceptions, 1):
            logger.error("  [%d] %s: %s", i, exc.__class__.__name__, str(exc))
        await _cleanup_client_quiet(client)
        raise MCPConnectionError("Some MCP connections failed", exceptions)

    total_tools = sum(len(v) for v in client.server_name_to_tools.values())
    # 🟢 LOG 11: Summary success
    logger.debug(
        "[MCP][%s] summary: all servers connected, total tools=%d",
        agent_name,
        total_tools,
    )
    return client

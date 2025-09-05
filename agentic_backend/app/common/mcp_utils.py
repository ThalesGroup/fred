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
for a given agent, with outbound auth and transport-specific hardening.

Audience
--------
Framework developers and maintainers. Application agents should **not**
import this directly—use `MCPRuntime` which wraps it and handles refresh/rebind.

Why this exists
---------------
- Agents may declare one or more MCP servers (OpenSearch ops, KPI services, etc.).
- Each server can use a different transport (`stdio`, `sse`, `streamable_http`, `websocket`).
- Outbound auth must be injected consistently (HTTP headers vs. env for stdio).
- Auth can expire: we *retry once* on auth failures after refreshing the token.
- We want strong, **safe** logging (no secret leakage) and helpful diagnostics.

Contract
--------
- Returns a connected `MultiServerMCPClient` with all configured servers attached.
- Raises `ExceptionGroup` if **any** server fails after retries (so devs see the full set).
- Only allows transports we know how to configure; misconfig leads to
  `UnsupportedTransportError`.

Notes on logging
----------------
- We mask auth headers in logs (`present:Bearer <first8>…`).
- We record which transports and URLs were used (with trailing slash normalization
  where required).
- On failure we log per-server errors and summarize.

Used by
-------
`app.common.mcp_runtime.MCPRuntime`:
- `init()` → calls `get_mcp_client_for_agent` once.
- `refresh()` → calls it again and swaps the client/toolkit.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from builtins import ExceptionGroup
import time
from typing import Any, Dict, List

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.common.structures import AgentSettings
from app.common.error import UnsupportedTransportError
from app.application_context import get_app_context
from app.core.agents.runtime_context import get_user_token, RuntimeContextProvider

logger = logging.getLogger(__name__)

# ✅ Only allow transports that Fred knows how to configure safely.
SUPPORTED_TRANSPORTS = ["sse", "stdio", "streamable_http", "websocket"]


def _mask_auth_value(v: str | None) -> str:
    """Return a non-sensitive label for Authorization header values.

    - If value is falsy → "none"
    - If value starts with "Bearer " → "present:Bearer xxxxxxxx…"
    - Otherwise → "present"

    This keeps logs useful without leaking secrets.
    """
    if not v:
        return "none"
    if v.lower().startswith("bearer "):
        return "present:Bearer " + v[7:15] + "…"
    return "present"


def _auth_headers(context_provider: RuntimeContextProvider | None = None) -> Dict[str, str]:
    """Build HTTP Authorization headers for outbound MCP requests.

    This function supports OAuth2 Token Exchange to preserve user identity:
    - If user context with token is provided, exchanges the user token for a service token
    - Otherwise falls back to standard client credentials service token
    - Returns {"Authorization": "Bearer <token>"}

    Args:
        context_provider: Optional function to get the runtime context with user token.

    Returns:
        Dict of headers suitable for HTTP transports (SSE, streamable_http, websocket).
    """
    headers = {}
    
    # Try token exchange first if user context is available
    if context_provider:
        try:
            context = context_provider()
            user_token = get_user_token(context)
            if user_token:
                # Get token exchange provider from app context
                oa = get_app_context().get_outbound_auth()
                exchanger = getattr(oa, "_token_exchanger", None)
                if exchanger:
                    try:
                        exchanged_token = exchanger.exchange_token(user_token)
                        headers["Authorization"] = f"Bearer {exchanged_token}"
                        logger.debug("Using token exchange for user identity preservation")
                        return headers
                    except Exception as e:
                        logger.warning("Token exchange failed, falling back to service token: %s", e)
        except Exception:
            # Don't fail if context provider fails, just skip token exchange
            pass
    
    # Fallback to standard service account token
    oa = get_app_context().get_outbound_auth()
    provider = getattr(oa.auth, "_provider", None)  # internal by design
    if callable(provider):
        try:
            token = provider()
        except Exception:
            token = None
        if token:
            headers["Authorization"] = f"Bearer {token}"
            logger.debug("Using standard service account token")
    
    return headers


def _auth_stdio_env(context_provider: RuntimeContextProvider | None = None) -> Dict[str, str]:
    """Build env vars used to pass auth to stdio transports.

    stdio servers don't see HTTP headers, so we mirror the Authorization header
    as environment variables to maximize compatibility:

    - MCP_AUTHORIZATION
    - AUTHORIZATION

    Args:
        context_provider: Optional function to get the runtime context with user token.

    Returns:
        Environment variable mapping (possibly empty).
    """
    hdrs = _auth_headers(context_provider)
    env_vars = {}
    
    # Add authorization token (already includes token exchange if applicable)
    if "Authorization" in hdrs:
        auth_val = hdrs["Authorization"]
        env_vars["MCP_AUTHORIZATION"] = auth_val
        env_vars["AUTHORIZATION"] = auth_val
    
    return env_vars


def _is_auth_error(exc: Exception) -> bool:
    """Heuristic to detect auth failures from adapter exceptions.

    Some adapter layers surface HTTP auth errors without structured status codes.
    We fallback to message inspection.

    Returns:
        True if the exception likely indicates a 401/Unauthorized, else False.
    """
    msg = str(exc)
    return "401" in msg or "Unauthorized" in msg


async def get_mcp_client_for_agent(
    agent_settings: AgentSettings,
    context_provider: RuntimeContextProvider | None = None,
) -> MultiServerMCPClient:
    """Create and connect a `MultiServerMCPClient` for the given agent.

    Behavior
    --------
    - Iterates all `agent_settings.mcp_servers`.
    - Validates the transport is supported (`SUPPORTED_TRANSPORTS`).
    - Injects outbound auth (headers for HTTP-like, env for stdio).
    - For HTTP-like transports, normalizes the URL (adds trailing slash where needed).
    - Connects to each server and records connection specs into the client for diagnostics.
    - On auth failure, refreshes token once (if the app provides a `refresh()`), then retries.
    - Aggregates failures and raises `ExceptionGroup` if any server couldn’t be connected.

    Logging
    -------
    - Logs per-server success/failure with duration and masked auth state.
    - Logs a summary of total tools discovered across all sessions.

    Args:
        agent_settings: Agent configuration containing one or more MCP server specs.
        context_provider: Optional function to get the runtime context with user info.

    Returns:
        A connected `MultiServerMCPClient` with all declared servers attached.

    Raises:
        ValueError: if no MCP servers are configured for the agent.
        UnsupportedTransportError: if an MCP server specifies an unknown transport.
        ExceptionGroup: if one or more servers failed to connect (after retry).
    """
    if not agent_settings.mcp_servers:
        raise ValueError("No MCP server configuration")

    ctx = get_app_context()
    oa = ctx.get_outbound_auth()

    client = MultiServerMCPClient()
    exceptions: List[Exception] = []

    # Build base auth once to avoid multiple provider calls.
    base_headers = _auth_headers(context_provider)
    base_stdio_env = _auth_stdio_env(context_provider)
    auth_label = _mask_auth_value(base_headers.get("Authorization"))

    for server in agent_settings.mcp_servers:
        if server.transport not in SUPPORTED_TRANSPORTS:
            # Fail fast on misconfiguration.
            raise UnsupportedTransportError(
                f"Unsupported transport: {server.transport}"
            )

        # Build the connection spec with explicit fields so it’s easy to log/inspect later.
        connect_kwargs: Dict[str, Any] = {
            "server_name": server.name,
            "url": server.url,
            "transport": server.transport,
            "command": server.command,
            "args": server.args,
            "env": server.env,
            "sse_read_timeout": server.sse_read_timeout,
        }

        # Inject auth and normalize per-transport.
        if server.transport in ("sse", "streamable_http", "websocket"):
            if server.url:
                url = server.url
                connect_kwargs["url"] = url
            if base_headers:
                connect_kwargs["headers"] = dict(base_headers)
            # The streamable_http adapter expects a timedelta for SSE read timeouts.
            if server.transport == "streamable_http" and isinstance(
                server.sse_read_timeout, (int, float)
            ):
                connect_kwargs["sse_read_timeout"] = timedelta(
                    seconds=float(server.sse_read_timeout)
                )
            else:
                connect_kwargs["sse_read_timeout"] = server.sse_read_timeout

        elif server.transport == "stdio":
            merged_env: Dict[str, str] = dict(server.env or {})
            merged_env.update(base_stdio_env)
            connect_kwargs["env"] = merged_env

        url_for_log = connect_kwargs.get("url", "")
        start = time.perf_counter()

        # --- First attempt ---------------------------------------------------
        try:
            await client.connect_to_server(**connect_kwargs)
            # Keep a copy of the exact spec used (helps a ton in support).
            client.__dict__.setdefault("_conn_specs", {})[server.name] = dict(
                connect_kwargs
            )

            dur_ms = (time.perf_counter() - start) * 1000
            tools = client.server_name_to_tools.get(server.name, [])
            logger.info(
                "MCP post-connect: client=%s sessions=%s tools=%d",
                f"0x{id(client):x}",
                list(client.sessions.keys()),
                len(tools),
            )
            logger.info(
                "MCP connect ok name=%s transport=%s url=%s auth=%s tools=%d dur_ms=%.0f",
                server.name,
                server.transport,
                url_for_log,
                auth_label,
                len(tools),
                dur_ms,
            )
            continue

        except Exception as e1:
            dur_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "MCP connect fail name=%s transport=%s url=%s auth=%s dur_ms=%.0f err=%s",
                server.name,
                server.transport,
                url_for_log,
                auth_label,
                dur_ms,
                e1.__class__.__name__,
            )

            if not _is_auth_error(e1):
                # Non-auth errors → collect and move on (we’ll raise at the end).
                exceptions.extend(getattr(e1, "exceptions", [e1]))
                continue

            # --- Auth retry once --------------------------------------------
            logger.info(
                "MCP connect 401 → refreshing token and retrying once (name=%s).",
                server.name,
            )

            refresh_fn = getattr(oa, "refresh", None)
            if callable(refresh_fn):
                try:
                    refresh_fn()
                except Exception as ref_exc:
                    logger.info(
                        "MCP token refresh failed quickly name=%s err=%s",
                        server.name,
                        type(ref_exc).__name__,
                    )

            fresh_headers = _auth_headers(context_provider)
            fresh_auth_label = _mask_auth_value(fresh_headers.get("Authorization"))

            if server.transport in ("sse", "streamable_http", "websocket"):
                if fresh_headers:
                    connect_kwargs["headers"] = dict(fresh_headers)
                else:
                    connect_kwargs.pop("headers", None)
            elif server.transport == "stdio":
                merged_env = dict(server.env or {})
                merged_env.update(_auth_stdio_env(context_provider))
                connect_kwargs["env"] = merged_env

            start2 = time.perf_counter()
            try:
                await client.connect_to_server(**connect_kwargs)
                client.__dict__.setdefault("_conn_specs", {})[server.name] = dict(
                    connect_kwargs
                )

                dur2_ms = (time.perf_counter() - start2) * 1000
                tools = client.server_name_to_tools.get(server.name, [])
                logger.info(
                    "MCP after-refresh: client=%s sessions=%s tools=%d",
                    f"0x{id(client):x}",
                    list(client.sessions.keys()),
                    len(tools),
                )
                logger.info(
                    "MCP connect ok (after refresh) name=%s transport=%s url=%s auth=%s tools=%d dur_ms=%.0f",
                    server.name,
                    server.transport,
                    url_for_log,
                    fresh_auth_label,
                    len(tools),
                    dur2_ms,
                )
                continue

            except Exception as e2:
                dur2_ms = (time.perf_counter() - start2) * 1000
                logger.info(
                    "MCP connect fail (after refresh) name=%s transport=%s url=%s auth=%s dur_ms=%.0f err=%s",
                    server.name,
                    server.transport,
                    url_for_log,
                    fresh_auth_label,
                    dur2_ms,
                    e2.__class__.__name__,
                )
                exceptions.extend(getattr(e2, "exceptions", [e2]))
                continue

    # If any server failed, raise them all together so devs see the full picture.
    if exceptions:
        logger.info("MCP summary: %d server(s) failed to connect.", len(exceptions))
        for i, exc in enumerate(exceptions, 1):
            logger.info("  [%d] %s: %s", i, exc.__class__.__name__, str(exc))
        raise ExceptionGroup("Some MCP connections failed", exceptions)

    total_tools = sum(len(v) for v in client.server_name_to_tools.values())
    logger.info("MCP summary: all servers connected, total tools=%d", total_tools)

    return client

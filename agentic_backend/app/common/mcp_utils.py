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

from __future__ import annotations

from datetime import timedelta
import logging
from builtins import ExceptionGroup
import time
import copy
from typing import Any, Dict, List
from urllib.parse import urlsplit, urlunsplit

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from app.common.structures import AgentSettings
from app.common.error import UnsupportedTransportError
from app.application_context import get_app_context

logger = logging.getLogger(__name__)

# ✅ Only allow transports that Fred knows how to handle.
#    This prevents silent misconfigurations where a developer
#    sets "grpc" or something unsupported in configuration.yaml.
SUPPORTED_TRANSPORTS = ["sse", "stdio", "streamable_http", "websocket"]

def _ensure_trailing_slash(url: str) -> str:
    """Hardening: MCP HTTP servers expect a base path ending with '/'."""
    if not url:
        return url
    parts = list(urlsplit(url))
    if not parts[2].endswith("/"):
        parts[2] += "/"
    return urlunsplit(parts)

def _mask_auth_value(v: str | None) -> str:
    """Never log secrets; show quick clue for ops."""
    if not v:
        return "none"
    if v.lower().startswith("bearer "):
        # Show first 8 chars after "Bearer "
        return "present:Bearer " + v[7:15] + "…"
    return "present"

def _auth_headers() -> Dict[str, str]:
    """
    Build Authorization headers for outbound MCP requests.

    Fred’s outbound auth system may provide a token provider (callable).
    This allows us to forward the current user/session’s security context
    when connecting to external MCP servers.

    Returns an empty dict if no provider is configured or token fails.
    """
    oa = get_app_context().get_outbound_auth()
    provider = getattr(oa.auth, "_provider", None)
    if callable(provider):
        try:
            token = provider()
        except Exception:
            return {}
        if token:
            return {"Authorization": f"Bearer {token}"}
    return {}


def _auth_stdio_env() -> Dict[str, str]:
    """
    For stdio-based MCP servers we cannot send HTTP headers.
    Instead we inject the same auth token as an environment variable.

    Two keys are set to maximize compatibility with different server implementations:
    - MCP_AUTHORIZATION
    - AUTHORIZATION
    """
    hdrs = _auth_headers()
    if not hdrs:
        return {}
    val = hdrs["Authorization"]
    return {"MCP_AUTHORIZATION": val, "AUTHORIZATION": val}

def _is_auth_error(exc: Exception) -> bool:
    """Heuristic: adapter errors may not expose status; check message."""
    msg = str(exc)
    return "401" in msg or "Unauthorized" in msg

async def ensure_mcp_sessions_alive(client) -> None:
    """
    Verify each MCP session. On 401 (expired bearer), refresh and reconnect that server
    with fresh Authorization (HTTP transports) or refreshed env (stdio).
    """
    conn_specs: Dict[str, Dict[str, Any]] = getattr(client, "_conn_specs", {})

    for name, session in list(client.sessions.items()):
        try:
            # Cheap ping that exercises auth/transport
            await load_mcp_tools(session)
        except Exception as e:
            if not _is_auth_error(e):
                logger.info("MCP health: non-auth error on %s: %s", name, e.__class__.__name__)
                continue

            logger.info("MCP health: 401 on %s — refreshing token and reconnecting.", name)

            # 1) refresh token
            oa = get_app_context().get_outbound_auth()
            _refresh = getattr(oa, "refresh", None)
            if callable(_refresh):
                try:
                    _refresh()
                except Exception as ref_exc:
                    logger.info("MCP token refresh failed quickly name=%s err=%s", name, type(ref_exc).__name__)

            # 2) rebuild headers/env *based on transport* and reconnect
            spec = copy.deepcopy(conn_specs.get(name, {}))
            if not spec:
                logger.info("MCP health: no saved spec for %s, skipping reconnect.", name)
                continue

            fresh_headers = _auth_headers()
            transport = spec.get("transport")

            if transport in ("sse", "streamable_http", "websocket"):
                # Always set fresh headers on reconnect (even if they weren't present initially)
                spec["headers"] = dict(fresh_headers) if fresh_headers else None
            elif transport == "stdio":
                # Merge fresh token into env for stdio transports
                merged_env: Dict[str, str] = dict(spec.get("env") or {})
                merged_env.update(_auth_stdio_env())
                spec["env"] = merged_env

            try:
                await client.connect_to_server(**spec)
                # Persist the effective spec so subsequent reconnects use it
                client.__dict__.setdefault("_conn_specs", {})[name] = dict(spec)
                logger.info("MCP health: reconnected %s after refresh.", name)
            except Exception as rexc:
                logger.info("MCP health: reconnect failed for %s err=%s", name, type(rexc).__name__)

async def get_mcp_client_for_agent(
    agent_settings: AgentSettings,
) -> MultiServerMCPClient:
    """
    Create and connect a MultiServerMCPClient for the given agent.

    📌 Fred rationale:
    - Each agent may declare one or more MCP servers in configuration.
    - We connect to all declared servers here and return a single client object.
    - That client is later injected into the agent runtime context,
      so the agent can transparently call external tools without worrying
      about transport or auth.

    Security/UX design:
    - Outbound authentication is injected automatically (headers or env).
    - If a token is expired, we retry once with a refreshed token.
    - Only supported transports are allowed to prevent misconfigurations.
    - Multiple failures are aggregated into a single ExceptionGroup
      so the developer sees *all* failing servers, not just the first.
    """
    if not agent_settings.mcp_servers:
        raise ValueError("no mcp server configuration")

    ctx = get_app_context()
    oa = ctx.get_outbound_auth()

    client = MultiServerMCPClient()
    exceptions: List[Exception] = []

    # Precompute base auth headers/env once, so we don’t repeat provider calls.
    base_headers = _auth_headers()
    base_stdio_env = _auth_stdio_env()
    auth_label = _mask_auth_value(base_headers.get("Authorization"))
    for server in agent_settings.mcp_servers:
        if server.transport not in SUPPORTED_TRANSPORTS:
            # This ensures config errors surface early instead of silently failing.
            raise UnsupportedTransportError(
                f"Unsupported transport: {server.transport}"
            )

        # --- Build kwargs with explicit Dict[str, Any] ---
        # We construct the full connection spec here.
        connect_kwargs: Dict[str, Any] = {
            "server_name": server.name,
            "url": server.url,
            "transport": server.transport,
            "command": server.command,
            "args": server.args,
            "env": server.env,
            "sse_read_timeout": server.sse_read_timeout,
        }

        # Inject auth according to transport type.
        if server.transport in ("sse", "streamable_http", "websocket"):
            if server.url:
                url = server.url
                if server.transport in ("sse", "streamable_http"):
                    url = _ensure_trailing_slash(url)
                connect_kwargs["url"] = url
            if base_headers:
                connect_kwargs["headers"] = dict(base_headers)
            if server.transport == "streamable_http" and isinstance(server.sse_read_timeout, (int, float)):
                connect_kwargs["sse_read_timeout"] = timedelta(seconds=float(server.sse_read_timeout))
            else:
                connect_kwargs["sse_read_timeout"] = server.sse_read_timeout
        elif server.transport == "stdio":
            merged_env: Dict[str, str] = dict(server.env or {})
            merged_env.update(base_stdio_env)
            connect_kwargs["env"] = merged_env


        url_for_log = connect_kwargs.get("url", "")
        start = time.perf_counter()
        try:
            await client.connect_to_server(**connect_kwargs)
            client.__dict__.setdefault("_conn_specs", {})[server.name] = dict(connect_kwargs)

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
                # Non-auth errors → keep details for final summary
                exceptions.extend(getattr(e1, "exceptions", [e1]))
                continue

            # ---- Auth retry once --------------------------------------------
            logger.info("MCP connect 401 → refreshing token and retrying once (name=%s).", server.name)
            oa = get_app_context().get_outbound_auth()
            refresh_fn = getattr(oa, "refresh", None)
            if callable(refresh_fn):
                try:
                    refresh_fn()
                except Exception as ref_exc:
                    logger.info("MCP token refresh failed quickly name=%s err=%s", server.name, type(ref_exc).__name__)

            fresh_headers = _auth_headers()
            fresh_auth_label = _mask_auth_value(fresh_headers.get("Authorization"))
            if server.transport in ("sse", "streamable_http", "websocket"):
                if fresh_headers:
                    connect_kwargs["headers"] = dict(fresh_headers)
                else:
                    connect_kwargs.pop("headers", None)
            elif server.transport == "stdio":
                merged_env = dict(server.env or {})
                merged_env.update(_auth_stdio_env())
                connect_kwargs["env"] = merged_env

            start2 = time.perf_counter()
            try:
                await client.connect_to_server(**connect_kwargs)
                client.__dict__.setdefault("_conn_specs", {})[server.name] = dict(connect_kwargs)

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

    if exceptions:
        logger.info("MCP summary: %d server(s) failed to connect.", len(exceptions))
        for i, exc in enumerate(exceptions, 1):
            logger.info("  [%d] %s: %s", i, exc.__class__.__name__, str(exc))
        raise ExceptionGroup("Some MCP connections failed", exceptions)

    # Optional: log grand total of tools
    total_tools = sum(len(v) for v in client.server_name_to_tools.values())
    logger.info("MCP summary: all servers connected, total tools=%d", total_tools)

    return client


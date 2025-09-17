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

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any, Dict

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.application_context import get_app_context
from app.common.error import UnsupportedTransportError
from app.common.structures import AgentSettings

logger = logging.getLogger(__name__)

# ✅ Only allow transports that Fred knows how to configure safely.
SUPPORTED_TRANSPORTS = ["sse", "stdio", "streamable_http", "websocket"]


class MCPConnectionError(Exception):
    """Raised when one or more MCP servers fail to connect."""

    def __init__(self, message, exceptions):
        super().__init__(message)
        self.exceptions = exceptions


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


def _auth_headers() -> Dict[str, str]:
    """Build HTTP Authorization headers for outbound MCP requests.

    We consult the app-level outbound auth provider (if configured).
    - If a token is available, return {"Authorization": "Bearer <token>"}.
    - Otherwise return an empty dict.

    Returns:
        Dict of headers suitable for HTTP transports (SSE, streamable_http, websocket).
    """
    oa = get_app_context().get_outbound_auth()
    provider = getattr(oa.auth, "_provider", None)  # internal by design
    if callable(provider):
        try:
            token = provider()
        except Exception:
            return {}
        if token:
            return {"Authorization": f"Bearer {token}"}
    return {}


def _auth_stdio_env() -> Dict[str, str]:
    """Build env vars used to pass auth to stdio transports.

    stdio servers don't see HTTP headers, so we mirror the Authorization header
    as environment variables to maximize compatibility:

    - MCP_AUTHORIZATION
    - AUTHORIZATION

    Returns:
        Environment variable mapping (possibly empty).
    """
    hdrs = _auth_headers()
    if not hdrs:
        return {}
    val = hdrs["Authorization"]
    return {"MCP_AUTHORIZATION": val, "AUTHORIZATION": val}


def _is_auth_error(exc: BaseException) -> bool:
    """Heuristic to detect auth failures from adapter exceptions.

    Some adapter layers surface HTTP auth errors without structured status codes.
    We fallback to message inspection.

    Returns:
        True if the exception likely indicates a 401/Unauthorized, else False.
    """
    msg = str(exc)
    return "401" in msg or "Unauthorized" in msg


# --- small, clear constants (Fred rationale: fast-fail, let retry loop recover) ---
CONNECT_TIMEOUT_SECS = 5.0
SSE_READ_TIMEOUT_SECS = 30.0
CONNECT_TIMEOUT_TD = timedelta(seconds=CONNECT_TIMEOUT_SECS)
SSE_READ_TIMEOUT_TD = timedelta(seconds=SSE_READ_TIMEOUT_SECS)


def _build_streamable_http_kwargs(server, headers: dict[str, str]) -> dict[str, Any]:
    """
    Fred rationale: build explicit, inspectable kwargs for one server.
    Only supports streamable_http here (narrow & simple).
    """
    if not server.url:
        raise ValueError(f"{server.name}: missing URL for streamable_http")
    kw: dict[str, Any] = {
        "server_name": server.name,
        "transport": "streamable_http",
        "url": server.url,
        "timeout": CONNECT_TIMEOUT_TD,  # adapter expects timedelta
        "sse_read_timeout": SSE_READ_TIMEOUT_TD,  # adapter expects timedelta
    }
    if headers:
        kw["headers"] = dict(headers)
    return kw


async def _cleanup_client_quiet(client: MultiServerMCPClient) -> None:
    try:
        await client.exit_stack.aclose()
    except BaseException:
        pass


async def _retry_auth_once(
    oa,
    client: MultiServerMCPClient,
    server,
    connect_kwargs: dict[str, Any],
    auth_label: str,
) -> None:
    """
    Fred rationale: one conservative auth retry path.
    """
    refresh_fn = getattr(oa, "refresh", None)
    if callable(refresh_fn):
        try:
            refresh_fn()
        except Exception:
            logger.warning("Auth refresh failed", exc_info=True)
            # best-effort; continue with retry anyway
            pass

    fresh_headers = _auth_headers()
    fresh_label = _mask_auth_value(fresh_headers.get("Authorization"))
    if fresh_headers:
        connect_kwargs["headers"] = dict(fresh_headers)
    else:
        connect_kwargs.pop("headers", None)

    start = time.perf_counter()
    try:
        await client.connect_to_server(**connect_kwargs)
        dur_ms = (time.perf_counter() - start) * 1000
        tools = client.server_name_to_tools.get(server.name, [])
        logger.info(
            "MCP connect ok (after refresh) name=%s transport=streamable_http url=%s auth=%s tools=%d dur_ms=%.0f",
            server.name,
            connect_kwargs.get("url", ""),
            fresh_label,
            len(tools),
            dur_ms,
        )
    except asyncio.CancelledError:
        logger.warning(
            "🧹 [%s] connect_to_server CANCELLED", connect_kwargs.get("server_name")
        )
        raise

    except asyncio.TimeoutError as e2:
        dur_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "MCP connect timeout (after refresh) name=%s transport=streamable_http url=%s auth=%s dur_ms=%.0f",
            server.name,
            connect_kwargs.get("url", ""),
            fresh_label,
            dur_ms,
        )
        raise e2
    except Exception as e2:
        dur_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "MCP connect fail (after refresh) name=%s transport=streamable_http url=%s auth=%s dur_ms=%.0f err=%s",
            server.name,
            connect_kwargs.get("url", ""),
            fresh_label,
            dur_ms,
            e2.__class__.__name__,
        )
        raise


async def get_mcp_client_for_agent(
    agent_settings: AgentSettings,
) -> MultiServerMCPClient:
    """
    Streamable HTTP ONLY.
    Fred rationale:
    - Keep agent dev simple (just call MCPRuntime.init()).
    - Bound every external call; return fast on failure.
    - Manager’s retry loop handles eventual success.
    """
    if not agent_settings.mcp_servers:
        raise ValueError("No MCP server configuration")

    # Enforce streamable_http-only for this slim version
    for s in agent_settings.mcp_servers:
        if s.transport != "streamable_http":
            raise UnsupportedTransportError(
                "This build supports only 'streamable_http'."
            )

    ctx = get_app_context()
    oa = ctx.get_outbound_auth()

    client = MultiServerMCPClient()
    exceptions: list[Exception] = []

    base_headers = _auth_headers()
    auth_label = _mask_auth_value(base_headers.get("Authorization"))

    for server in agent_settings.mcp_servers:
        # Build kwargs
        try:
            connect_kwargs = _build_streamable_http_kwargs(server, base_headers)
        except Exception as e:
            exceptions.append(e)
            continue

        url_for_log = connect_kwargs.get("url", "")
        start = time.perf_counter()

        # ---- first attempt (bounded) --------------------------------------
        try:
            logger.info(
                "MCP connect start name=%s transport=streamable_http url=%s auth=%s",
                server.name,
                url_for_log,
                auth_label,
            )
            await client.connect_to_server(**connect_kwargs)
            logger.info(
                "MCP connect established name=%s transport=streamable_http url=%s auth=%s",
                server.name,
                url_for_log,
                auth_label,
            )
            # snapshot the spec used — useful for diagnostics
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
                "MCP connect ok name=%s transport=streamable_http url=%s auth=%s tools=%d dur_ms=%.0f",
                server.name,
                url_for_log,
                auth_label,
                len(tools),
                dur_ms,
            )
            continue

        except BaseException as e1:
            dur_ms = (time.perf_counter() - start) * 1000
            logger.warning(
                "MCP connect fail name=%s transport=streamable_http url=%s auth=%s dur_ms=%.0f err=%s",
                server.name,
                url_for_log,
                auth_label,
                dur_ms,
                e1.__class__.__name__,
            )

            if not _is_auth_error(e1):
                exceptions.extend(getattr(e1, "exceptions", [e1]))
                continue

            # ---- one auth retry -------------------------------------------
            try:
                await _retry_auth_once(oa, client, server, connect_kwargs, auth_label)
            except BaseException as e2:
                exceptions.extend(getattr(e2, "exceptions", [e2]))
                continue

    # ---- finalize ---------------------------------------------------------
    if exceptions:
        logger.info("MCP summary: %d server(s) failed to connect.", len(exceptions))
        for i, exc in enumerate(exceptions, 1):
            logger.info("  [%d] %s: %s", i, exc.__class__.__name__, str(exc))
        await _cleanup_client_quiet(client)
        raise MCPConnectionError("Some MCP connections failed", exceptions)

    total_tools = sum(len(v) for v in client.server_name_to_tools.values())
    logger.info("MCP summary: all servers connected, total tools=%d", total_tools)
    return client

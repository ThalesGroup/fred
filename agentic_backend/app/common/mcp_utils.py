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

import logging
from builtins import ExceptionGroup
from typing import Any, Dict, List

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.common.structures import AgentSettings
from app.common.error import UnsupportedTransportError
from app.application_context import get_app_context

logger = logging.getLogger(__name__)

# ✅ Only allow transports that Fred knows how to handle.
#    This prevents silent misconfigurations where a developer
#    sets "grpc" or something unsupported in configuration.yaml.
SUPPORTED_TRANSPORTS = ["sse", "stdio", "streamable_http", "websocket"]


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
            if base_headers:
                connect_kwargs["headers"] = dict(base_headers)
        elif server.transport == "stdio":
            merged_env: Dict[str, str] = dict(server.env or {})
            merged_env.update(base_stdio_env)
            connect_kwargs["env"] = merged_env

        # First connection attempt
        try:
            await client.connect_to_server(**connect_kwargs)
            continue
        except Exception as e1:
            msg = str(e1)
            unauthorized = ("401" in msg) or ("Unauthorized" in msg)
            if not unauthorized:
                # Non-auth errors → collect for final ExceptionGroup
                for exc in getattr(e1, "exceptions", [e1]):
                    if isinstance(exc, Exception):
                        exceptions.append(exc)
                continue

            # Auth error → refresh and retry once
            try:
                logger.info("MCP connect 401 — refreshing token and retrying once.")
                if oa.refresh:
                    oa.refresh()

                fresh_headers = _auth_headers()
                fresh_stdio_env = _auth_stdio_env()

                if server.transport in ("sse", "streamable_http", "websocket"):
                    if fresh_headers:
                        connect_kwargs["headers"] = dict(fresh_headers)
                    else:
                        connect_kwargs.pop("headers", None)
                elif server.transport == "stdio":
                    merged_env2: Dict[str, str] = dict(server.env or {})
                    merged_env2.update(fresh_stdio_env)
                    connect_kwargs["env"] = merged_env2

                await client.connect_to_server(**connect_kwargs)
                continue
            except Exception as e2:
                # Retry failed → collect exception for final aggregation
                exceptions.extend(getattr(e2, "exceptions", [e2]))
                continue

    if exceptions:
        # Aggregate all partial failures so the developer sees the full picture.
        raise ExceptionGroup("Some MCP connections failed", exceptions)

    return client

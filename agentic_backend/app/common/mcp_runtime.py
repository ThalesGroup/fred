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

# app/common/mcp_runtime.py

"""
# MCPRuntime — one place to own MCP init/refresh/close across agents

## Why this exists

Agents in Fred consume MCP servers (e.g., OpenSearch ops, KPI, tabular). These
servers are typically protected by bearer tokens issued on demand by the
outbound auth layer. Tokens expire. After idle periods a user's first request
often hits a `401 Unauthorized` while the auth layer is still “cold”. If we let
that bubble up in the middle of a tool call:

- The LLM can emit `tool_calls`, but the tool invocation fails → OpenAI rejects
  the **next** message with `400` (“assistant message with 'tool_calls' must be
  followed by tool messages…”). noisy + confusing.
- Reconnecting MCP sessions mid-reasoning can leave dangling transports unless
  they’re closed carefully.

**MCPRuntime** centralizes all that logic:

- Initializes a `MultiServerMCPClient` and wraps tools in a context-aware
  toolkit (so runtime parameters can be injected).
- Provides a **serialized** `refresh()` that builds a *fresh* client + toolkit
  when we detect auth issues or timeouts.
- Closes the *old* client quietly, preferring `aclose()` and falling back to
  `close()` / `AsyncExitStack.aclose()` to avoid leftover tasks and
  `CancelledError` noise.
- Exposes `get_tools()` so your tool node can always fetch the *current* tools
  after a refresh (avoid stale snapshots).

Pair this with the resilient tool node (which emits fallback `ToolMessage`s on
transient errors) and your agents remain stable and chatty, instead of brittle.

## How agents use it (recipe)

- Build once per agent:
    ```python
    self.mcp_runtime = MCPRuntime(agent_settings, lambda: self.get_runtime_context())
    await self.mcp_runtime.init()
    self.model = self.model.bind_tools(self.mcp_runtime.get_tools())
    ```

- In your graph’s tools node:
    ```python
    tools_node = make_resilient_tools_node(
        get_tools=self.mcp_runtime.get_tools,                    # live accessor
        refresh_cb=lambda: self.mcp_runtime.refresh_and_bind(self.model),
    )
    ```

- On shutdown:
    ```python
    await self.mcp_runtime.aclose()
    ```

**Important**: pass the callable `get_tools` (not a captured list). After
`refresh()`, the tool node will pull the fresh tool set automatically.

## Error model & behavior

- `refresh()` is guarded by an `anyio.Lock` to serialize concurrent refresh
  calls. If a refresh fails to connect, the previous client/tools are kept.
- Closing the old client prefers public APIs (`aclose()`, then `close()`),
  falling back to `exit_stack.aclose()` as a last resort. Any close-time errors
  are logged at `INFO` and swallowed (best-effort cleanup).
- This module intentionally **does not** auto-refresh on a schedule. Instead,
  your tool node decides *when* to refresh (e.g., after a timeout or `401`) and
  calls `refresh_and_bind()`.

## Observability

- `_snapshot()` logs a compact one-line view of client/toolkit identities and
  the tool names. This is invaluable for verifying that a refresh re-bound the
  model to a new toolkit and not using stale tools.

## Gotchas & tips

- Always re-bind the model after a refresh (`refresh_and_bind`). Bound tool
  specs are captured by the LLM client; forgetting to re-bind means the LLM
  may try to call tools that no longer belong to the current client.
- Avoid capturing `self.toolkit.get_tools()` into a local list at graph build
  time; use a callable (`get_tools`) so refreshes take effect on the next tool
  run.
- This runtime assumes MCP auth/header/env injection is handled upstream by
  `get_mcp_client_for_agent()` (see `mcp_utils.py`), which also retries once on
  `401` with a freshly minted token.

"""

from __future__ import annotations

from contextlib import AsyncExitStack
import inspect
import logging
from typing import Optional

import anyio
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.common.mcp_utils import get_mcp_client_for_agent
from app.common.mcp_toolkit import McpToolkit
from app.common.structures import AgentSettings
from app.core.agents.runtime_context import RuntimeContextProvider

logger = logging.getLogger(__name__)


async def _close_mcp_client_quietly(client: Optional[MultiServerMCPClient]) -> None:
    """Best-effort, no-raise shutdown for a `MultiServerMCPClient`.

    Order of preference:
      1) `client.aclose()`  (async, public API)
      2) `client.close()`   (sync, public API)
      3) `client.exit_stack.aclose()`  (internal safety net)

    Rationale:
    - Some transports spawn background tasks (streams, health loops, etc.).
      Using the public close methods lets the adapter clean them up properly.
    - In rare adapter versions where close isn’t surfaced, we lean on the
      internal `AsyncExitStack` to unwind the context.
    - Any exceptions during shutdown are logged and swallowed to avoid
      disrupting agent flows during refresh or application shutdown.
    """
    if not client:
        return

    try:
        # 1) Public async close
        aclose = getattr(client, "aclose", None)
        if callable(aclose):
            res = aclose()
            if inspect.isawaitable(res):
                await res
            return

        # 2) Public sync close
        close = getattr(client, "close", None)
        if callable(close):
            close()
            return

        # 3) Internal safety net
        exit_stack = getattr(client, "exit_stack", None)
        if isinstance(exit_stack, AsyncExitStack):
            await exit_stack.aclose()

    except Exception:
        logger.info("[MCP] old client close ignored.", exc_info=True)


class MCPRuntime:
    """
    Owns the MCP client + toolkit for an agent.

    Responsibilities:
    - `init()`   : connect to all configured MCP servers and build a toolkit
                  (wrapping base tools with runtime context if provided).
    - `refresh()`:
        * Serialize concurrent refreshes (anyio.Lock)
        * Build a new client + toolkit
        * Swap them in atomically on success
        * Quietly close the old client
      If connection fails, keep the old client/tools and log the error.
    - `get_tools()`: the single, live accessor agents should hand to their
      tool node (`make_resilient_tools_node`) so refreshes are picked up.
    - `aclose()` : graceful shutdown for app/lifespan tear down.

    Typical usage in an agent:

        self.mcp_runtime = MCPRuntime(agent_settings, self.get_runtime_context)
        await self.mcp_runtime.init()
        self.model = self.model.bind_tools(self.mcp_runtime.get_tools())

        tools_node = make_resilient_tools_node(
            get_tools=self.mcp_runtime.get_tools,
            refresh_cb=lambda: self.mcp_runtime.refresh_and_bind(self.model),
        )

    Note:
    - Tool binding is model-specific. After `refresh()`, call
      `refresh_and_bind(self.model)` or manually `model.bind_tools(...)`.
    """

    def __init__(
        self,
        agent_settings: AgentSettings,
        context_provider: Optional[RuntimeContextProvider] = None,
    ):
        self.agent_settings = agent_settings
        self.context_provider = context_provider

        self.mcp_client: Optional[MultiServerMCPClient] = None
        self.toolkit: Optional[McpToolkit] = None

        # Serialize refresh() across concurrent callers (multiple tool errors
        # may attempt a refresh at the same time).
        self._refresh_lock = anyio.Lock()

    # ---------- helpers ----------
    def _snapshot(self, where: str) -> None:
        """Log a compact view of the current client/toolkit and tool names.

        This is extremely useful when diagnosing “stale tool” behavior or
        verifying that a refresh actually replaced the toolset.
        """
        tools = []
        if self.toolkit:
            tools = self.toolkit.get_tools()
        logger.info(
            "[MCP][Snapshot] %s | client=%s toolkit=%s tools=[%s]",
            where,
            f"0x{id(self.mcp_client):x}" if self.mcp_client else "None",
            f"0x{id(self.toolkit):x}" if self.toolkit else "None",
            ", ".join(f"{t.name}@{id(t):x}" for t in tools),
        )

    # ---------- lifecycle ----------
    async def init(self) -> None:
        """Create a connected MCP client and build the toolkit.

        Delegates connection/auth/header/env handling to
        `get_mcp_client_for_agent()`. On success, the agent should bind the
        model’s tools using `self.get_tools()`.
        """
        self.mcp_client = await get_mcp_client_for_agent(self.agent_settings, self.context_provider)
        self.toolkit = McpToolkit(self.mcp_client, self.context_provider)
        self._snapshot("init")

    def get_tools(self) -> list[BaseTool]:
        """Return the *current* set of tools.

        Always call this via a function pointer in your tool node (do not
        capture the list) so that post-refresh toolsets are used automatically.
        """
        return self.toolkit.get_tools() if self.toolkit else []

    async def aclose(self) -> None:
        """Gracefully close current MCP client and drop references.

        Call this from application shutdown/lifespan to ensure transports are
        torn down cleanly and don’t leak background tasks.
        """
        await _close_mcp_client_quietly(self.mcp_client)
        self.mcp_client = None
        self.toolkit = None

    async def refresh(self) -> None:
        """Rebuild MCP client + toolkit and swap them in atomically.

        Behavior:
        - Serialized by `_refresh_lock`.
        - On failure to create a *new* client/toolkit, keeps the previous
          instances untouched and logs the exception.
        - On success, swaps in the new instances and then quietly closes the
          old client.

        This method does not re-bind your model—use `refresh_and_bind()` if you
        want a convenience wrapper that returns a model bound to the fresh tools.
        """
        async with self._refresh_lock:
            self._snapshot("refresh/before")
            old = self.mcp_client
            try:
                new_client = await get_mcp_client_for_agent(self.agent_settings, self.context_provider)
                new_toolkit = McpToolkit(new_client, self.context_provider)
            except Exception:
                logger.exception("[MCP] Refresh failed; keeping previous client.")
                return

            self.mcp_client = new_client
            self.toolkit = new_toolkit
            self._snapshot("refresh/after")
            await _close_mcp_client_quietly(old)
            logger.info("[MCP] Refresh complete.")

    async def refresh_and_bind(self, model):
        """Refresh MCP and return `model` bound to the fresh tools.

        Convenience for tool-node callbacks:
            `refresh_cb=lambda: self.mcp_runtime.refresh_and_bind(self.model)`

        Note: callers must assign the returned model if they keep a local
        reference to a bound model instance.
        """
        await self.refresh()
        return model.bind_tools(self.get_tools())

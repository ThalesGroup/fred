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

# app/common/mcp_toolkit.py

"""
# McpToolkit — context-aware wrapper over MCP tools

## Why this exists

Agents call MCP tools (e.g., OpenSearch ops, KPI, tabular). Many of those tools
benefit from *runtime context* (e.g., current tenant, library allowlists,
time-range defaults, or per-session flags). Hard-coding that logic into each
tool or each agent leads to duplication and drift.

**McpToolkit** wraps the bare MCP tools with a `ContextAwareTool` that can
inject runtime parameters at call time (via a `RuntimeContextProvider`).
This keeps tools declarative and makes agents simpler.

## What it does

- Pulls the base tools from a connected `MultiServerMCPClient`.
- If a `RuntimeContextProvider` is supplied, wraps each base tool in a
  `ContextAwareTool(tool, context_provider)`. Otherwise, returns the base tools.
- Preserves tool identity (name/description/schemas) so the LLM’s
  function-calling remains stable.
- Logs a compact “built tools” snapshot useful for debugging.

## How to use

Typically created by `MCPRuntime`:

```python
self.mcp_runtime = MCPRuntime(agent_settings, self.get_runtime_context)
await self.mcp_runtime.init()
self.model = self.model.bind_tools(self.mcp_runtime.get_tools())
```
or if you need it directly:
```python
toolkit = McpToolkit(mcp_client, context_provider=my_ctx_provider)
tools = toolkit.get_tools()
model = model.bind_tools(tools)
```
"""

import logging
from typing import List, override

from langchain_core.tools import BaseTool, BaseToolkit
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import Field

from app.core.agents.context_aware_tool import ContextAwareTool
from app.core.agents.runtime_context import RuntimeContextProvider

logger = logging.getLogger(__name__)


class McpToolkit(BaseToolkit):
    """Toolkit for MCP tools with optional runtime-context injection.

    If a `RuntimeContextProvider` is given, each tool call goes through a thin
    adapter (`ContextAwareTool`) that:
    - fetches runtime context at invocation time
    - merges/injects defaults (e.g., tenant/library filters, date ranges)
    - forwards to the original tool

    Otherwise, this returns the raw tools from the MCP client.

    The toolkit is immutable after construction; to reflect refreshed MCP
    connections, build a new `McpToolkit` (handled for you by `MCPRuntime`).
    """

    tools: List[BaseTool] = Field(
        default_factory=list, description="List of the tools."
    )

    def __init__(
        self,
        mcp_client: MultiServerMCPClient,
        context_provider: RuntimeContextProvider | None = None,
    ):
        super().__init__()
        base_tools = mcp_client.get_tools()

        if context_provider:
            # Wrap tools with context awareness
            self.tools = [
                ContextAwareTool(tool, context_provider) for tool in base_tools
            ]
        else:
            self.tools = base_tools

        logger.info(
            "[McpToolkit] building tools: toolkit=%s mcp_client=%s tools=[%s]",
            f"0x{id(self):x}",
            f"0x{id(mcp_client):x}",
            ", ".join(f"{t.name}@{id(t):x}" for t in self.tools),
        )

    @override
    def get_tools(self) -> list[BaseTool]:
        """Get the tools in the toolkit."""
        return self.tools

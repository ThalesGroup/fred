# MCP Runtime & Toolkit — Dev Guide

This document explains **how to use** the `MCPRuntime`, `McpToolkit`, and the resilient tools node in our agent framework, and **why** we need these pieces to make OAuth-protected MCP servers work reliably with LLM tool-calling.

---

## TL;DR

- Use **`MCPRuntime`** to create and refresh the MCP client + toolkit for an agent.  
- Bind tools from **`McpToolkit`** to your model.  
- Run tools via our **resilient ToolNode** so a 401/timeout never corrupts your chat turn (no “dangling tool calls”).  
- We automatically:
  - Inject outbound **OAuth** (headers or env for `stdio`).
  - **Retry once** on auth failures after refreshing the token.
  - Normalize URLs and timeouts for HTTP-like transports.
  - Provide **safe, rich logs** without leaking secrets.

Agents should not talk directly to `MultiServerMCPClient`. They should rely on `MCPRuntime`.

---

## Why this is non-trivial (MCP + OAuth is tricky)

1. **Multiple transports**: MCP servers may be `stdio`, `sse`, `streamable_http`, or `websocket`. Auth must be injected differently for each:
   - HTTP-like transports → **Authorization header**
   - `stdio` → **env variables** (no headers possible)

2. **Expiring tokens**: First call after inactivity often returns **401**. We must:
   - Detect auth failures even when adapters don’t surface a structured status code.
   - Refresh the token and retry once.
   - Avoid breaking the LLM turn (OpenAI requires tool calls to be followed by tool results).

3. **Model/tool-call contract**: If the model emits `tool_calls`, the API **must** receive a `ToolMessage` for each `tool_call_id`. If a tool fails or times out and we don’t return tool results, you get the infamous 400:
   > “An assistant message with 'tool_calls' must be followed by tool messages …”

   Our **resilient ToolNode** guarantees that—even on failure—we emit **fallback ToolMessages** so the turn stays valid.

4. **HTTP quirks**: Redirects, timeouts, and server-specific expectations:
   - Some adapters require a **trailing slash** on base URLs.
   - `streamable_http` expects **`timedelta`** for SSE read timeouts.
   - Some servers 401 when terminating sessions (DELETE), which we ignore safely.

5. **Stability and observability**: We need to avoid dangling references to old clients, close resources quietly, and log just enough to debug without leaking secrets.

---

## Components

### `MCPRuntime`
- **Owns** the `MultiServerMCPClient` and the `McpToolkit`.
- **APIs**:
  - `await init()`: connect to all configured MCP servers, wrap tools.
  - `get_tools()`: list of tools (wrapped if a runtime context provider is supplied).
  - `await refresh()`: reconnect with a fresh client and rebuild the toolkit.
  - `await aclose()`: close the client quietly.
  - `await refresh_and_bind(model)`: refresh then return `model.bind_tools(...)`.

It centralizes client lifecycle, auth, and diagnostics so **agents don’t duplicate this logic**.

### `McpToolkit`
- Thin wrapper that takes tools from the MCP client and **optionally wraps** each tool with `ContextAwareTool` (so tools can read the **runtime context**—e.g., current library/project—when invoked by the agent).
- Exposes `get_tools()`.

### Resilient ToolNode (`make_resilient_tools_node(...)`)
- Executes tools with a **per-call timeout**.
- On **timeout / stream closed / 401**:
  - Calls your `refresh_cb()` (which should refresh the MCP client and re-bind tools).
  - **Emits fallback `ToolMessage`s** for all pending `tool_call_id`s so the model turn remains valid.
- This avoids OpenAI’s 400 “missing tool messages” and preserves UX with a clear “temporary auth issue—please retry” message back to the model.

---

## Quickstart: using MCP in an agent

```python
class MyExpert(AgentFlow):
    def __init__(self, agent_settings: AgentSettings):
        self.agent_settings = agent_settings
        self.model = None

        # 1) Runtime context provider is optional; pass one if your tools need it.
        self.mcp_runtime = MCPRuntime(
            agent_settings,
            context_provider=lambda: self.get_runtime_context(),
        )

    async def async_init(self):
        # 2) Model first
        self.model = get_model(self.agent_settings.model)

        # 3) Connect MCP & wrap tools
        await self.mcp_runtime.init()

        # 4) Bind tools to the model
        self.model = self.model.bind_tools(self.mcp_runtime.get_tools())

        # 5) Build graph with resilient ToolNode
        tools_node = make_resilient_tools_node(
            get_tools=self.mcp_runtime.get_tools,
            refresh_cb=self._refresh_and_rebind,  # see below
            per_call_timeout_s=8.0,
        )

        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", self.reasoner)
        builder.add_node("tools", tools_node)
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")
        self._graph = builder
        super().__init__(graph=self._graph, ...)

    async def _refresh_and_rebind(self) -> None:
        # Called by the resilient ToolNode when it detects 401/timeout/closed stream.
        self.model = await self.mcp_runtime.refresh_and_bind(self.model)

    async def aclose(self):
        await self.mcp_runtime.aclose()

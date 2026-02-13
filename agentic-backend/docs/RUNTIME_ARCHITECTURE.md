# Chat Runtime Architecture (Sessions · Agents · MCP)

This document explains the new end‑to‑end flow from a user question to an agent’s response, including session restore, agent caching/initialization, streaming, persistence, KPIs, and MCP integration.

## 1) High‑Level Flow

1. WebSocket receives `ChatAskInput` and authenticates the user
2. SessionOrchestrator ensures a session exists (restore or create)
3. AgentFactory returns a warm agent (cached or freshly initialized)
4. Minimal LC history is restored when needed (non‑cached agent)
5. The user message is emitted to the stream
6. StreamTranscoder runs the agent graph and streams events → ChatMessage[]
7. Final messages are persisted; KPIs are recorded; FinalEvent sent to client

Key benefit: the controller stays transport‑only; orchestration and runtime logic are isolated for testability and clarity.

## 2) Key Components

- WebSocket Controller — accepts WS, parses input, sends events
  - `agentic_backend/core/chatbot/chatbot_controller.py`
- SessionOrchestrator — session lifecycle, history, KPI, persistence, streaming
  - `agentic_backend/core/chatbot/session_orchestrator.py`
- AgentFactory — per-(session, agent) cache, initialization, leader crew
  - `agentic_backend/core/agents/agent_factory.py`
- AgentFlow — base agent class (tuning, graph compile, astream_updates)
  - `agentic_backend/core/agents/agent_flow.py`
- StreamTranscoder — turns LangGraph events into Chat Protocol v2 messages
  - `agentic_backend/core/chatbot/stream_transcoder.py`
- MCPRuntime — token‑aware MCP client + toolkit lifecycle for tools
  - `agentic_backend/common/mcp_runtime.py`

## 3) Detailed Sequence (Single Exchange)

1) WebSocket handler accepts and authenticates
- Reads token from `Authorization` header or `token` query param; decodes via Keycloak
- Accepts `ChatAskInput`, reconciles access/refresh tokens and injects into `RuntimeContext`
- References:
  - `chatbot_controller.py:181` WebSocket route
  - `chatbot_controller.py:200`–`214` token handling
  - `chatbot_controller.py:251`–`255` inject tokens into `RuntimeContext`

2) Orchestrator entrypoint
- `SessionOrchestrator.chat_ask_websocket(...)` orchestrates the whole exchange
- References:
  - `session_orchestrator.py:114`–`135` method header and responsibilities

3) Session ensure/restore
- Get or create session; for new sessions, generate a concise title via the default model
- References:
  - `session_orchestrator.py:161`–`164` ensure session
  - `_get_or_create_session` at `session_orchestrator.py:520+` (title generation)

4) Agent creation/reuse
- `AgentFactory.create_and_init(...)` returns a warm, per-(session, agent) instance
- If cached: refresh runtime context; else: instantiate from catalog, apply settings, set context, run `async_init` (Leader builds crew)
- References:
  - `agent_factory.py:64`–`110` create/reuse
  - `agent_factory.py:129`–`176` simple vs leader init/crew

5) History restore (only when not cached)
- Rebuilds minimal LangChain history (system/human/assistant + tool calls/results) per exchange, ordered by `rank`, with a window of the last N exchanges
- References:
  - `session_orchestrator.py:171`–`180` restore decision and logging
  - `_restore_history` at `session_orchestrator.py:400+`

6) Emit user message and run agent
- Emit user message immediately to the stream (rank = current history length)
- Wrap agent execution with KPI timer and run via `StreamTranscoder.stream_agent_response`
- References:
  - Emit: `session_orchestrator.py:186`–`199`
  - Stream: `session_orchestrator.py:203`–`231`

7) Streaming and transcoding
- `StreamTranscoder` executes `agent.astream_updates(...)` with a `RunnableConfig` carrying `thread_id`, `user_id`, `access_token`, `refresh_token`
- Converts LLM/tool events to ChatMessage parts: `TextPart`, `ToolCallPart`, `ToolResultPart`, and optional `thought`
- Ensures exactly one assistant `final` per exchange, with intermediate `observation` messages when applicable
- References:
  - `stream_transcoder.py:120`–`137` run config and tokens
  - `stream_transcoder.py:171`–`239` tool calls/results
  - `stream_transcoder.py:291`–`335` final vs observation channels

8) Persist + KPIs + FinalEvent
- Persist session (updated_at) and the union of prior + emitted messages
- Record `chat.exchange_total` with `status=ok|error`
- Send `FinalEvent` over WS with the full message batch of the exchange
- References:
  - `session_orchestrator.py:236`–`256` KPIs and persistence
  - `chatbot_controller.py:274`–`278` FinalEvent

## 4) Agent Lifecycle & Caching

- Cache key: `(session_id, agent_id)` using a thread‑safe LRU with a bounded size from configuration
- On reuse, always refresh the runtime context (tokens can change across requests)
- Fresh builds apply authoritative settings from AgentManager, then call `async_init`
- LeaderFlow builds a crew by instantiating and initializing each expert agent once; the crew is passed to the leader’s `async_init`
- Session deletion triggers `AgentFactory.teardown_session_agents(session_id)` which sequentially awaits each agent’s `aclose()`
- References:
  - `agent_factory.py:51`–`61`, `:76`–`90`, `:92`–`110`, `:129`–`176`, `:179`–`200`

## 5) MCP Integration (Tools)

- Agents that need tools declare MCP server(s) in their tunings; during `async_init`, they:
  - Instantiate `MCPRuntime(agent=self)`
  - `await mcp.init()` to create a `MultiServerMCPClient` using the agent’s `RuntimeContext` tokens
  - Bind tools to the model, e.g., `self.model = self.model.bind_tools(self.mcp.get_tools())`
- Lifecycle guarantees: the MCP client opens and closes in the same asyncio task; `aclose()` is awaited on agent teardown
- Example: `SentinelExpert` shows end‑to‑end binding of MCP tools in `async_init`
- References:
  - `sentinel_expert.py:86`–`103` init + bind tools
  - `mcp_runtime.py:88`–`123` init; `:124`–`180` lifecycle task; `:181`–`195` tool access; `:196`–`200` aclose signature

## 6) Security & Tokens

- WS handler reconciles access/refresh tokens per message and writes them into `RuntimeContext`
- Tokens flow via `RunnableConfig.configurable` to the agent graph; tools/LLMs can read them from `agent.run_config`
- Agents may refresh tokens mid‑run via `AgentFlow.refresh_user_access_token()` which updates the `RuntimeContext`
- References:
  - Inject: `chatbot_controller.py:251`–`255`
  - Pass: `stream_transcoder.py:129`–`137`
  - Refresh helper: `agent_flow.py:120`–`238`

## 7) History Model & Restore Rules

- Persistence uses Chat Protocol v2 (`ChatMessage` with `rank`, `exchange_id`, `role`, `channel`, `parts`)
- Restore is strictly ordered by `rank` (true chronology) and windowed by “last N exchanges” if configured
- Tool call context is tracked per‑exchange to avoid cross‑leak; a `ToolMessage` is emitted only if a matching call_id exists in the same exchange
- References:
  - `session_orchestrator.py:112`–`135` responsibility note
  - `_restore_history` at `session_orchestrator.py:400+`

## 8) KPIs & Metrics

- KPIs recorded for counts and latency with `agent_id`, `session_id`, `exchange_id`, and `user_id`
- Outcome (`status=ok|error`) is decided after streaming based on the presence of a single assistant/final
- Metrics retrieval is delegated to the history store
- References:
  - `session_orchestrator.py:147`–`160`, `:203`–`248`, `:338`–`356`

## 9) Error Handling

- WS handler distinguishes internal vs external errors and sends `ErrorEvent` if the socket is still connected
- Orchestrator logs failures during agent execution; KPI timer marks status=error in that case
- References:
  - `chatbot_controller.py:280`–`308`
  - `session_orchestrator.py:232`–`235`

## 10) Extensibility Guidance

- To add a new agent:
  - Register it in the catalog (YAML/DB) with `class_path` and tuning fields
  - Implement `async_init` to set the model, initialize MCP (when needed), bind tools, and build the graph
  - Return a compiled graph via `get_compiled_graph()` and stream with `astream_updates`
- To enable MCP tools, add MCP servers in the agent’s tuning; ensure `RuntimeContext` carries tokens

---

This architecture keeps concerns cleanly separated: transport (WS), orchestration (sessions/history/KPIs), agent runtime (graphs/tools), and persistence/metrics. It is token‑aware, safe to cache across exchanges, and friendly to MCP‑enabled agents.


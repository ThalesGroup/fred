# Fred Portable Layer

This document describes the portable infrastructure layer that sits beneath the
Fred agent runtime. Its purpose is to standardize cross-cutting concerns —
observability and context propagation — in a way that is decoupled from any
specific agent framework, backend, or deployment environment.

---

## Why a portable layer exists

Fred agents run on top of LangGraph and LangChain. Those frameworks are adapters,
not the identity of the platform. The cross-cutting concerns an agent depends on
(tracing, metrics, context) should not be expressed in framework-specific terms.

The portable layer defines the stable spine that holds those concerns together:

- a small **tracer interface** decoupled from any one observability backend
- a **metrics timer interface** for duration measurements
- a **null base-class design** — safe by default, no dependencies required

This lives in `fred_core.portable` (zero runtime dependencies, pure Python stdlib)
and is wired by `fred-runtime` into the actual FastAPI and LangGraph execution path.

---

## Layer map

```
fred_core.portable     Contracts only — Tracer, Span, MetricsProvider
                        Zero dependencies. Pure Python base classes.
     │
fred-runtime           Wires portable contracts to real platform services
     │                  observability_factory.py → Langfuse / logging / null backends
     │                  UserTokenRefresher   → Keycloak token refresh
     │                  RequestContextHelpers → FastAPI dependency injection
     │
fred-sdk               Agent runtime — ReAct, Graph, Team
                        Receives RuntimeServices which carries the wired instances
```

---

## Observability

`fred_core.portable` defines three classes:

| Class             | Responsibility                                                      |
| ----------------- | ------------------------------------------------------------------- |
| `Tracer`          | Start named spans with attributes (base = null/no-op)               |
| `Span`            | One unit of traced work — set attributes, end                       |
| `MetricsProvider` | Timer context manager for duration measurements (base = null/no-op) |

Standard span names used across the Fred runtime:

| Span name    | Emitted by                  |
| ------------ | --------------------------- |
| `agent.run`  | Agent execution entry point |
| `llm.call`   | LLM invocation              |
| `tool.call`  | Tool execution              |
| `mcp.invoke` | MCP transport call          |

Three built-in implementations ship with `fred_core.portable`:

| Implementation            | Use case                                         |
| ------------------------- | ------------------------------------------------ |
| `Tracer` (base)           | Default — no overhead, safe in any environment   |
| `LoggingTracer`           | Emits spans as structured log entries            |
| `MetricsProvider` (base)  | Default — no overhead, null timer                |
| `LoggingMetricsProvider`  | Emits timer entries as structured log entries    |
| `InMemoryMetricsProvider` | Test assertions — inspect captured timer records |

`fred-runtime`'s `observability_factory.py` selects and constructs the appropriate
backend (Langfuse, logging, null) based on `configuration.yaml` at pod startup.

---

## Usage

```python
from fred_core.portable import (
    get_tracer, get_metrics_provider,
    set_tracer, set_metrics_provider,
    LoggingTracer, LoggingMetricsProvider,
)

# Configure once at startup (done by observability_factory):
set_tracer(LoggingTracer())
set_metrics_provider(LoggingMetricsProvider())

# Use anywhere in the runtime:
tracer = get_tracer()
span = tracer.start_span("agent.run", agent_id="my-agent")
span.set_attribute("session_id", session_id)
span.end()

with get_metrics_provider().timer("tool.call", dims={"tool": "search:v1"}) as dims:
    result = await tool.run()
    dims["status"] = "ok"
```

---

## Test support

`InMemoryMetricsProvider` stores `TimerRecord(name, dims)` entries for assertion:

```python
from fred_core.portable import InMemoryMetricsProvider

metrics = InMemoryMetricsProvider()
services = RuntimeServices(metrics=metrics)

# ... run the agent ...

assert any(
    t.name == "app.phase_latency_ms" and t.dims.get("phase") == "v2_graph_node"
    for t in metrics.timers
)
```

---

## Identity

`fred-runtime` wires a `UserTokenRefresher` that implements the token-provider
pattern: it holds the current user's access token and refreshes it transparently
before expiry using the Keycloak refresh token.

Agent tools and MCP clients receive the token through `ToolContext.access_token` —
they never own token lifecycle directly.

The separation is:

- **where a token comes from** → `UserTokenRefresher` / Keycloak (runtime concern)
- **where a token is used** → tool calls, MCP requests, Knowledge Flow clients (authoring concern)

---

## Tool invocation boundary

The stable portability boundary for tool calls is not a LangChain `Tool` object or
a LangGraph node — it is:

- a **tool reference** (string id declared on the agent)
- a **normalized input payload**
- the **portable context** (`RuntimeContext` carrying user, team, session, token)

`fred-runtime`'s `ContextAwareTool` base class enforces this: every platform tool
receives a `ToolContext` that carries the full runtime context rather than
platform-specific arguments. This makes tools testable in isolation and portable
across agent families (ReAct, Graph, Team).

---

## What this layer is not

- Not an agent framework — it does not define agent lifecycle, sessions, or routing
- Not a transport layer — it does not own HTTP or MCP connections
- Not a governance engine — policy evaluation lives in the control plane
- Not a replacement for LangGraph — it sits beneath it, not above it

Fred keeps the agent runtime shell. This layer provides the portable infrastructure
contracts around it.

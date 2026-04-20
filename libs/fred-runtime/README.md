# fred-runtime

`fred-runtime` is the infrastructure and execution layer for Fred agent pods.  
It wires platform services (databases, LLM routing, MCP, observability, security) into
the execution engine defined by `fred-sdk`, and provides a ready-to-use FastAPI app
factory so any agent pod is just a registry and a YAML file away from running.

---

## Where `fred-runtime` fits

Fred follows a strict three-layer model:

```
fred-core          Pure utilities — model factories, embeddings, logging, KPI store
     │
fred-sdk           Execution engine + authoring surface (pip-installable, no infra)
     │              ReAct runtime, Graph runtime, agent contracts, tool abstractions
     │
fred-runtime       Platform adapters + pod factory (this package)
                    SQL checkpointer, MCP wiring, LLM routing, OpenAI-compat surface,
                    FastAPI app factory, observability, security middleware
```

**Rule of thumb:**
- Write agent logic in `fred-sdk`.  
- Write infrastructure adapters (DB, MCP server, Keycloak, object store) in `fred-runtime`.  
- `fred-sdk` must stay importable on a bare laptop with no services running.

---

## What's in the box

### `fred_runtime.app` — Agent pod factory

The main entry point for building a Fred agent pod.

```python
from fred_runtime.app import create_agent_app, load_agent_pod_config

config = load_agent_pod_config()          # reads ENV_FILE + CONFIG_FILE (configuration.yaml)
app    = create_agent_app(registry=REGISTRY, config=config)
```

`create_agent_app` returns a FastAPI application that exposes:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `{base_url}/agents/execute` | Single-turn execution — returns final JSON |
| `POST` | `{base_url}/agents/execute/stream` | Streaming SSE execution — yields `RuntimeEvent` objects |
| `GET`  | `{base_url}/agents` | List registered agent IDs |
| `GET`  | `{base_url}/agents/sessions` | List session IDs for a user |
| `GET`  | `{base_url}/agents/sessions/{id}/messages` | Full conversation history for a session |
| `GET`  | `/v1/models` | OpenAI model list (agent IDs as model names) |
| `POST` | `/v1/chat/completions` | OpenAI chat completions — works with Open WebUI, openai-python SDK, etc. |

The OpenAI-compatible `/v1` surface is **enabled by default**.  
Set `app.openai_compat: false` in `configuration.yaml` to disable it for internal pods.

Multi-turn continuity and HITL (human-in-the-loop) are handled transparently through
the SQL checkpointer. The session ID is the LangGraph `thread_id`.

---

### `fred_runtime.runtime_support` — Infrastructure adapters

| Module | What it provides |
|--------|-----------------|
| `sql_checkpointer` | Durable LangGraph checkpointer backed by SQLite (dev) or PostgreSQL (prod) |
| `user_token_refresher` | Transparent Keycloak token refresh for long-lived agent sessions |
| `request_context_helpers` | FastAPI dependency helpers for extracting user/session context |

---

### `fred_runtime.model_routing` — LLM routing

Multi-provider model resolution with per-agent tuning overrides.  
Supports routing by agent ID, execution category, or explicit model name.  
Providers: OpenAI, Azure OpenAI, Mistral, Ollama, and any LangChain-compatible backend.

---

### `fred_runtime.common` — Knowledge Flow + MCP clients

HTTP clients that connect agent tools to the Fred platform services:

| Client | Connects to |
|--------|------------|
| `kf_http_client` | Knowledge Flow REST API (generic) |
| `kf_vectorsearch_client` | Vector search / retrieval |
| `kf_markdown_media_client` | Document content (Markdown + media) |
| `kf_workspace_client` | Workspace and library management |
| `kf_logs_client` | Audit log retrieval |
| `kf_fast_text_client` | FastText classification |
| `mcp_runtime` / `mcp_toolkit` | MCP server lifecycle and tool injection |
| `context_aware_tool` | Tool base class that propagates the runtime context (user, team, token) |

---

### `fred_runtime.integrations` — v2 runtime adapters

Small adapters that bridge the platform-agnostic `fred-sdk` contracts to real
services available at runtime (chat model factory, checkpointer wiring, MCP discovery).

---

### `fred_runtime.client` — Developer CLI (`fred-agent-chat`)

An interactive REPL and one-shot client for any Fred agent pod:

```bash
# Interactive mode — connects to http://127.0.0.1:8000/api/v1 by default
fred-agent-chat

# Set the current team scope inside the REPL
/team my-team

# Inspect runtime KPIs without Grafana
/kpi
/kpi tool_name=search

# One-shot
fred-agent-chat --agent my-agent "What is the status of cluster A?"

# Run a YAML scenario file (smoke tests, checkpointing tests)
fred-agent-chat --scenario tests/scenarios/smoke.yaml

# Keycloak browser login
fred-agent-chat --login

# Start already scoped to one team
fred-agent-chat --team-id my-team

# Override the metrics endpoint used by /kpi
fred-agent-chat --metrics-url http://127.0.0.1:9115/metrics
```

The target pod URL is resolved from `configuration.yaml` automatically,
or overridden with `--base-url` / `FRED_AGENT_POD_URL`.

---

## Configuration

Every Fred pod uses the same two-file convention:

| File | Purpose |
|------|---------|
| `.env` (path from `ENV_FILE`) | Secrets: API keys, DB URLs, Keycloak credentials |
| `configuration.yaml` (path from `CONFIG_FILE`) | App settings: port, base URL, LLM routing, observability, security |

Minimal `configuration.yaml` for a local pod:

```yaml
app:
  name: "My Agent Pod"
  base_url: "/myapp/v1"
  host: "0.0.0.0"
  port: 8010
  log_level: "info"
  metrics_address: "127.0.0.1"
  metrics_port: 9115
  kpi_process_metrics_interval_sec: 10

observability:
  tracer: logging
  metrics: prometheus

ai:
  knowledge_flow_url: "http://localhost:8111/knowledge-flow/v1"
```

Full schema: `fred_runtime.app.config.AgentPodConfig`.

When `observability.metrics: prometheus` is enabled, `create_agent_app(...)`
starts a dedicated Prometheus exporter on `app.metrics_address:app.metrics_port`
and restores the shared Fred KPI pipeline, including process and SQL pool KPIs.

---

## Installation

```bash
# Core library (runtime adapters, CLI, model routing)
pip install fred-runtime

# With FastAPI pod factory
pip install fred-runtime[app]
```

Requires Python 3.12.

---

## Building an agent pod

A minimal pod is three files:

**`main.py`**
```python
from fred_runtime.app import create_agent_app, load_agent_pod_config
from myapp.registry import REGISTRY

config = load_agent_pod_config()
app = create_agent_app(registry=REGISTRY, config=config)
```

**`__main__.py`**
```python
import uvicorn
from fred_runtime.app import load_agent_pod_config

def main():
    config = load_agent_pod_config()
    uvicorn.run("myapp.main:app", host=config.app.host, port=config.app.port, reload=True)

if __name__ == "__main__":
    main()
```

**`registry.py`**
```python
from fred_sdk.contracts.models import ReActAgentDefinition

class MyAgent(ReActAgentDefinition):
    agent_id = "my-agent"
    ...

REGISTRY = {MyAgent.agent_id: MyAgent()}
```

See [fred-samples](https://github.com/ThalesGroup/fred) for a working reference pod.

---

## Related packages

| Package | PyPI | Role |
|---------|------|------|
| `fred-core` | [pypi](https://pypi.org/project/fred-core/) | Pure utilities — logging, model factories, embeddings, portable observability |
| `fred-sdk` | [pypi](https://pypi.org/project/fred-sdk/) | Agent authoring — ReAct, Graph, tool contracts |
| `fred-runtime` | [pypi](https://pypi.org/project/fred-runtime/) | This package |

---

## License

Apache 2.0 — see [LICENSE](./LICENSE).

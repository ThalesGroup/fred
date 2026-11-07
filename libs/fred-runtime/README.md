# fred-runtime

`fred-runtime` is the infrastructure and execution layer for Fred agent pods.  
It wires platform services (databases, LLM routing, MCP, observability, security) into
the execution engine defined by `fred-sdk`, and provides a ready-to-use FastAPI app
factory so any agent pod is just a registry and a YAML file away from running.

---

## Where `fred-runtime` fits

```
fred-pod                    configuration, identity, naming
└── fred-sdk                authoring contracts
    └── [agents]            + fred-core, langchain, langgraph
        └── fred-runtime    execution, MCP, model routing    ← this package
            └── [app]       + the FastAPI pod factory        → an agent pod
```

**Rule of thumb:**

- Write agent logic against `fred-sdk`.
- Write infrastructure adapters (DB, MCP server, Keycloak, object store) in `fred-runtime`.
- `fred-sdk` must stay importable on a bare laptop with no services running.

A Knowledge Base pod does not need this package. What a pod is, and which
package each kind installs:
[fred-pod](https://github.com/ThalesGroup/fred/tree/swift/libs/fred-pod).

---

## What's in the box

### `fred_runtime.app` — Agent pod factory

The main entry point for building a Fred agent pod.

```python
from fred_runtime.app import create_agent_app, load_agent_pod_config

config = load_agent_pod_config()          # reads ENV_FILE + CONFIG_FILE (configuration.yaml)
app    = create_agent_app(registry=REGISTRY, config=config)
```

`create_agent_app` mounts protected routes with the explicit admission dependency
`app.security.current_user`: common JWT/delegation verification, then the effective
person's configured terms acceptance in `cp_read.terms_acceptance`. Capability
routers inherit this guard at mounting; their handlers retain local resource
authorization. No historical OIDC admission override is installed. The shared
`get_config` override remains available to contributed routers and other helpers.

`create_agent_app` returns a FastAPI application that exposes:

| Method | Path                                       | Description                                                              |
| ------ | ------------------------------------------ | ------------------------------------------------------------------------ |
| `POST` | `{base_url}/agents/execute`                | Single-turn execution — returns final JSON                               |
| `POST` | `{base_url}/agents/execute/stream`         | Streaming SSE execution — yields `RuntimeEvent` objects                  |
| `GET`  | `{base_url}/agents`                        | List registered agent IDs                                                |
| `GET`  | `{base_url}/agents/sessions`               | List session IDs for a user                                              |
| `GET`  | `{base_url}/agents/sessions/{id}/messages` | Full conversation history for a session                                  |
| `GET`  | `/v1/models`                               | OpenAI model list (agent IDs as model names)                             |
| `POST` | `/v1/chat/completions`                     | OpenAI chat completions — works with Open WebUI, openai-python SDK, etc. |

The OpenAI-compatible `/v1` surface is **enabled by default**.  
Set `app.openai_compat: false` in `configuration.yaml` to disable it for internal pods.

Multi-turn continuity and HITL (human-in-the-loop) are handled transparently through
the SQL checkpointer. The session ID is the LangGraph `thread_id`.

---

### Private Weaver history reads

The HTTP readers for messages, session IDs and checkpoint details/index share
`app/history_access.py`. After the existing JWT/admission dependency, only a
person with their own bearer may read: anonymous/dev access, service accounts,
service roles and asserted delegation are refused. The actual
`PersonCredentialProvider` forwards that bearer only to the configured Control
Plane destination, with the shared bounded HTTP client, no inherited auth,
redirects or retry. No run or delegated credential is created for a read.

The pod reads M4's `checkpoint_thread_owner.binding_json` and its owner without
loading checkpoints or messages. That persisted space selects M5a's
`GET /spaces/{space}/sessions/{session}`. M5a checks current admission, space Read
and private ownership. Its response must match the pod's session key, space,
instance, template and runtime; the local owner must match the authenticated
person and the runtime must match this pod. Request query IDs confer no authority.
The metadata response omits the person ID: its owner-scoped query is the
Control Plane proof of that same bearer person's ownership.

No executable instance, template discovery, preparation or M4 resolver is involved.
An instance's removal/disablement or an unusable template therefore does not deny
otherwise authorized history. Success responses use `Cache-Control: no-store`;
every independent consultation makes fresh checks. One content read costs one
local provenance SELECT and one M5a GET before the content query. Indexes process
local owner-filtered candidates serially to bound pressure on the shared client;
cost grows with that person's stored sessions, with no cross-request decision cache.
No SQL connection is retained while waiting for Control Plane.

Unknown, foreign, revoked, mismatched and unbound conversations return the same
404 `Conversation unavailable`. Authorized conversations with persisted provenance
and zero messages return `[]`. Metadata-only registrations that have never acquired
M4 provenance are unavailable through these pod readers; reading never creates a
binding. Old history, including history retained after checkpoint/provenance erasure,
is not adopted or repaired. Indexes omit refused candidates; 401 and infrastructure
failures abort the request instead of returning partial success or empty history.
SQL failures propagate as technical errors; provenance storage/Control Plane
unavailability returns 503. No content is loaded before the shared guard.

Covered routes: GET `/agents/sessions`, `/agents/sessions/{id}/messages`,
`/agents/checkpoints` and `/agents/checkpoints/{id}`. Aggregate `_stats` contains no
session IDs or conversation content; erasure endpoints are outside this read lot.
The CLI already raises HTTP failures, and the existing frontend history hook treats
non-2xx as unavailable. Neither consumer is rewired here; frontend cache behavior
and full chat integration remain separate work. Turn admission, invocation, retry,
descendant, cancellation and terminal authority are unchanged.

---

### `fred_runtime.runtime_support` — Infrastructure adapters

| Module                    | What it provides                                                           |
| ------------------------- | -------------------------------------------------------------------------- |
| `sql_checkpointer`        | Durable LangGraph checkpointer backed by SQLite (dev) or PostgreSQL (prod) |
| `user_token_refresher`    | Transparent Keycloak token refresh for long-lived agent sessions           |
| `request_context_helpers` | FastAPI dependency helpers for extracting user/session context             |

---

### `fred_runtime.model_routing` — LLM routing

The Weaver chat factory consumes Control Plane's admitted `inference` decision.
Selection and reasoning are evaluated once by Control Plane; this runtime supplies
no independent fallback or model policy. `TurnAuthority` preserves provenance and
lifetime, and invocation/HTTP guards enforce the admitted model and options.

Each `inference_credentials` entry binds `credential_binding` and `api_root`, and
names the variables required by the admitted `auth`: `api_key_env`, `client_secret_env`,
`gateway_key_env`. Both values and that exact set must match before reading any variable.
Every connection takes one path: one `ChatOpenAI` on the shared bounded HTTP pools,
whose transport guard accepts one URL and sets the gateway key. No global-key or Swift
profile fallback is available. See the Control Plane README's inference connection and workload
provisioning and rotation contract; environment changes require a coordinated
workload restart, while already-admitted clients retain their context.

---

### Pod skills and admitted loading

Missing `skills` or `skills: {}` defaults to the packaged directory; explicit
`skills: null` disables it. Custom directories retain the same admission rules.
The pod inventories a bounded immutable snapshot, including invocation modes and
builtin provenance. ReAct `load_skill`, native reads and Deep's read-only backend
use that snapshot; a later filesystem edit requires a restart and inventory refresh.

Control Plane owns authorization, using the same pod offers as capabilities with
organization/team/project ceilings. `WeaverRuntimeBinding.skills` admits a subset
and its source revision. Missing admission denies new loads; mismatching nonempty
revisions or metadata fail explicitly. Runtime configuration cannot grant a skill.
An available empty source, disabled source and unavailable source are distinct.

The packaged set is `analyze-data`, `compare-options`, `grounded-research`,
`summarize-document` (model-only), `meeting-minutes`, `grill-me` (user-selected),
and `graph` (both). The graph skill can use tables, charts or Mermaid and loads
its Mermaid reference only when needed. Retired names have no aliases. Custom
skills retain their own presentation; only trusted package entries get translated
builtin labels. Graph agents and embedded Ralph are unsupported.

Each managed team, personal or project turn/resume receives a fresh server
admission. A running admitted turn may finish; revocation prevents later loads,
without deleting historical instructions/checkpoints. Partial/full load traces
come from actual reads, including referenced files, not from plain name mentions.
Public catalog/detail GETs use the person's resolver projection and never obtain
inference/title admission. See the [operator note](../../deploy/release-notes/changes/weaver-pod-skills-and-space-ceilings.md).

---

### Deep conversation deliverables

Deep registers `list_conversation_files`, `read_conversation_file` and
`publish_conversation_file` through its existing middleware tool mechanism. They
reuse `RuntimeServices.workspace_fs`, the admitted CP delegation, the common writer
and its transport replay. Lists contain up to 100 entries per call. Reading copies
UTF-8 bytes into an unused workspace path and returns the content identity selected
with those bytes. The model retains that identity in the conversation tool result
and submits it unchanged when replacing the original catalogue path on a later turn.
A concurrent update returns a conflict, requiring another read and edit.

Publication accepts saved `.md` and `.csv` workspace files up to 4 MiB. A null
expected identity means creation only. The tool returns the confirmed CP identity
and common download link; on transport uncertainty it returns an error with the
replay key, never a success link. Replay requires identical arguments and unchanged
workspace bytes. The existing conversation files drawer reloads after the turn.
Workspace, `.deep`, checkpoints, skills and editor access keep their existing
owners. Editor buffers are not synchronized back to workspace files and are never
used as publication input. This implementation still needs end-to-end k3d acceptance.

### Managed conversation titles

Managed execution now uses the workload-delegated **POST** runtime resolver. Its
optional `title` admission is the sole authority to generate a title; preparation,
skill catalog GETs and browser flags do not grant that permission. Resume admission
consumes eligibility without generating another title. Existing sessions remain
unchanged. Standalone/local SDK invocations without a managed admission do not
produce persistent titles.

`app/session_title.py` uses the existing routed factory, admitted credentials,
HTTP pools and inference tracing/KPI middleware. The title admission may name a
different permitted offer, or the answer offer with independent bounded options.
It does not change the answer model or inherit its reasoning parameters. Model
instances are cached per complete selection so these options cannot collide.

One child task lives inside the owner's `RunScope`: input is limited to 600
characters, the prompt targets 3–8 words, cleaned text is limited to 80 characters,
and the whole operation has a 10-second budget. Persistence has a 2-second bound;
the final answer waits at most 2 seconds for outstanding title work. Completion,
disconnection and cancellation cancel and await that child before authority closes.
Errors/invalid output preserve the initial title without failing the answer.

The workload-only conditional metadata write carries immutable admitted provenance
and the attempt ID. A manual rename or deletion supersedes it. On success the SSE
`session_title` event carries only the originating session ID: consumers reload
canonical metadata. Usage is aggregated by offer in the existing idempotent run
report (one aggregate when answer and title share the offer). It is not added to
the assistant's displayed answer usage or saved as a chat message. Received usage
is retained even if title cleanup/persistence fails; unavailable provider counters
on cancellation are not estimated. No title retries or background worker are added.

See the [Control Plane contract](../../apps/control-plane/README.md#automatic-conversation-titles)
and [rollout note](../../deploy/release-notes/changes/weaver-conversation-titles.md).

### `fred_runtime.common` — Knowledge Flow + MCP clients

HTTP clients that connect agent tools to the Fred platform services:

| Client                        | Connects to                                                             |
| ----------------------------- | ----------------------------------------------------------------------- |
| `kf_http_client`              | Knowledge Flow REST API (generic)                                       |
| `kf_vectorsearch_client`      | Vector search / retrieval                                               |
| `kf_markdown_media_client`    | Document content (Markdown + media)                                     |
| `kf_workspace_client`         | Workspace and library management                                        |
| `kf_fast_text_client`         | FastText classification                                                 |
| `mcp_runtime` / `mcp_toolkit` | MCP server lifecycle and tool injection                                 |
| `context_aware_tool`          | Tool base class that propagates the runtime context (user, team, token) |

---

### `fred_runtime.integrations` — v2 runtime adapters

Small adapters that bridge the platform-agnostic `fred-sdk` contracts to real
services available at runtime (chat model factory, checkpointer wiring, MCP discovery).

`DocumentSimilarityAdapter` uses `/documents/search` with the anchor as `question`.
It narrows model-named document IDs through the turn's selection and builds the
same `TurnAuthority` document context as document search, with corpus enabled
and attachments excluded. Knowledge Flow uses its default search policy and
optionally reranks before filtering original scores. Only similarity opts into
bounded transient retries and `timeouts.similarity_read`; ordinary search keeps
its existing transport settings.

---

### `fred_runtime.client` — Developer CLI (`fred-agents-cli`)

An interactive REPL and one-shot client for any Fred agent pod:

```bash
# Interactive mode — connects to http://127.0.0.1:8000/api/v1 by default
fred-agents-cli

# Set the current team scope inside the REPL
/team my-team

# Inspect runtime KPIs without Grafana
/kpi
/kpi tool_name=search

# One-shot
fred-agents-cli --agent my-agent "What is the status of cluster A?"

# Keycloak browser login
fred-agents-cli --login

# Start already scoped to one team
fred-agents-cli --team-id my-team

# Override the metrics endpoint used by /kpi
fred-agents-cli --metrics-url http://127.0.0.1:9115/metrics
```

The target pod URL is resolved from `configuration.yaml` automatically,
or overridden with `--base-url` / `FRED_AGENT_POD_URL`.

---

## Configuration

Every Fred pod uses the same two-file convention:

| File                                           | Purpose                                                            |
| ---------------------------------------------- | ------------------------------------------------------------------ |
| `.env` (path from `ENV_FILE`)                  | Secrets: API keys, DB URLs, Keycloak credentials                   |
| `configuration.yaml` (path from `CONFIG_FILE`) | App settings: port, base URL, LLM routing, observability, security |

Minimal `configuration.yaml` for a local pod:

```yaml
app:
  name: "My Agent Pod"
  base_url: "/myapp/v1"
  host: "0.0.0.0"
  port: 8010
  log_level: "info"
  limit_concurrency: 200
  metrics_address: "127.0.0.1"
  metrics_port: 9115
  kpi_process_metrics_interval_sec: 10

observability:
  tracer: logging
  metrics: prometheus

ai:
  knowledge_flow_url: "http://localhost:8111/knowledge-flow/v2"
```

Full schema: `fred_runtime.app.config.AgentPodConfig`.

When `observability.metrics: prometheus` is enabled, `create_agent_app(...)`
starts a dedicated Prometheus exporter on `app.metrics_address:app.metrics_port`
and restores the shared Fred KPI pipeline, including process and SQL pool KPIs.

Set `app.limit_concurrency: null` to disable Uvicorn connection limiting, or a
positive integer to reject excess concurrent HTTP and WebSocket connections
with `503` before application code runs.

---

## Installation

```bash
# Core library (runtime adapters, CLI, model routing)
pip install fred-runtime

# With FastAPI pod factory
pip install fred-runtime[app]
```

`fred-runtime` depends on `fred-sdk[agents]`, so an agent pod installs nothing
else to get the authoring surface. A Knowledge Base pod installs
`fred-sdk[knowledge-base]` instead and never needs `fred-runtime`.

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
    uvicorn.run(
        "myapp.main:app",
        host=config.app.host,
        port=config.app.port,
        limit_concurrency=config.app.limit_concurrency,
        reload=True,
    )

if __name__ == "__main__":
    main()
```

**`registry.py`**

```python
from fred_sdk import ReActAgent

class MyAgent(ReActAgent):
    agent_id: str = "acme.my.assistant"
    role: str = "Assistant"
    description: str = "Answers general questions."
    system_prompt_template: str = "You are a concise assistant."

MY_AGENT = MyAgent()

REGISTRY = {MY_AGENT.agent_id: MY_AGENT}
```

How to write agents and their tools: the
[fred-sdk README](https://github.com/ThalesGroup/fred/tree/swift/libs/fred-sdk).
[fred-samples](https://github.com/fred-agent/fred-samples/tree/swift/agents) is a
working pod with several agents.

---

## Related packages

| Package        | PyPI                                           | Role                                                                          |
| -------------- | ---------------------------------------------- | ----------------------------------------------------------------------------- |
| `fred-pod`     | [pypi](https://pypi.org/project/fred-pod/)     | What every pod shares — configuration, identity, naming                       |
| `fred-core`    | [pypi](https://pypi.org/project/fred-core/)    | The agents platform — stores, model providers, logging, observability         |
| `fred-sdk`     | [pypi](https://pypi.org/project/fred-sdk/)     | Authoring — agents, tools, Knowledge Bases                                    |
| `fred-runtime` | [pypi](https://pypi.org/project/fred-runtime/) | This package                                                                  |

---

## License

[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).


### Managed execution scope

Managed turns use the `space_id` validated by Control Plane, including evaluation,
HITL resume, capabilities and checkpoint/history writes. `team_id` is optional
ancestry, not a substitute for that space. Runtime skill catalog/detail reads now
require `space_id` and `agent_instance_id`, without a `team_id` query parameter.
Their person-credential and resolver consistency checks remain in place.

For an existing local database, read the [schema notes](fred_runtime/migrations/README)
before starting the pod: Alembic owns history/steering, whereas the checkpointer
owns its separate tables and refuses the old owner schema. No data conversion
from team ancestry is provided. The unused history-to-owner backfill helper has
been removed; invocation writes supply retention metadata directly.

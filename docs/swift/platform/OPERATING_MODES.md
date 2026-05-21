# Fred Operating Modes

Single reference for choosing, configuring, and understanding the two supported
operating modes for the Fred platform.

---

## At a glance

| | **Standalone** | **Full stack** |
|---|---|---|
| **Who uses it** | Developer, agent author, CI | Team deployment, end users |
| **Services required** | `fred-agents` pod only | `fred-agents` + `control-plane-backend` + Keycloak |
| **Authentication** | None — mock user injected | Keycloak OIDC + OpenFGA ReBAC |
| **Agent access** | Direct by `agent_id` | Team-scoped via `agent_instance_id` |
| **Teams** | Single implicit personal team | Multi-team, RBAC-enforced |
| **Data storage** | SQLite + in-memory | PostgreSQL (control-plane) + SQLite (runtime history) |
| **Primary interface** | `fred-agents-cli` (`make cli`) | Frontend + CLI |
| **Backend auth** | `KEYCLOAK_ENABLED=false` | `KEYCLOAK_ENABLED=true` + Keycloak config |
| **Frontend auth** | `user_auth.enabled: false` in `config.json` | `user_auth.enabled: true` + `realm_url` + `client_id` in `config.json` |

---

## Mode 1 — Standalone

Run a single `fred-agents` pod. No control-plane, no Keycloak, no teams.
This is the right mode for:

- developing and testing agents locally
- validating the LLM + SSE pipeline without any shared infrastructure
- CI unit tests and integration scenarios
- working in an airgapped or offline environment

### What runs

```
fred-agents pod  (apps/fred-agents)
  └── fred-runtime
        ├── ReAct runtime
        ├── Graph runtime
        ├── SSE streaming
        ├── SQLite history store
        └── Agent registry (all fred.github.* agents)
```

Nothing else is required.

### How to start

```bash
cd apps/fred-agents
make run         # starts the pod on the default port
make cli         # opens fred-agents-cli connected to the pod
```

Set at minimum:
```bash
KEYCLOAK_ENABLED=false       # disables auth; mock user "admin" is injected
OPENAI_API_KEY=...           # or whichever LLM backend you configure
```

### How agents are accessed

The CLI connects directly and selects an agent by `agent_id`.
On connect, the first registry entry is selected by default — currently
`fred.github.assistant`.

```
[chat] agent  : fred.github.assistant
[chat] team   : personal
[chat] user   : admin
```

You can switch agents with `/agents` and select by number.

Direct HTTP access uses the raw `agent_id` path:
```
POST /agents/execute/stream
  { "agent_id": "fred.github.assistant", "session_id": "...", "message": "..." }
```

No `ExecutionGrant` or `agent_instance_id` is required in this mode.

### Agent behavior in standalone mode

| Agent | Standalone behavior | Notes |
|---|---|---|
| `fred.github.assistant` | ✅ Works fully | Pure LLM — no external services needed. If you equip it with MCP servers via the form and those servers are unreachable, the agent answers from model knowledge and says so. |
| `fred.github.sentinel` | ⚠️ Fails gracefully | Requires OpenSearch MCP. Will report a tool connection error. **This is intentional and useful** — validates that the runtime error path and SSE `execution_error` event work correctly. |
| `fred.github.rag_expert` | ⚠️ Fails gracefully | Requires the Fred built-in `knowledge.search` tool bound at runtime. Useful for validating the declared-tool-ref error path. |
| `fred.github.test_assistant` | ✅ Always works | No LLM, no MCP. Exercises every SSE event type with pure Python. Use this to validate the chat UI without any external dependency. |

### Session and identity in standalone mode

- `user_id` is always `"admin"` (mock, injected by the no-security middleware)
- `team_id` is always `"personal"` (the implicit personal team)
- History, checkpoints, and KPI labels all carry these values consistently
- Checkpoints accumulate indefinitely — run `/purge-session` in the CLI or
  `DELETE /agents/sessions/{session_id}` to clear a session

### What is not available in standalone mode

- Team creation, membership, or permission management
- Managed agent instances (agent configuration via control-plane form)
- Session metadata sidebar (that is a control-plane concern)
- OIDC token refresh or user switching
- ReBAC access checks

---

## Mode 2 — Full Stack

Run the complete platform: agents pod, control-plane backend, and Keycloak.
This is the right mode for:

- team deployments where multiple users share agents
- validating the end-to-end managed execution path
- staging and production environments

### What runs

```
fred-agents pod  (apps/fred-agents)
  └── fred-runtime (same as standalone)

control-plane-backend  (apps/control-plane-backend)
  ├── Team and user management
  ├── Agent template discovery (polls the agents pod)
  ├── Managed agent instance CRUD
  ├── Session metadata (create, list, patch)
  └── ExecutionGrant issuance (authorizes frontend to call the pod)

Keycloak
  └── OIDC identity provider + token issuance

OpenFGA  (optional, for ReBAC)
  └── Fine-grained team membership and permission checks
```

### How agents are accessed

All frontend calls go through control-plane to get an `ExecutionPreparation`
(which includes a time-limited `ExecutionGrant`), then hit the pod directly:

```
Frontend
  1. GET  /control-plane/v1/teams/{team_id}/sessions/{session_id}/prepare-execution
       → ExecutionPreparation { runtime_url, agent_instance_id, execution_grant, ... }
  2. POST {runtime_url}/agents/execute/stream
       { agent_instance_id, execution_grant, session_id, message }
```

The pod validates the grant on every request. If the grant is missing or invalid,
the request is rejected with a `401`.

The `fred-agents-cli` also supports managed execution:
```bash
FRED_AGENT_INSTANCE_ID=<uuid>  make cli
```

### Agent instances vs agent templates

In full-stack mode, team admins do not chat directly with a template (`agent_id`).
Instead they:

1. Browse available agent templates (sourced from the agents pod catalog)
2. Create a **managed agent instance** — choosing a name, optional tuning fields
   (system prompt, MCP server selection, per-server config), and model profile
3. Users in the team chat with the **instance** (`agent_instance_id`), not the raw template

This separation lets one template serve many differently-configured instances across
teams without any code change.

### Key environment variables

**Agents pod:**
```bash
KEYCLOAK_ENABLED=true
KEYCLOAK_SERVER_URL=https://keycloak.example.com
KEYCLOAK_REALM=fred
KEYCLOAK_CLIENT_ID=fred-runtime
```

**Control-plane-backend:**
```bash
KEYCLOAK_ENABLED=true
KEYCLOAK_SERVER_URL=https://keycloak.example.com
KEYCLOAK_REALM=fred
DATABASE_URL=postgresql+asyncpg://...
FRED_RUNTIME_POD_URLS=http://fred-agents:8000   # comma-separated pod base URLs
```

See [`ENV_VARIABLES.md`](ENV_VARIABLES.md) for the full reference.

**Frontend:**

The frontend security toggle is **not** an environment variable — it lives in `frontend/public/config.json`:

```json
{
  "user_auth": {
    "enabled": true,
    "realm_url": "http://keycloak:8080/realms/fred",
    "client_id": "fred-frontend"
  }
}
```

| `user_auth.enabled` | Behaviour |
|---|---|
| `false` (default for local dev) | No Keycloak. The frontend mints unsigned local dev tokens with `admin` role. All auth code paths still run — the app is production-shaped. |
| `true` | Real Keycloak OIDC (PKCE flow). `realm_url` and `client_id` must match your Keycloak deployment. |

In Kubernetes this file is rendered from `deploy/charts/fred/templates/configmap-frontend.yaml` via Helm values — no image rebuild required. For local `make run`, edit `frontend/public/config.json` directly.

> Note: the backend `KEYCLOAK_ENABLED` flag and the frontend `user_auth.enabled` flag are **independent**. In a real deployment both must be set to `true`; in local dev both default to disabled.

---

## Decision guide

```
Are you developing or testing a single agent?
  └── YES → Mode 1 (standalone)
        └── Does your agent need MCP/tools?
              ├── NO  → works out of the box
              └── YES → run the required MCP server locally, or accept graceful failure

Are you deploying for multiple users sharing a set of agents?
  └── YES → Mode 2 (full stack)
        └── Do you need fine-grained team permissions?
              ├── NO  → Keycloak + control-plane, skip OpenFGA
              └── YES → full stack including OpenFGA
```

---

## Testing error handling in standalone mode

The sentinel and rag_expert agents intentionally require external services that
are not available in standalone mode. Their graceful failure is a **feature** —
use them to verify:

- The runtime emits a typed `execution_error` SSE event (not a silent crash)
- The CLI displays the error with the correct colour coding
- The frontend renders the error bubble rather than hanging

Run `/run error` with `fred.github.test_assistant` to trigger a deterministic
synthetic error without any external dependency.

---

## Cross-references

| Topic | Document |
|---|---|
| Execution grant lifecycle and SSE event types | [`design/RUNTIME-EXECUTION-CONTRACT.md`](../design/RUNTIME-EXECUTION-CONTRACT.md) |
| Control-plane product API boundary | [`design/CONTROL-PLANE-PRODUCT-CONTRACT.md`](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md) |
| ReBAC access model | [`REBAC.md`](REBAC.md) |
| Keycloak setup | [`KEYCLOAK.md`](KEYCLOAK.md) |
| Full deployment guide | [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) |
| Environment variable reference | [`ENV_VARIABLES.md`](ENV_VARIABLES.md) |
| Writing a new agent | [`V2_AGENT_CREATION.md`](V2_AGENT_CREATION.md) |
| CLI pattern (`make cli`) | [`CLI-CONVENTION.md`](CLI-CONVENTION.md) |

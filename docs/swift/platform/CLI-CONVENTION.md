# Fred CLI Convention

**Every Fred backend service exposes a `make cli` target backed by a `fred-{component}-cli` executable.**

This is a platform-wide design decision, not a per-component convenience.

---

## Why this matters

Fred is a distributed platform. Its value comes from the quality of the contracts between components — execution contracts, authorization grants, session identity, KPI observability. A first-class CLI attached to each backend service makes those contracts testable, debuggable, and operable without a browser, a frontend build, or a full production stack.

The CLI is the smallest possible end-to-end consumer of a service's public API. If the CLI can do it, the API is solid. If the CLI cannot do it, the API is not ready for frontend integration or production validation.

**Use the CLI to:**

- validate a backend change before wiring it to the frontend
- debug auth, team scope, session continuity, and HITL flows in isolation
- inspect production KPIs, history, and checkpoints without Grafana or a browser
- gate phase completions: if the CLI cannot exercise the flow, the phase is not done

---

## Convention per component

| Component                                 | Executable        | `make` target | Status  |
| ----------------------------------------- | ----------------- | ------------- | ------- |
| Agent execution (`fred-agents` pod)       | `fred-agents-cli` | `make cli`    | ✅ live |
| Knowledge Flow (`knowledge-flow-backend`) | `fred-kf-cli`     | `make cli`    | planned |
| Control Plane (`control-plane-backend`)   | `fred-cp-cli`     | `make cli`    | planned |

---

## `fred-agents-cli` reference

Entry point: `fred-agents-cli` (defined in `libs/fred-runtime/pyproject.toml`).

```bash
cd apps/fred-agents
make cli               # start interactive REPL against a running pod
make cli -- --help     # show all flags
```

### Slash commands

| Command                      | What it does                                                            |
| ---------------------------- | ----------------------------------------------------------------------- |
| `/help [question]`           | Print command reference, or ask a natural-language question via the pod |
| `/agents`                    | List available agent IDs                                                |
| `/agent <id>`                | Switch active agent                                                     |
| `/login` / `/login-password` | Authenticate via PKCE or username/password                              |
| `/whoami` / `/logout`        | Auth status and logout                                                  |
| `/team [team_id\|clear]`     | Show, set, or clear current team scope                                  |
| `/mode [final\|stream]`      | Show or change execution mode                                           |
| `/session <id>`              | Change current session ID                                               |
| `/session-new`               | Start a fresh session                                                   |
| `/session-info [id]`         | Show session metadata (timestamps, agents, tokens, title)               |
| `/sessions`                  | List all sessions for the current user                                  |
| `/history [--raw] [id]`      | Show conversation history                                               |
| `/checkpoints [limit]`       | List checkpoint threads                                                 |
| `/checkpoint <thread_id>`    | Inspect all checkpoints for one thread                                  |
| `/stats`                     | Checkpoint storage statistics                                           |
| `/context`                   | Show execution context summary                                          |
| `/kpi [limit]`               | Show recent `agent.turn_completed` KPI events                           |
| `/kpi prom [pattern]`        | Show Prometheus metrics snapshot                                        |
| `/audit [limit]`             | Show recent security audit events                                       |
| `/delete-session [id]`       | Delete history rows (checkpoint kept)                                   |
| `/delete-checkpoint [id]`    | Delete checkpoint (history kept)                                        |
| `/purge-session [id]`        | Delete both history and checkpoint                                      |
| `/quit`                      | Exit                                                                    |

Any text not starting with `/` is sent as a message to the active agent.

### Typical session (secured pod)

```bash
# In terminal 1 — pod running
cd apps/fred-agents && make run

# In terminal 2 — CLI
cd apps/fred-agents && make cli
# First time: /login  (browser opens, token cached at ~/.config/fred/agent-chat-session.json)
# Subsequent times: token is reused automatically
```

---

## Design rules for new CLIs

When a new Fred backend service is added, its CLI must:

1. Live in its own pod project under a `cli/` module.
2. Be registered as a `[project.scripts]` entry in `pyproject.toml` with the name `fred-{component}-cli`.
3. Expose `make cli` in the project `Makefile` with this exact form:
   ```makefile
   .PHONY: cli
   cli: dev ## Open the interactive CLI for a running {component} pod
   	ENV_FILE=$(CURDIR)/config/.env VIRTUAL_ENV= $(UV) run fred-{component}-cli
   ```
4. Support unauthenticated mode when the pod has security disabled, and Keycloak PKCE login when security is enabled, reusing `fred_core.cli.auth`.
5. Use `[cli]` as the log prefix in startup output (not the component name or "chat").
6. Be the **primary backend validation tool** for the service — not an afterthought. Every non-trivial API flow the service exposes must be exercisable through the CLI.

---

## Relationship to the test suite

The CLI is not a replacement for automated tests. It is the **manual validation gate** that sits between a backend implementation and frontend integration:

```
Backend implementation → make cli validation → integration tests → frontend cutover
```

Any phase gate that says "the backend is ready" must be reachable from `make cli` before it can be marked done.

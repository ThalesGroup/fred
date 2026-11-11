---
name: fred
description: Start local Fred components and, on request, a fred-samples pod and its test server; observe and challenge the quality of their logs and available KPIs during UI testing, without any automatic test or measurement campaign.
---

# Fred — local startup and observation

The developer drives the UI and manages Docker Compose (Keycloak, Postgres,
Temporal, OpenSearch and other infrastructure services). The assistant starts
the requested applications, reads their logs and helps with diagnosis.

## Scope and agreement

- A request to prepare or modify this skill starts nothing.
- Before starting anything, state the components, commands and directories. An
  explicit start request authorizes that scope; otherwise wait for agreement.
- Check that the developer has finished starting the infrastructure. Do not
  start, stop, rebuild or reset their Docker Compose.
- Ask before any widening: tests, business requests, KB publication,
  configuration/code changes, extra installation or long troubleshooting.
  Run neither `make test`, nor `make code-quality`, nor an automatic campaign.
- In every session, apply the quality criteria of
  [live-observability-session](../live-observability-session/SKILL.md) to the
  available logs, audits and KPIs: confidentiality at the source, concise INFO,
  cost and diagnostic value. Incomplete rewiring of Swift KPIs in Weaver does not
  exempt from reporting gaps; it does not trigger a campaign.

## Directories and components

Use the checkout chosen in the conversation, never another checkout for
convenience. Check paths, branch and repository instructions; never assume a
usual location designates the chosen checkout.

| Component | Directory relative to Fred | Command |
|---|---|---|
| Control Plane API and background tasks | `apps/control-plane` | `make run` |
| Knowledge Flow API | `apps/knowledge-flow-backend` | `make run` |
| Knowledge Flow worker | `apps/knowledge-flow-worker` | `make run` |
| Fred Agents API | `apps/fred-agents` | `make run` |
| Fred Agents capability preparation worker | `apps/fred-agents` | `make run-worker` |
| Frontend | `apps/frontend` | `make run` |

These are available commands, not a list of mandatory processes. Respect the
requested profile and components; check their dependencies in the current checkout.

## Configuration and authentication

Read `AGENTS.md` and the components' current READMEs and Makefiles before starting.
The Rust Control Plane serves the API and its background tasks in one process;
do not look for an old separate Python worker. The selected profile determines
which Python services are useful. Do not start a component only because it
appears in an old Swift scenario.

Inspect the effective configuration and prerequisites without displaying secrets.
For the Control Plane, follow `apps/control-plane/README.md`; a database migration
is not a side effect authorized by a request to read logs. For Python components,
check their current delegation and identity mechanisms. Never relax audience,
issuer, isolation or access control to get started. An authentication refusal
is to be diagnosed, not bypassed.

Measurement campaigns and token renewal tests are not part of startup.
Observation uses the current emitters/exporters and the arc42 operations
references. Do not reactivate old Swift settings or scripts without checking
their compatibility. Token lifetime changes, publications, migrations and
campaigns must belong to the requested scope.

## Before starting

1. Read the Makefile targets and their prerequisites. `make run` may install
   dependencies, and the Knowledge Flow worker may download models. Report a
   significant preparation cost before triggering it. For the frontend, compare
   the active Node with `.nvmrc` and the check in `scripts/makefiles/node.mk`;
   select a compatible version already installed before considering an install.
2. Check `config/.env` and the file named by `CONFIG_FILE`, then any Makefile
   overrides. On Docker, a checkout without `config/.env` is not prepared:
   `make docker-prepare DIR=<checkout>` from deployment-factory, with agreement.
   The `fred_weaver` database is shared between checkouts: compare migrations
   before switching.
   In the current local Compose profile, the Control Plane, Knowledge Flow and
   Fred Agents APIs use `configuration_prod.yaml`; the Knowledge Flow worker uses
   its own `configuration_worker.yaml`. Both Fred Agents processes share the same
   `.env` and YAML, with `scheduler.enabled` for the worker. Check the ports
   published by Compose and the shared Temporal namespace, without confusing
   containers' internal DNS names with addresses seen from the host.
   Read only the values needed; never display secrets or copy the whole `.env`
   into a reply. Check local destinations, authentication and API/worker
   consistency; rewrite nothing silently.
   For the frontend, check its Makefile, Vite configuration and proxies.
3. Identify occupied ports and existing processes with a read-only local
   inspection. An occupied port does not prove the right checkout is available.
   Do not kill an unknown process; ask whether to keep or replace it. Do not use
   a global "kill-stale" cleanup.

## Startup and logs

- On Docker, for an observation session, start all of Fred with
  `make fred-json FRED_CHECKOUT=<checkout>` from deployment-factory, in the
  background: same commands and ports as `make run`, JSON logs per component in
  `/tmp/fred-structured-logs/`, collected into Loki and visible to the developer
  at <http://localhost:3002/d/fred-local-logs/fred-logs>. `make fred-stop` stops
  it. Otherwise, or for a single component:
- One supervised process per component, started from its own directory, with
  the tool's persistent mechanism: `exec_command` / `write_stdin` sessions in
  Codex, a background Bash command in Claude Code. Then read the log files; do
  not assume a tool specific to the other agent.
- Keep complete stdout AND stderr in one file per component, under a unique
  session directory such as `/tmp/fred-live-<session>/`. Avoid filtering at
  capture: Temporal activity lines are useful for ingestion. Keep these files
  private. Check whether the platform collector actually reads these processes:
  a local capture of `make run` is not automatically collected by Fluent Bit or
  Loki.
- Keep a small session journal in that directory: component, checkout, command,
  session/process identifier, log, observed state. This allows resuming
  observation without starting duplicates after an interruption.
- Start the authorized processes, then read each log. Check the readiness message
  and that the process stays alive; for APIs/frontend, also check the expected
  ports. A worker does not necessarily have an HTTP port: its Temporal connection
  and polling message are the evidence sought.
- After about two minutes without readiness, give the state and the last useful
  error rather than multiplying restarts. Do not hide a failure behind a restart
  loop or change configuration without agreement.
- Give the developer a short table: ready / starting / blocked, UI URL when
  known, and log location.

## Observation during UI testing

Read new lines from ALL session processes with cursors, in small batches during
active turns and at each developer signal. Do not reread the whole history, nor
watch only the last backend started. Files keep receiving logs between turns; do
not claim to analyze them continuously when the assistant is no longer active.

For each action reported in the UI, correlate timestamps and the identifiers
present (task_id, document_uid, workflow_id, run_id). Report briefly: what was
observed, the component, the useful excerpt redacted of secrets, then any
hypothesis and the next proposed action. An absent log does not prove the action
did not happen. Read targeted code if it helps explain the traces; ask before
fixing or reproducing the action yourself.

## Samples, on request only

For WebDAV, work in the fred-samples checkout's `knowledge-bases/webdav`:

- KB pod: `make run`, with its `config/.env` and YAML. It is a Temporal worker
  without an inbound port. Also check the SDK actually installed and the checkout
  targeted by an editable install, without reinstalling it by default.
- With or without delegation, the KB pod reads its run context with its own
  identity (service account of the client bound to the definition) and writes to
  its library through the right created with the instance; no grant is expected.
  A 403 on the context signals a wrong client or a missing service role.
- Test server: read the current `make share-run` target before running it. It
  may build an image and replace an existing container: state these effects and
  ask before replacing. The requested test server is distinct from the Docker
  Compose infrastructure managed by the developer.
- Also observe `make share-logs`, the pod logs, Knowledge Flow API/worker and
  Control Plane. Do not run `make sync` / `make watch` automatically.
- `make publish` modifies the Fred catalog: propose it if the declaration must be
  created or refreshed, then wait for agreement. Do not change M2M identity to
  bypass a refusal.

For another companion, read its README/Makefile and add only the requested
processes to the same session journal. Do not add the evaluator or other
services by default.

## Shutdown

A stop instruction immediately cancels any starts/restarts still planned. If
processes have just restarted, stop them and say so; do not resume restarting on
the basis of an earlier authorization. When resuming a session, check current
PIDs, groups, ports and log destinations: an old journal does not prove a
process is still running. Check the checkout and process ownership before
reusing or replacing existing processes.

At the developer's request, cleanly stop only the processes started by this
session and verify they stopped, including their children. For a test server,
stop only the container created by this session and included in the request. Do
not stop the infrastructure or the developer's processes. Keep the logs and state
explicitly what remains running.

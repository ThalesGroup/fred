# RFC: Admin/ops agents — read-only platform-introspection capabilities + ready-made templates

**Status:** draft — pending developer sign-off; nothing implemented
**Author:** fmuller
**Date:** 2026-08-27
**ID:** OPSCAP-01
**Related docs:** `docs/swift/capabilities/AUTHORING.md`; `docs/swift/platform/REBAC.md`;
`docs/swift/rfc/CAPABILITY-SCOPE-CEILING-RFC.md` (CAPAB-SCOPE-01 — adjacent, deliberately
*not* required by this RFC); issues #2308 (ungated Prometheus MCP), #2251 (capability
packs / ceiling implementation)

---

## 1. Problem

Fred's operators are regularly asked to check things on a live deployment: "how many
sessions yesterday", "is the vector index healthy", "what does this team's storage look
like", "why is this pod restarting". Today that means logging into Postgres, OpenSearch
Dashboards, Prometheus, the object store, or the cluster by hand and typing queries.

Fred is an agent platform. It should dogfood: ship **admin agents** — agents with
read-only introspection tools over the platform's own infrastructure — that a platform
admin can chat with instead of shelling in. Constraints:

- **Heavily guarded.** These tools expose broad data. They must be invisible and
  unusable to anyone but the admins an admin explicitly grants them to.
- **Flavors.** Some admins only hold a slice of trust (e.g. KPI-only). It must be
  possible to assemble a narrower agent (e.g. "query the KPI index only, no cluster
  health") from the same building blocks.
- **Air-gap friendly.** Target environments may have no internet access and no external
  tooling (no Claude Code / codex). Everything runs inside the platform.
- **Integrated, not exposed.** Prior art exists as MCP servers on Knowledge Flow
  (`mcp-knowledge-flow-opensearch-ops`, `-prometheus-ops`, `-mcp-tabular`), but an MCP
  server mounted on a KF route is an HTTP endpoint reachable from outside the cluster
  and must therefore carry its own endpoint authz — which the Prometheus one currently
  does not (auth-only, #2308). We want tools whose only caller is the agent runtime.

## 2. Decision: pure capabilities, not MCP

Each tool family ships as a **native capability package** (`tools()` lane of
`docs/swift/capabilities/AUTHORING.md`): in-process Python tools running inside the
`fred-agents` pod. Consequences, all deliberate:

- **No new network surface.** The tools are not HTTP endpoints; there is nothing to
  forget to gate. The capability framework *is* the authorization: every capability
  defaults to `team_scope: ADMIN_GATED`, so a platform admin must explicitly enable it
  per team via the existing `/admin/capabilities` surface and CapabilitiesPage UI.
- **The admin team roster is the security boundary.** Agents are enrolled into a
  dedicated admins/ops team; `capability#can_use` is checked team-subject at
  enroll/save (403 on ungranted selection), and revoking a grant synchronously
  suspends dependent instances (`capabilities/enablement.py`).
- **MCP stays an option later** for external clients (a Claude Code instance pointed at
  Fred), but is out of scope here.

### Packaging

One **optional pip package for the whole family** (working name
`fred-capability-platform-ops`), following the out-of-tree precedent
(`libs/fred-capability-ppt-filler/`): own `pyproject.toml`; installing the wheel in
the `fred-agents` pod is the registration. The packaging unit and the grant unit
deliberately differ: the package declares **one
`[project.entry-points."fred.capabilities"]` entry per concern**, so each concern
remains an independently grantable ADMIN_GATED capability (flavors by composition,
§3.3) with its own `required_env` (fail-loudly, §3.4), while connection clients and
config helpers live once in a shared module. **Amended 2026-08-27
(PLATFORM-POSTGRES spec §3):** for a Tier B capability the *credentialed executor*
is not in the package at all — it lives in fred-runtime behind a typed
`RuntimeServices` port (first: `PlatformSqlPort`); the package owns declaration,
tools, and result shaping only. "Shared connection clients in the package" applies
to Tier A / new-backend capabilities (e.g. the Prometheus HTTP client), where the
credential is capability-specific rather than the pod's own. **Not in fred-core.** The package may
also be imported by Knowledge Flow where sharing a client makes sense (e.g. the
Prometheus HTTP client currently living in
`knowledge_flow_backend/features/kpi/prometheus_service.py`); the capability
package is then the owner and KF the consumer, not the other way around.

## 3. Security model

1. **Read-only is server-enforced, never by query parsing.** Two acceptable tiers;
   each capability's spec picks (and may offer both):
   - **Tier A — credential-level** (strongest: holds no matter what our code does):
     a dedicated Postgres role with `SELECT`-only grants; bucket-scoped read-only
     object-store credentials; a read-only OpenSearch account where supported; a
     read-only Kubernetes ServiceAccount (RBAC `get/list/watch` only, phase 2).
     Recommended for production; each spec documents the provisioning.
   - **Tier B — session-level, reusing the pod's existing credentials.** The
     fred-agents pod already holds read-write Postgres and OpenSearch credentials
     (`storage.postgres` / `storage.opensearch`, used by the history store,
     checkpointer and user store — `fred_runtime/app/context.py`), so a capability
     reusing them works with **zero extra setup**. Read-only is still enforced by
     the *server*, not by our code's judgment: for Postgres, every tool call goes
     through one shared executor that runs a **server-side prepared single
     statement inside an explicit `READ ONLY` transaction** — multi-statement
     smuggling (`"...; DELETE ..."`) is impossible by construction, and Postgres
     rejects writes regardless of the role's grants. The executor uses a
     **dedicated small pool with its own `statement_timeout`**, never the app
     engine's pool, so a heavy analytical query cannot starve the
     checkpointer/history hot path. Residual risk vs Tier A: a future tool
     bypassing the shared executor — a small, auditable surface (one helper, every
     tool must go through it).
   - Query validators (like tabular's `validate_read_query`) are welcome as
     defense-in-depth but are **never the guarantee**. A tool family where neither
     tier can be achieved is skipped, not shipped softened.
2. **Scoping lives in admin-set capability config, enforced by tool code.** Example:
   the OpenSearch query capability takes an `indices` config field (list of index
   patterns); its tools refuse anything outside it. Because the client code is ours and
   in-process, the pin is structural — no reliance on OpenSearch security plugins.
   This deliberately does **not** depend on CAPAB-SCOPE-01: these tools have no
   per-user rights dimension; the config *is* the ceiling, and only the admin team's
   editors can change it.
3. **Flavors by composition.** Narrow concerns are separate capabilities (e.g. cluster
   health split from index query), so a "KPI admin" agent = the query capability
   configured on the KPI index, nothing else. A "full ops" agent selects them all.
4. **Secrets via environment variables (Tier A / new backends).** Each manifest
   declares `required_env`; pod boot fails loudly (`MissingRequiredEnvError`) when
   one is missing. Operators set them in the `fred-agents` Helm values (which also
   implies: the fred-agents pod gains the network path + credentials to the
   backend — a chart/NetworkPolicy change per capability). A Tier B capability
   reusing the pod's `storage.*` config may declare no `required_env` at all —
   zero-setup is the point of that tier. Capability code is trusted platform code;
   plain `os.getenv` is fine.

## 4. Capability list (priority order — one spec per capability, to come)

The concrete design of each capability (tool surface, config fields, env, scoping)
is **deliberately not specified here**. Each capability gets its own short spec in
`docs/swift/rfc/admin-ops-capabilities/`, designed and validated individually by
the developer before its implementation issue opens. This RFC fixes only the
cross-cutting decisions (§2 packaging, §3 security model, §5 templates).

Wish list, in priority order:

**Questions on platform data** (e.g. "what's the mean member count per team?"):

1. Postgres — **spec written and validated 2026-08-27:**
   `admin-ops-capabilities/PLATFORM-POSTGRES.md`
2. OpenSearch (KPIs)
3. OpenFGA
4. Prometheus

**Bug identification:**

5. Logs (possibly just the OpenSearch capability pointed at log indices, if
   application logs land there — to settle in its spec)
6. Code (see open question §9.2)
7. Kubernetes (phase 2 — see open question §9.1)

**Bonus:**

8. Content store (S3/GCS/MinIO…)

Shared rules every spec inherits unless it argues otherwise: `kind="tool"`,
default `team_scope` (ADMIN_GATED), `tools()` lane only (execution-model-agnostic),
no router, no owned tables, no chat parts in v1. Every tool output is size-bounded
(rows/hits/bytes caps — config-exposed only where an admin genuinely needs the
knob; hard-coded harness constants otherwise, per the Postgres spec) — these
results enter an LLM context. **Minimal tool surface** (2026-08-27): roughly one
query tool plus one discovery tool per data source; anything a single query can
express is not a tool.

## 5. Ready-made agents

A ready-made admin agent is **a template**: a `ReActAgentDefinition` in
`apps/fred-agents/fred_agents/registry.py` whose ready-made part is exactly (a) a
system prompt and (b) a default capability selection. This mechanism exists today
(`general_assistant.py` is the precedent):

- system prompt: `system_prompt_template` from a markdown file **plus** a
  `FieldSpec(key="prompts.system", type="prompt")` so admins can edit it per instance
  (overlay applied at `agent_app.py:1280`);
- default capabilities: `default_mcp_servers` (already the generic default-capability
  list — native capability ids are valid entries), projected as
  `default_capability_ids`.

Templates are themselves ADMIN_GATED capabilities (`agent__{runtime}__{agent}`), so
they are invisible to every team until granted. After enrollment the instance's
prompt, capability selection, and per-capability config all remain editable through
the normal agent form.

Proposed templates:

1. **`fred.github.platform_ops`** — "Platform operations assistant". Defaults: all
   shipped ops capabilities (each capability WP appends itself). Prompt: diagnose
   deployments; never speculate when a tool can answer; aggregate in the query
   rather than fetching raw rows. (2026-08-27: the earlier "always state which
   query produced a number" rule was dropped — per-query attribution already lives
   in the session history's tool calls; see PLATFORM-POSTGRES §5.)
2. **`fred.github.kpi_analyst`** — "KPI analyst". Defaults: the OpenSearch query
   capability only (admins configure it on the KPI index). Demonstrates the narrow
   flavor.

### Required UI fix (blocking for "ready-made")

The agent form currently discards template defaults: on template pick it resets the
selection to `[]` (`AgentFormModal.tsx:263`) and always submits an explicit array, so
`default_capability_ids` never take effect through the UI. Fix: initialize the form
selection to `default_capability_ids ∩ (capabilities the team can use)`, matching the
backend's `capability_ids: null` semantics (`product/service.py:1384`). Small,
self-contained frontend change; benefits every template, not just these.

`MCPServerRef.locked` is declared but unenforced today; enforcing it is explicitly
**out of scope** — the enrolling admin owns the config.

## 6. Alternatives considered

- **MCP servers on Knowledge Flow** (status quo lane). Rejected as the primary
  vehicle: each server is an externally reachable endpoint that must carry its own
  authz (the Prometheus one currently doesn't — #2308), and the tools should be
  usable in deployments where nothing but Fred itself is available. The existing KF
  ops MCP servers stay as-is for now; whether to retire them in favor of these
  capabilities is an open question (§9).
- **One monolithic "admin tools" capability.** Rejected: flavors require composition,
  and per-concern enable/disable is exactly what the capability admission model gives
  for free. The *packaging* does collapse to one pip package (§2) — it is the grant
  unit that stays per concern.
- **Waiting for CAPAB-SCOPE-01.** Not needed: no per-user rights dimension here; the
  admin-set config is the ceiling and the admin team roster is the trust boundary.

## 7. Delivery plan

Each work package is its own issue + PR (consolidation-phase scope discipline):

- **WP1** — agent-form fix: initialize capability selection from template defaults.
- **One WP per capability**, following the §4 priority order (Postgres first). Each
  WP is gated on its spec in `docs/swift/rfc/admin-ops-capabilities/` being written
  and signed off. The first capability shipped also proves the whole chain
  end-to-end (package → entry point → admission → grant → enroll → chat) and adds
  the first template (§5); the OpenSearch query capability adds `kpi_analyst`.
- **WP-hardening** (separate ticket, not blocking the capability WPs): make the runtime-binding
  endpoint refuse suspended instances — `GET /teams/{team}/agent-instances/{id}/runtime`
  (`product/api.py:1355`) checks `binding.enabled` but not `suspension_reason`, so
  pod-direct callers (CLI, OpenAI-compat) can execute a suspended instance that the
  frontend's `prepare_execution` preflight would refuse with 409.

Docs: each shipped package gets a row in the capability docs per AUTHORING.md; no
frozen-contract change is expected (capabilities and templates are additive; the UI
fix is frontend-only).

## 8. Deployment impact

- `apps/fred-agents` image/deps: the `fred-capability-platform-ops` package
  installed (optional extra).
- Tier B capabilities (Postgres, OpenSearch reusing `storage.*`): no new secrets,
  env, or NetworkPolicy — the pod already has the path and credentials.
- Tier A / new backends (Prometheus, object store, K8s, or Tier A overrides):
  per-capability env secrets in Helm values; NetworkPolicy allowing fred-agents →
  that backend as enabled.
- Postgres read-only role provisioning (Tier A override) documented in the
  deployment guide.

## 9. Open questions

1. **Kubernetes boundary.** `fred_sdk/contracts/execution.py:472` declares K8s
   concerns out of Fred's scope. That rule targets Fred *implementing* infra
   (discovery/ingress), not reading the API — but the team should confirm before the
   k8s capability's spec is written.
   The chart's dormant kubeconfig hook (`configmap-kube.yaml`) could be revived.
2. **Codebase reading.** The original wish list includes "explore/read the code".
   `mcp-web-github-readonly` is declared in `mcp_catalog.yaml` but its inprocess
   provider was never implemented (dead entry). Options: implement it, add a
   `code-reading` capability over a bundled/mounted source tree (air-gap friendly), or
   drop it from v1 and delete the dead catalog entry. Leaning: drop from v1, delete
   the dead entry as consolidation.
3. **Fate of the KF ops MCP servers.** Once the capabilities ship, do
   `mcp-knowledge-flow-opensearch-ops` / `-prometheus-ops` stay (for external MCP
   clients) or retire? If they stay, #2308's gating must land regardless.
4. **Package location.** ~~In-tree `libs/fred-capability-*` (like ppt-filler /
   writable-document) vs a separate repo. Leaning in-tree.~~ **Resolved
   2026-08-27:** in-tree, `libs/fred-capability-platform-ops/` (PLATFORM-POSTGRES
   §2) — proven precedent, no new CI/release infrastructure during consolidation.
5. **Generic connectors vs Fred-scoped introspection.** Should a capability like
   Postgres be Fred-scoped (operator-provisioned read-only DSN via env, per §3.4)
   or a generic self-service connector where any team supplies its own credentials
   in the agent config (`secret` FieldSpec exists in fred-sdk)? Generic is a real
   user feature (connect your own database without asking the platform team) but
   changes the trust model: secrets move from pod env into the agent-config store
   (encryption at rest, masking, platform-export leakage all to check), and the
   §3.1 credential-level read-only guarantee becomes the user's responsibility.
   Possible mitigations for a generic flavor: a config-time privilege probe that
   refuses to save over-privileged credentials (advisory only — grants change
   after validation), and server-side enforcement by running every query in a
   `READ ONLY` transaction / `default_transaction_read_only=on` session, which
   holds regardless of the role's grants. To settle per capability in its spec;
   §3 stands as the default until a spec argues otherwise.
   **Resolved for Postgres (2026-08-27):** Fred-scoped Tier B, pod credentials
   behind `PlatformSqlPort` (PLATFORM-POSTGRES §1) — a generic bring-your-own-DSN
   connector is out of this family's scope; if wanted later it is a separate
   capability with its own trust-model review.

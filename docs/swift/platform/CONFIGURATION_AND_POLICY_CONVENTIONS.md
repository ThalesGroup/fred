# Fred Configuration And Policy Conventions

This page is the operational contract for developers working on Fred backends.

> [!IMPORTANT]
> **Access-control convention for all backends:**
> Keep the distinction explicit between global app RBAC roles (`admin`/`editor`/`viewer`) and team ReBAC relations (`team_admin`/`team_editor`/`team_analyst`/`team_member`).
> Team-level write operations must rely on team relations, not on app role shortcuts.
> A team's first `team_admin` is granted by the platform-admin-gated team-bootstrap action (`POST /teams`, RFC §28), not by post-install automation guessing at ownership.

It answers two practical questions:

1. How startup configuration is loaded.
2. How policy decisions are configured and enforced.

No extra conventions should be introduced outside this contract.

## Backends Covered

- `apps/fred-agents` (agent execution pod)
- `knowledge-flow-backend`
- `apps/control-plane-backend`

All three follow the same startup configuration contract.

## Startup Configuration Contract (Same In The 3 Backends)

At startup, each backend must do exactly this:

1. Load environment variables from `ENV_FILE` (default: `./config/.env`).
2. Resolve YAML configuration from `CONFIG_FILE` (default: `./config/configuration.yaml`).
3. Parse the YAML into the backend-specific pydantic `Configuration`.
4. Log identifier-free load status; never emit selected paths, secret names,
   configuration contents, or raw parser/exception details into log sinks.

Item 4 is the requirement, not a description of current behavior: the shared
helper and the backend startup paths still emit the resolved file paths. The
gap is outstanding work and is not a licence to log paths in new code.

The shared helper used by backends is:

- `fred_core.ConfigFiles`

This is intentionally opinionated so DevOps has one rule only for startup config across services.

## Environment Variables (Do Not Rename)

These names are fixed for all backends:

- `ENV_FILE`
- `CONFIG_FILE`

Do not add service-specific aliases for config path loading.

Complete env inventory and ownership rules are documented in:

- [`docs/ENV_VARIABLES.md`](./ENV_VARIABLES.md)

## Expected Runtime Behavior

- `make run` starts API using the same `ENV_FILE/CONFIG_FILE` contract.
- `make run-worker` starts worker using the same `ENV_FILE/CONFIG_FILE` contract.
- API and worker logs report configuration load status without file paths or
  other system identifiers. Keep operational inspection separate from log sinks.
  This is the required behavior; the current startup paths still emit the
  resolved file paths.

## Policy Configuration In Fred

Fred policy behavior must come from files, not hardcoded values.

Current policy sources:

- Model/routing policy catalogs (agentic + knowledge-flow usage paths)
- Runtime-pod request policy in `apps/fred-agents` configuration, including
  `app.max_chat_input_chars` for the deployment-scoped chat-message limit
- Conversation lifecycle policy catalog in control-plane:
  - `apps/control-plane-backend/config/conversation_policy_catalog.yaml`
  - The same file also carries `wiki_policies` (WIKI-05: how long an
    unanswered wiki proposal may sit before the lifecycle sweep rejects it) —
    not conversation-shaped, but one catalog file/load path was judged not
    worth splitting for a single platform-wide duration.

`app.max_chat_input_chars` is loaded once into `PodAppConfig`, enforced by the
runtime, and published read-only to managed chat through runtime-template and
execution-preparation metadata. It is not a database setting or a live
platform-admin preference.

When implementing behavior (for example purge delays), read from policy config and apply.
Do not embed retention windows or team-specific rules in code.

## Platform Feature Gates

Platform-wide staged features use typed boolean fields under
`platform.frontend.feature_flags`. Each feature has its own flag, and a missing
value is treated as `false`; one unfinished feature must never enable another.
Control-plane owns the value and publishes it through the authenticated
frontend bootstrap.

Frontend code consumes these fields through the shared feature-flag hook and
gate rather than repeating bootstrap lookups. A feature with backend routes or
gateway paths must also fail closed at those boundaries. Hiding a frontend
control is not authorization, so the normal permission checks still apply when
the feature is enabled.

`enableApplications` is the team-applications gate and defaults to `false`.
While it is off, application routes, catalogs, administration controls, and
both the `/apps` and `/app-services` gateway paths are unavailable. Registered
entries and existing team grants stay configured but dormant, so enabling the
flag needs no re-registration and no re-granting.

The control-plane field is the single authoritative deployment setting. The
Fred Helm chart derives the frontend container's
`FRONTEND_ENABLE_APPLICATIONS` value from it so the backend and gateway cannot
be configured independently through chart values. The environment variable is
still accepted directly for local Vite and standalone-container parity, where
the operator must keep it aligned with the control-plane field; it also defaults
to `false`.

## Contributed Identity Naming

Everything a contributor adds to a deployed Fred — an agent, a Knowledge Base,
an application — is named with **dotted segments, under a prefix that
contributor owns**:

```
fred.github.assistant          fred.github.sql_expert
fred.samples.hello_graph       fred.samples.local-folder
thales.prism.triage
```

Read left to right: the project, then where it comes from, then the thing.
`fred.github.*` is the open-source core; `fred.samples.*` is the samples
repository; `thales.*` is an in-house component. Provenance is in the name, and
nobody has to look it up.

This is how Java packages, Maven `groupId`s and npm scopes work, for the same
reason: **uniqueness comes from owning the prefix, not from a registry someone
has to keep.** Two contributors cannot collide without claiming the same
prefix, so cloudops never arbitrates a name.

### Ownership is a prefix, not a segment to parse

A confidential Keycloak client owns a prefix. Anything named under it belongs
to that client, and nothing else may write there. There is no separator to
find and no boundary to compute — Fred checks that a name starts with a prefix
the caller owns.

That is why the names need no `__`. It existed to mark where a publisher ended
and a thing began; with an owned prefix there is nothing to mark.

### Characters

Lowercase letters, digits, `-` and `_` inside a segment; `.` between segments.
The single underscore is deliberate: real identifiers already use it
(`sql_expert`, `hello_graph`, `bank_transfer.graph`).

**A double underscore is forbidden.** It carries no meaning now that names are
not split, and it is the one sequence that made older composite forms
ambiguous.

### The version is not in the name

A declaration carries its own `version`. A redeployment replaces an entry, it
never creates a second one. Maven coordinates end in a version; these do not.

### The Kubernetes namespace is not the name

Fred sees no part of the cluster. Two Deployments in two Kubernetes namespaces
carrying the same prefix are one contributor to Fred; a Deployment renamed or
scaled to ten replicas is unchanged. Identity travels in the token and the
declaration.

### What this rule governs, and what it does not

It governs **the name a contributor chooses**. It does not govern the keys Fred
builds internally — the shared administration catalog, for instance, prefixes
its dictionary keys per kind so an agent and a tool cannot collide in one flat
dict. Those keys are implementation details, they differ by kind, and a
contributor neither writes nor reads them.

Concretely: `fred.github.assistant` is the name, and it is already correct.
That the catalog stores it under a longer internal key is not a naming
question.

### What a contributor hands over, and what cloudops does

A contributor delivers the **image**, the **prefix** it claims, and the **list
of what it exposes**.

Cloudops creates one confidential Keycloak client per prefix, sets the prefix
and the client credentials in the Deployment's environment, and deploys. The
only check is a lookup, never a judgement: *is this prefix already owned by a
different client?*

## Application Registration

Applications are registered in deployment configuration, not built into Fred.
Each one ships as its own UI container image, and optionally its own API, built
and released by the team that owns it. Fred compiles no application code, so
there is no manifest, no generator, and no generated artifact to keep in sync.

Registration has two halves, one per process. `app_id` is the only key they
share, it must match across them, and its shape follows the naming rule above —
a dotted name under a prefix its contributor owns, such as
`fred.samples.document-triage`:

- **Control plane** — `platform.application_sources[]`, expressed like
  `platform.runtime_catalog_sources[]`. Each entry carries `app_id`,
  `ui_prefix`, `version`, `icon`, localized `display_name`/`description`, and
  `enabled`. It owns the catalog the API returns, exposes `app__<app_id>` as
  the flat catalog and administration id, and maps that entry to the OpenFGA
  authorization object `app:<app_id>`. It registers no proxy upstream at all.
  `ui_prefix` is browser-facing: exactly
  `/apps/<app_id>` while the UI is served from Fred's origin — config load
  rejects any other own-origin path, because the gateway routes on that
  segment and nothing else can reach the application — or an absolute `https`
  URL once the UI is served from its own origin. Nothing may assume the
  former.
- **Frontend gateway** — `FRONTEND_APPLICATIONS_JSON`, a JSON array of
  `{app_id, ui_upstream, service_upstream?, service_required?}`. These are the
  server-side addresses nginx proxies to and they never reach the browser. The
  two halves are separate because the control plane never proxies and the
  gateway never authorizes.

Because the halves are separate, an `app_id` registered in one and not the
other is not detected at startup. Forward (control plane only): the
application appears in the catalog and its frame 404s. Reverse (gateway only):
the prefixes proxy for an application no team was ever granted — the gateway
performs no authorization of its own, so keep the gateway list a subset of the
catalog. In the current implementation, `enabled: false` withdraws an application
from the catalog but leaves its gateway routes serving; remove both halves to
retire one.

**Current scope:** configuration registers enabled applications using the dedicated
`app` authorization type and existing entitlement controls. Registration alone
does not grant a team access. There is no app-wide active marker, lifecycle
database or reconciliation command to initialize.

**Lifecycle gap:** `enabled: false` hides a catalog entry; removing an entry
withdraws registration from the loaded catalog. Neither action guarantees
global denial by a directly reachable first-party backend or deletion of stored
grants, denies or default-on. Re-adding the same identifier can reuse surviving
permissions. Use existing entitlement revocation and route restrictions when
access must be withdrawn; removing catalog and gateway entries is not proof
that all authorization state has been erased.

Global Deactivate/Activate/Delete belongs to a future shared lifecycle design
for all or most applicable ReBAC types. Its authority, ownership, cleanup,
recovery and rollout semantics are not selected here. No new lifecycle UI/API
is included. See [the ReBAC guide](REBAC.md) and
[the deferred RFC scope](../rfc/FRED-APPLICATION-HOSTING-RFC.md#6-deferred-shared-resource-lifecycle).

Neither half carries a token, credential, arbitrary header, or raw HTML.
Registration is routing and catalog configuration, not a secrets channel.

Container startup rejects duplicate ids and unsafe URLs, and the gateway
refuses to start when a `service_required` application has no
`service_upstream` — a permanent 503 is a deployment mistake, not a runtime
state to serve. That rule lives in the gateway alone, since it is the process
that would serve the 503. A UI-only
application simply omits `service_upstream`: Fred starts, `/apps/<app_id>/`
serves, and `/app-services/<app_id>/...` returns a generic 503. Unknown ids
return 404 in both namespaces, as does everything under either prefix while
the feature switch is off.

## When Adding A New Backend

Use the same startup contract immediately:

1. Use `ConfigFiles` for env/config path loading.
2. Keep `ENV_FILE` and `CONFIG_FILE` as-is.
3. Parse into local pydantic config model.
4. Log identifier-free configuration load status, not loaded paths or raw errors.

If this contract cannot be followed, document the reason in this file before merging.

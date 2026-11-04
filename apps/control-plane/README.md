# control-plane

Fred's service for spaces, folders, documents and their authorization. Its design,
invariants and decisions are in the architecture dossier:
[docs/architecture](../../docs/architecture/README.md). This file says how to work on it. Use the [source map](src/README.md) to locate a feature.

## Develop

Same targets as the other apps (`make help` lists them). Building needs `protoc`;
`PROTOC` defaults to `~/bin/tools/protoc/bin/protoc`.

Rust packages share the repository-root Cargo workspace and `Cargo.lock`.
Authentication and platform-role reads come from the internal
[`fred-rust-sdk`](../../libs/fred-rust-sdk/README.md); Control Plane retains schema
and role-mutation ownership. Docker builds use the repository root as context.

```
cp config/.env.template config/.env   # once: the four secrets
make run                              # http://localhost:8222/control-plane/v1
make test                             # offline unit tests
make test-integration                 # throwaway Postgres and Keycloak containers
make test-lifecycle-temporal          # disposable SQL/Temporal worker recovery
make code-quality                     # model parity + clippy + rustfmt
make -C ../../docs/architecture check # the dossier still matches the code
```

## Organization supervision (API only)

The existing Control Plane serves organization totals and team detail, gated by
organization attachment. The [supervision contract](../../docs/architecture/A8-organizations.md#organization-supervision)
defines counters, privacy boundaries, pagination and failure behavior; the
[read budget](../../docs/architecture/09-quality.md#organization-supervision-read-budget)
documents SQL costs. The [HTTP catalogue](../../docs/architecture/A2-manager-contracts.md#organization-supervision-api)
is generated from the handlers. There is no supervision UI or separate service.

## Embedded Rust agent

The same process serves `POST /control-plane/v1/agents/execute/stream` (under the
configured base URL). It uses the existing authentication and consent checks and
streams Fred runtime events. Managed instances use the common inference admission
and Rig; direct `agent_id: "fred.github.ralph"` remains a fixed demonstration. See the
[agent library](agent/README.md) for the contract and current integration limits.
No additional server or deployment is required.

## From scratch (fred-deployment-factory)

**Host run, after `make docker-up` or `make k3d-up`:**

With `DATABASE_URL` pointing to a fresh control-plane database, initialize the
complete schema before starting the API:

```sh
cargo run --locked -- initialize-schema
make run
```

API startup only verifies the installed schema fingerprint. The explicit
initialization command creates the schema atomically, or does nothing when the
same schema is already installed. It refuses an incompatible database.

**In the cluster, after `make k3d-up`**, from fred-deployment-factory:

```
make k3d-app APP=fred DIR=../fred            # build, import, sync
make k3d-app-validate APP=fred DIR=../fred   # lint and render only
make k3d-logs SVC=control-plane-backend
```

Use `ENV=secondary` for this checkout's local profile. It deploys
`control-plane-backend`, `knowledge-flow-worker` and `frontend`; HTTP and background
tasks run together as `control-plane serve`. See [the profile](../../deploy/k3d/README.md).
Open Fred and check the connected SSO identity. Enter the installation bootstrap secret
to activate platform administration for that account, then accept the CGU before
using protected operations. Status reads do not create a local profile or consent.
See [independent platform initialization](../../docs/architecture/A6-security.md#independent-platform-initialization). The local service uses `FRED_BOOTSTRAP_TOKEN` from `config/.env`.
The k3d Fred values read the cluster secret `fred-secrets` key
`CONTROL_PLANE_BOOTSTRAP_TOKEN`; use the value supplied by your deployment.

The root is platform admin and has no organization membership. Open
**Provisioning**, import the ZIP built below, then sign out and sign in as an
imported user. That person accepts their own CGU and sees their declared spaces.
There is no automatic personal space or default-team enrollment.

`app.gcu_version: v1` enables this step in the reference and k3d configurations.
Changing the version requires everyone, including root, to accept again. Publish
the corresponding frontend `gcu.<language>.md`/`gcu.md` assets with the version;
`null` disables the gate. Existing Python consent and bootstrap records are not
manager consent or bootstrap records.

## Commands

| Command | Purpose |
| --- | --- |
| `control-plane serve` | HTTP API and its background tasks (default) |
| `control-plane discover-agents` | Describes the embedded agent and public templates from enabled configured runtimes; JSON output, no SQL or enrollment |
| `control-plane initialize-schema` | Creates the complete schema from `DATABASE_URL`; repeatable on the same schema, refuses incompatible history |
| `control-plane generate-openapi` | Prints the HTTP contract, without configuration or services |
| `control-plane generate-config-schema` | Prints the configuration JSON Schema |
| `control-plane processing-schema` | Prints the wire contracts shared with the Knowledge Flow worker |
| `control-plane register-local-user <weaver-user-id> <username>` | Explicitly registers a known identity in the local directory, without roles or consent |
| `control-plane import-provisioning <bundle.zip> --token-file <path>` | Authenticated additive import ([below](#import-a-provisioning-bundle)) |

### Admit a user with the local directory

With `security.user_directory: local` (required for generic OIDC), a deployment
operator explicitly registers the identity before an administrator assigns its
first role. Use the canonical Weaver UUID returned by the person's authenticated
`GET /me/onboarding` and the exact username verified with the identity provider.
For non-UUID OIDC subjects, this Weaver ID is different from the provider's raw
subject; do not substitute the username or compute another mapping.

```sh
control-plane register-local-user <weaver-user-id> <username>
```

The command uses the usual `CONFIG_FILE` and deployment database credentials, like
`initialize-models`; it requires enabled authentication and the local directory.
It reuses `user_identity`, creates no provider account, role, personal space or
CGU acceptance, and refuses to replace an existing subject's different username.
Replaying the same registration preserves the profile. The administrator then
uses the existing organization governance or role-grant API/UI. Only after this
grant can the person accept CGU and enter Weaver. Merely signing in with a Swift
SSO identity never performs this registration.

## Discover agent definitions

`control-plane discover-agents` loads the usual `ENV_FILE` and `CONFIG_FILE`,
includes the embedded `control-plane` catalog without a network request or source
configuration, then calls each enabled `platform.runtime_catalog_sources` entry:

```yaml
platform:
  runtime_catalog_sources:
    - runtime_id: fred-agents
      base_url: http://localhost:8000/fred/agents/v2
      enabled: true
```

From `apps/control-plane`, run `cargo run --locked -- discover-agents` after
starting fred-agents. The runtime's public `GET /agents/templates` endpoint needs
no bearer. Output is a JSON array of `{runtime_id, templates}`; template payloads
retain tuning, capability metadata and additional runtime fields. Internal
(non-public) templates are excluded. Disabled sources are not contacted; an
omitted platform configuration yields only `control-plane`, with one `fred.github.ralph`
template of the same name, version `0.1.0`. Its direct demonstration path replies
`Hello world!` without an LLM or data access. The managed path described below
requires an admitted instance and local inference provisioning. Its `kind` is `static`: the Rust discovery field
is a free string, and no ReAct or Graph engine runs this fixed response.
`control-plane` is reserved: configuring an external source with that identifier
is rejected, even when disabled.

The existing Administration Console -> Features -> Agents tab reads this same
catalog through `GET /control-plane/v1/organizations/{organization_id}/agents`.
Admission, a direct role in that organization, active lifecycle and `can_manage` on an
organization are required; neither organization attachment alone nor platform
roles bypass this check. The page reads projected template identities and their organization defaults.
Its existing switch writes `PUT /organizations/{organization_id}/agents/{agent_id}/default-on`.
The default starts off and is stored in `agent_template_policy`. No enrollment or
instance state is inferred. The write reuses platform/organization locks after discovery; no
runtime call holds a SQL transaction. Templates declaring tool dependencies cannot
be enabled by this initial integration. The supplied local configuration disables the
external fred-agents source; with no enabled external source the embedded catalog
requires no fred-agents process. An explicitly enabled source still fails the
whole discovery if unavailable.

This operator command uses a 10-second timeout per source and exits with an error
if any source fails, without printing a partial catalog. It does not start the API,
connect to SQL, persist definitions or enroll instances. `serve` does not
poll runtimes. This command does not enroll or execute agents.

## Pod skills and local offer ceilings

Skills are pod-owned offers in the existing capability inventory (`kind: skill`,
ID `skill:<canonical-name>`). Instructions are never stored in Control Plane or
accepted from the browser. Organization authorizations remain in the existing
capability policy. New skill offers are initially denied. Skill refresh uses the
same source configuration, observation transaction and diagnostic path as tools.
Unreachable/unavailable sources retain the last known offers and decisions;
a successful complete catalog marks removed offers as withdrawn.

Migration `0005_pod_skills_and_local_offers.sql` adds source skill diagnostics and
the shared team/project restriction tables. No local policy means inheritance;
`restricted=true` with no permissions means deny all. Every ancestor ceiling
must allow an offer. Reset preserves a monotonically increasing revision, so a
stale PUT cannot undo a later decision. SQL uniqueness/FKs retain source identity; space
cascades own local cleanup; mutations use the existing organization lock.
No runtime call is made inside the policy mutation transaction.

`GET /spaces/{space_id}/capability-policies` and revision-checked
`PUT /spaces/{space_id}/capability-policies/{runtime_id}` require direct Manage in
the team/project, without requiring Read or granting rights in a child. Personal
spaces follow the organization ceiling. Tools and skills use the same
`agents::enablement::usable` rule. Admission loads only the target ancestry.
Project agents/chat use the existing direct roles; organization authorization
is still a ceiling. No prompt publication/editor behavior is added to projects.

Preparation projects only eligible ReAct/Deep skills and the source preview URL.
Public runtime GET provides metadata without inference/title allocation. Private
execution POST carries the admitted skill snapshot alongside inference. Runtime
checks source revision and summary identity before loading; replicas must serve
matching content. A new turn or resume observes current policy while history
remains intact. Embedded Ralph and graph agents cannot load skills.

See the [operator note](../../deploy/release-notes/changes/weaver-pod-skills-and-space-ceilings.md)
for rollout/rollback and `tests/support/pod_skills.rs` for disposable SQL upgrade,
concurrency, isolation and execution-preparation proofs. These tests do not
replace a deployed k3d acceptance journey.

## Platform model inventory and organization administration

`platform.model_sources` defaults to `[]` in the schema. The host development
configuration and checkout-owned k3d overlay opt into the Mistral test source;
see [the local model setup](../../deploy/k3d/README.md#models-for-local-testing).
`serve` applies these non-secret approvals to SQL after checking the schema, then
runs the bounded organization initialization below. Organization APIs expose only
assigned sources and persist explicit choices. There is no background model polling. The internal `configure_sources`,
`refresh` and `inventory` operations remain available to trusted Rust callers;
`refresh(pool, source)` requires the exact persisted platform configuration and
carries no user authorization. Administrative routes instead own the claim and
publication transactions and reuse that same M1 discovery adapter.

Example of a **disabled, fictitious** source (no credential value is provided):

```yaml
platform:
  model_sources:
    - source_id: example-gateway
      revision: 1
      enabled: false
      discovery_url: https://catalog.example.invalid/v1/models
      inference:
        provider: openai
        api_root: https://inference.example.invalid/v1
        credential_binding: example-gateway-inference
      visibility_scope: example-account-namespace-all-models
      authentication:
        mode: bearer
        secret_env_var: EXAMPLE_MODEL_DISCOVERY_TOKEN
        provider_scopes: [provider-list-scope]
        authority: discovery_only
      qualification: mixed_capabilities_v1
      complete_inventory_guaranteed: true
```

### Initialize organization models once

`platform.organization_models` declares exact existing organization names (the same
PostgreSQL lookup as provisioning), explicit source IDs and exact offer keys. It
never creates an organization. This fictitious example assumes the two separately
approved, enabled sources have successfully discovered the named chat models:

```yaml
platform:
  organization_models:
    - organization: Example Research
      sources: [research-account, shared-gateway]
      permitted:
        - {source_id: research-account, upstream_model_id: chat-v1}
        - {source_id: shared-gateway, upstream_model_id: backup-v2}
      default: {source_id: research-account, upstream_model_id: chat-v1}
      fallback: {source_id: shared-gateway, upstream_model_id: backup-v2}
      reasoning_enabled:
        - {source_id: research-account, upstream_model_id: chat-v1}
    - organization: Example Support
      sources: [support-account]
      permitted: []
      default: null
      fallback: null
      reasoning_enabled: []
```

Different provider accounts require different `source_id` values even at the same
URL. Sharing a source with two organizations requires two explicit assignments.
At most 64 organizations, 64 sources per organization and 4096 permitted offers
are accepted. Reasoning requires a permitted, source-reported reasoning-capable
offer. A missing or unavailable model fails initialization; no substitute is picked.

Deployment order:

1. Provision existing Kubernetes Secrets/environment references and runtime-local
   inference bindings; initialize the schema through the deployment Job.
2. Start Control Plane with platform source approvals and organization declarations.
   The initial pass defers missing organizations, with a diagnostic.
3. Provision organizations through the existing organization API, Provisioning UI
   or `import-provisioning` CLI. After its commit, the caller runs a separate model
   initialization pass; the Swift bundle format does not contain model settings.
   The k3d overlay explicitly declares Acme and Globex, so the demo import requires
   no additional model manipulation in the UI.

For existing organizations, `serve` applies pending declarations on startup. For
recovery or deployment automation after external organization provisioning, run
`control-plane initialize-models` with the same `CONFIG_FILE` and environment as
Control Plane (for k3d: `kubectl exec deployment/control-plane-backend --
control-plane initialize-models`, with the deployment context/namespace). This trusted operator command uses deployment database credentials, not a
browser token, starts no service and requires every declared organization to exist.
Each pass has a 120-second deadline; discovery retains its five-second per-source
limit and runs outside transactions. This is initialization, not ongoing YAML sync.

**Initialize once, preserve afterwards.** Per organization, assignments, initial
policy and completion receipt commit together under the existing organization lock.
A successful replay performs no discovery and changes no decisions. UI edits,
including an empty policy, survive restart. A separate durable receipt also remembers
an administered policy after deletion; removing a policy or assignment cannot make
the seed recreate it. Removing YAML is not revocation. Source revision changes,
credential rotation and disabling remain handled by `configure_sources`, independently
of the receipt. Keep identical declarations across replicas; a concurrent refresh
may report `model_refresh_superseded`, which is safely replayable.

Every model permission references an explicit organization source assignment from
creation. The foreign key is validated in the initial schema. Already administered
policies (including empty or deleted policies) remain protected from YAML reseeding;
there is no migration of historical model decisions.

Failures identify the declaration index and a fixed diagnostic such as
`unknown_model_offer`, `model_offer_not_selectable` or `model_discovery_failed`.
Correct the exact ID, source configuration or discovery dependency and replay
`initialize-models`. No failed organization receives partial permissions or a
completion receipt; earlier successful organizations and the organization provisioning
itself remain committed. Discovery failure retains the last inventory. No provider
body, token or configuration value is included in initialization diagnostics.
Do not delete receipts to retry. Changing an already initialized association requires
an explicit administrative change; this lot adds no association-management UI.

### Source approval and discovery

The platform must review both destinations, the provider account/namespace,
visibility, actual credential scopes and egress/TLS policy together. Discovery
secrets use the existing `ENV_FILE`/process environment; inference credentials
remain pod-owned references and are never looked up by Rust. `mode: public` is an
explicit alternative, not a default. A credential that also permits inference
requires `authority: discovery_and_inference` **and**
`accept_inference_authority: true`; issuing a distinct key is not proof of scope.
HTTPS is required unless `allow_insecure_http: true` explicitly approves internal
HTTP. URLs with credentials, query parameters or fragments are refused. No URL is
derived from another and no Fred or pod token is implicitly reused.

Increase `revision` for every change, including rotation behind the same secret
reference. Apply the same configuration across replicas: older revisions and
different content at the same revision are rejected. A changed discovery URL,
inference provider/root or visibility scope requires a new source ID. The platform
must declare account/namespace changes through `visibility_scope`; discovery cannot
verify them from a bearer token. Disable a source at a higher revision before
removing its configuration. Disabled SQL rows and offers remain for diagnostics.
Configuration changes invalidate in-flight refreshes and retain the last success;
the observation becomes `not_observed` at the new revision.

The single adapter requires HTTP 200 and `{ "data": [{ "id": "exact-id" }] }`.
IDs are unique, nonblank, without outer whitespace/control characters, at most
256 UTF-8 bytes, and are never normalized. Requests take at most five seconds,
read at most one MiB and never follow redirects. The only supported envelope keys
besides `data` are `object: "list"`, `complete: true`, and
`has_more`/`partial`/`truncated: false`. Unknown envelope fields, pagination links,
ranges, truncation and unsupported pagination markers cannot replace a snapshot.
Non-identity content encodings are refused. A 200 response alone does not prove
completeness: `complete_inventory_guaranteed: false` always yields `incomplete`.
Silent provider truncation remains undetectable; platform approval must establish
the full-list guarantee for that exact visibility scope.

`chat_source` establishes chat from the platform guarantee;
`mixed_capabilities_v1` reads boolean `capabilities.completion_chat` and
`capabilities.reasoning` from the discovery response.
Missing/invalid mixed-source metadata stays unknown, and `false` still retains
the inventory member. Metadata records chat provenance, optional `name` or
`display_name`, positive integer `context_length`/`max_model_len`/
`max_context_length`, `max_input_tokens` and `max_output_tokens`. Invalid optional
fields become unknown. Labels are bounded to 256 bytes, limits to positive i64;
these remain source-reported facts. Reasoning is `true`, `false`, or unknown; no
static list supplements discovery. No tools, reasoning, modalities or limits are
inferred from IDs; unsupported feature metadata remains unknown.

Successful publication is atomic per source, including the observation and empty
inventories. Withdrawals retain the composite key, first/last-seen dates and last
metadata; reappearance restores that same row. Failures update only the attempt
state (`unavailable`, `invalid` or `incomplete`) and sanitized error code. They
preserve the last success and offers. Discovery creates no permission.
SQL refresh tokens implement last-started-wins across processes: an older attempt
cannot publish success or failure after a newer claim or configuration change.
Cancellation preserves the previous snapshot; the next explicit refresh needs no
lease recovery. The HTTP phase retains no SQL connection or transaction. Reads use
one consistent SQL snapshot and expose no URLs or credential references.

The following paths use the usual `/control-plane/v1` prefix. Every operation
requires `AdmittedUser`, active organization placement and `Manage`, with no
platform-role exception. Reads recheck admission and Manage after their consistent
SQL snapshot. No response schema includes destinations, credential references or
source approval configuration.

| Method/path | Contract |
| --- | --- |
| `GET /organizations/{organization_id}/models` | One repeatable-read snapshot of explicitly assigned sources (including disabled ones), observations, retained offers and only this organization's policy. `advertised`, chat qualification/provenance, discovery state/revisions and permission are separate facts. |
| `POST /organizations/{organization_id}/model-sources/{source_id}/refresh` | No body or destination override. Only an assigned, enabled source in this replica's approved configuration can be refreshed, and it must exactly match SQL. 204 on publication; 403 unassigned; 404 unknown; 409 disabled, obsolete or superseded; 502 invalid/incomplete discovery; 503 unavailable discovery. Failures retain the last success. |
| `GET /organizations/{organization_id}/model-policy` | Explicit permitted composite keys, optional default/fallback, revision and creation/update attribution. Absent policy is revision 0, empty set, null choices and null attribution. |
| `PUT /organizations/{organization_id}/model-policy` | Full replacement with `expected_revision`, `permitted`, `default` and `fallback`; all four fields required. Null clears each optional choice. 200 returns the saved policy; 409 on revision conflict or a newly selected unavailable offer; 422 on malformed policy, duplicates, unknown offers or choices outside the permitted set. |

PUT accepts at most 4096 distinct exact offer keys. Revision increments on every
successful write, including a no-op; callers must reload after a conflict. Default
and fallback must belong to the submitted permitted set, so revoking a selected
offer also requires explicitly clearing or replacing that choice. No default,
fallback, name-based match or permission is inferred.

Every submitted permission requires a source assignment. Only additions to `permitted` and changed non-null default/fallback selections
need fresh eligibility: known offer, enabled source, `state=ok`,
`snapshot_source_revision=source_revision`, advertised presence and `chat=true`.
The affected source/offer rows are share-locked until commit. Retained choices are
not revalidated as new selections: outage, changed configuration, unknown/non-chat
metadata and confirmed withdrawal remain diagnosable without blocking permission
reductions or explicit clearing. Refresh never rewrites policy; reappearance never
restores a revoked permission. Permission alone establishes no execution readiness.

Refresh checks admission/Manage before claiming a SQL token, commits, then performs
HTTP without a SQL connection. After HTTP it reacquires the existing platform and
organization locks, rechecks admission/placement/lifecycle/Manage and source assignment inside the same SQL transaction
before calling the publication store on that same transaction. Revocation refuses
publication of both successes and failures. Configuration equality and latest-token
checks still fence M1 publication; an unauthorized or cancelled attempt leaves its
token harmlessly supersedable by a later explicit refresh.

Tables `organization_model_policy` and `organization_model_permission` hold the policy. Composite offer foreign keys retain diagnostic
references; deferred membership foreign keys ensure atomic default/fallback
consistency. A trigger restricts the policy owner to an organization. Policy and
permissions cascade only on physical organization purge, not retirement or a user's
departure. Model policies remain organization scoped.

Initialize the complete schema before deploying this binary; startup checks
its fingerprint. Instance settings and resolver data are described below.

### Instance recommendations and resolver data (M3)

The existing space-scoped POST/PATCH and GET/list routes now accept/project
`recommended_model: {source_id, upstream_model_id}` and `model_options` in the
existing instance tuning JSON. There is no profile entity or new migration.
The owning organization comes from the authorized space, including personal spaces.
Creation and changed non-null recommendations reuse M2's `require_selectable`:
known, permitted, advertised, chat-qualified, enabled source and successful
observation at its current revision. The existing platform/organization lock
serializes policy changes; source/offer share locks keep the checked facts stable
until the instance write commits. SQL parameters never carry browser authority.

| Input | POST | PATCH |
| --- | --- | --- |
| `recommended_model` omitted/null | No recommendation | Omitted preserves; null clears |
| `recommended_model` key | Validate and save | Validate a changed key; an unchanged saved reference remains retained |
| `model_options` omitted/null | No overrides (`{}`) | Omitted preserves; null resets to `{}` |
| `model_options` object | Save explicit overrides | Replace the complete options object; omitted/null members remove their override |

Only `temperature` (finite number), `max_tokens` (positive integer) and `top_p`
(finite number in [0, 1]) are accepted. Booleans, numeric strings, fractional token
counts and unknown keys are rejected. An empty object supplies no values. There
are no invented provider defaults or source/template-option merges: resolver
options are precisely the saved instance overrides, shared across candidate offers.
No options alter identity or permission. Transport, endpoints, provider, credentials,
retries, timeouts and reasoning are not instance options.
When saving a changed recommendation or an options object, known output/context
limits bound `max_tokens` for the recommendation, otherwise the organization default.
A legacy-only profile prevents that implicit default resolution. Missing metadata
adds no inferred capability. Prompt-dependent input/context budgets and actual
provider support still require pod validation. The resolver separately diagnoses
option incompatibility for every candidate, including a possible fallback.

Metadata-only edits, unchanged recommendations and explicit clears do not require
successful discovery. Revocation, withdrawal or outage never rewrite a saved key.
`recommended_chat_profile_id` remains in ordinary instance reads for diagnosis;
new non-null writes return 422 `legacy_model_reselection_required`. Omission keeps
it and explicit null clears it. Selecting a new composite key does not erase that
history. No name conversion, synthetic profile or automatic migration exists.

The existing authenticated `/spaces/{space_id}/agent-instances/{agent_instance_id}/runtime`
route adds `models` and `agent.configuration_updated_at`. One read-only repeatable-read
snapshot contains instance configuration, policy, source/offer observations and
approved connections. Admission, canonical space/template authorization and enabled
instance checks are retained; admission/space/template rights are checked again
before returning. No SQL transaction survives a provider call (there is no provider
call here); the additional authorization checks occur outside the read transaction.

Reasoning activation is an organization ceiling stored on the existing permission
rows (`reasoning_enabled`, initially false). Complete policy replacement
includes `reasoning_enabled`, a subset of permitted composite keys. Newly enabled
reasoning requires a selectable offer with discovery-reported `reasoning: true`;
revoking permission removes its reasoning activation too. The same Manage gate,
revision check and source/offer locks apply. No model-name inference is used.

Control Plane evaluates the requested `reasoning: true` with the selected model's
organization permission and known capability. The admitted options contain
`reasoning_effort: high` only when all three allow it; otherwise it is omitted.
Python and Rust consume those options unchanged. Known output/context ceilings
bound `max_tokens`, even when the instance did not set an explicit override.
Python's existing Mistral reasoning replay and transport guards remain active.

`models.policy` includes revision, permitted and reasoning-enabled keys and explicit default/fallback;
`recommendation`, `options`, `legacy_profile_id` and `requires_reselection` describe
saved settings. `offers` is the union of permitted keys and retained references.
Each entry separates `permitted`, `candidate`, `selectable`, typed diagnostics,
known metadata and source/snapshot revisions and dates. A candidate requires known
presence/chat, current source revision, enabled source, permission and compatible
known option limits. It does not prove pod support, credentials, connectivity or
upstream authorization. After discovery failure a retained candidate may remain;
`selectable` is false until successful current discovery. Withdrawn, non-chat,
disabled, revoked, unknown and obsolete-source references are not candidates.

`model_catalog::instance::decide` is the single inference decision used by public
preparation, trusted Python delegation and internal Rust admission. Selection is
explicit choice, then instance recommendation, then organization default. A present
unknown/forbidden choice is refused without substitution; legacy-only profiles
require explicit re-selection. Fallback requires confirmed withdrawal and stays
within the same source and its approved provisioning/account. A discovery outage
alone, disabled source, revoked permission or missing credential never triggers it.

The `/runtime` query accepts `model_source_id` and `model_upstream_id` together,
and `reasoning`. These are requests, never authority. A trusted workload with the
existing authenticated person/run/agent delegation receives `inference`:
`selection` (effective key, selection origin, effective options and policy/source/
snapshot revisions) plus `connection` (provider, API root, local credential-binding
reference). Person calls receive facts without any connection or binding reference.
The in-process Rust host uses an explicit private resolver path after authenticating
the person, without manufacturing an HTTP delegation. Browser preparation returns
only the safe `selection` as `inference`, or the common decision's `model_error`.
No token value crosses these APIs or enters SQL.

The surrounding `RuntimeBinding` supplies subject, space/organization, instance,
configuration revision and conversation attribution. Python pins it to `RunScope`;
Rust retains it through the turn's tracing context. Neither runtime refreshes
permissions between LLM calls. New admissions observe changes; admitted turns can
finish, subject to local cancellation/deadlines and upstream credential rejection.
The legacy profile remains diagnostic data, never a connection lookup key.

### Workload provisioning and rotation

Python uses top-level `inference_credentials` in `AgentPodConfig`; the embedded
Rust workload uses `platform.inference_credentials` in Control Plane configuration.
Both use the same non-secret entry shape:

```yaml
inference_credentials:
  - source_id: example-gateway
    source_revision: 3
    api_root: https://gateway.example.invalid/v1
    credential_binding: example-account
    api_key_env: FRED_EXAMPLE_INFERENCE_KEY
```

`source_revision` must equal the admitted source configuration revision, including
rotation. Before reading the named environment variable, consumers check source,
exact destination, binding and revision against their local configuration. Missing,
duplicate, incomplete or inconsistent provisioning fails closed, with no HTTP
inference request and no global-key/Swift fallback. Only the OpenAI-compatible
adapter is connected. The variable name is an explicit source mapping, not a default.
Kubernetes Secrets/environment still provision the value; no secret manager or API
distribution was added. Deploy Control Plane and Python together for this contract:
Python now requires the admitted `inference`, and candidate offers no longer carry
private connections.

For rotation, prepare the new Secret and matching workload configuration, increase
the Control Plane source revision, refresh discovery for that revision, and roll
both consuming workloads with the same revision and approved connection. Deployment
ordering must prevent old/new mismatches from admitting work; mismatches fail closed
while the rollout converges. Environment variables are process snapshots and are
not automatically reloaded. Drain admitted turns before retiring the old credential
if continuity matters; the provider may reject an already-admitted revoked key.
An account/namespace/payer change requires a new source identity, not a fallback.

Targeted tests use a shared fixture in
`libs/fred-sdk/tests/fixtures/inference_admission.json`, real ChatOpenAI and Rig
adapters with simulated providers, and disposable SQL for host admission. These
checks do not establish k3d, provider or selector availability for Ralph.


## Automatic conversation titles

Newly registered conversations keep their initial title until one cosmetic title
attempt succeeds. Migration `0004_conversation_titles.sql` leaves every existing
session ineligible; it does not rewrite titles or histories. Registration replays
retain the original row and its eligibility. Run `control-plane init-schema` before
starting this version, using the normal schema-owner deployment procedure.

An organization **Owner** can optionally select a title model in its existing
Models settings. The choice is a pair `(source_id, upstream_model_id)` in the same
organization's permitted offers. It is persisted with the revisioned model policy,
whose complete replacement now requires `title` (use `null` for no dedicated
choice). Inventory `selectable` and write validation use the same calculation.
There is no platform-wide override, additional role or per-pod title setting.

With no dedicated choice, title inference uses the offer admitted for the answer,
with separate bounded settings: at most 128 output tokens (capped by known model
limits), no reasoning, no inherited answer temperature/top-p. With a dedicated
choice, an unusable offer leaves the initial title; it never falls back to another
organization's model or bypasses permission. Workload credentials for that source
must already be provisioned by the existing inference contract. Unchanged choices
can remain visible when unavailable, but newly selected offers must be selectable.

The read-only `GET .../agent-instances/{id}/runtime` never reserves a title.
Execution uses workload-delegated `POST` on the same path; the embedded Rust host
uses its private equivalent. After normal admission and association checks, an
atomic session update consumes `title_pending` and returns a unique attempt only
to one execution. A first resume or unavailable title model also consumes the
opportunity. Failures and retries do not schedule later attempts. No transaction
spans a provider call, and no extra queue or service is involved.

`POST /spaces/{space}/sessions/{session}/generated-title` is workload-only. Its
conditional write checks admitted subject, space, instance, session, attempt and
absence of deletion. Any manual non-null `PATCH` title clears the attempt, even
when its text equals the initial title; an activity-only patch does not. A late
result then receives 409 without changing the row. Deleted sessions are never
recreated. Successful persistence emits `session_title` with the original session
ID so the browser reloads canonical metadata instead of applying a stale string.

Python managed agent turns and embedded Rust Ralph implement the same envelope:
first 600 input characters, a prompt for 3–8 words in the input language, plain
text bounded to 80 characters, 10-second generation budget and at most 2 seconds
of grace before the final answer event. Closing/cancelling the stream cancels the
title work; failure or invalid output leaves the answer intact. The title is not
an assistant message. Existing inference observation and usage reporting count
consumption under its actual offer, including output rejected as an invalid title.
A provider's unreturned usage cannot be inferred after cancellation.

These contracts are covered by focused simulated-provider, SQL-upgrade and UI
component tests. They do not certify a local k3d or integration-platform journey.
Deploy Control Plane, SDK/runtime and frontend coherently; see the
[operator note](../../deploy/release-notes/changes/weaver-conversation-titles.md).

## Conversation metadata and browser preparation (M5a)

These backend APIs and generated clients back managed chat. Focused tests do not
establish a k3d/integration-validated journey. Paths below are relative to the CP prefix.

| Method / path | Behavior |
| --- | --- |
| `POST /spaces/{space_id}/sessions` | Register `{session_id, agent_instance_id, title?}`; 201 new, 200 identical association replay. The frontend ID is retained. |
| `GET /spaces/{space_id}/sessions` | Only the authenticated owner's conversations, ordered by `updated_at DESC, session_id`. |
| `GET /spaces/{space_id}/sessions/{session_id}` | Private metadata, retained instance/template/runtime IDs, current or registration-snapshot agent name, deletion/disabled flags, nullable public `messages_url`. |
| `PATCH /spaces/{space_id}/sessions/{session_id}` | Only `title` and/or `updated_at`; omitted/null values are unchanged. Empty title clears; activity is monotonic and capped at server time. |
| `POST /spaces/{space_id}/agent-instances/{agent_instance_id}/prepare-execution?session_id=...` | Admission, space Read, template Use, instance/source state and optional private association checks; public runtime/history routes and browser-safe model facts. |

Admission and current space Read apply to all operations. Session ownership is
always the authenticated subject; space membership, Write/Manage and platform roles
grant no access to another person's sessions. A foreign/unknown session is 404;
an owned incompatible association is 409 `session_association_mismatch`.
Unknown mutation fields are rejected with 422. Registration replay returns the
original row without overwriting title/activity, even when its instance is now
missing or disabled. New registration requires an executable saved association.
Title/activity edits and history metadata reads do not require template Use.

Table `session_metadata` is a private index, distinct from
shared instances; it contains no messages or checkpoints.
Its immutable identity columns deliberately have no cascading foreign keys:
instance/space purge neither removes retained provenance nor cascades into runtime
history. Missing/retired space authorization still prevents reading that index.
No purge, deletion endpoint, attachments, prompt library or history migration is
part of this surface. Agent names fall back to the registration snapshot after
instance deletion; registration is not a name-synchronization mechanism.

For each external `platform.runtime_catalog_sources` entry, `base_url` remains the
internal discovery endpoint. Optional `public_base_url` is an independently
approved same-origin ingress path, e.g. `/fred/agents/v2`. It must have canonical
nonempty path segments (ASCII letters/digits and `-_.~`, no `.`/`..`, trailing
slash, encoded characters, authority, query or fragment). No route is inferred.
Missing/disabled sources return `messages_url=null`; an instance's deletion or
disabling does not itself remove history routing. Reusing a runtime ID for another
history store is not a supported migration.

Preparation uses the existing bounded, nonredirecting template discovery, outside
SQL. Unavailable discovery is 503, denied discovery is 403, absent template is 409.
Missing public routing is 409 `agent_public_route_unavailable`; disabled instance
is 409 `agent_instance_disabled`; unavailable runtime is 409
`agent_runtime_unavailable`. No-tool react/graph families expose the existing SSE
and UI-part transport and the advertised input limit; HITL is false and
a `reasoning_toggle` only when at least one candidate model has reasoning enabled.
The existing composer offers it only for the selected enabled model, initially off.
Active capabilities return 422, other execution families 409.
No unsupported control is replaced with a default or hidden tool selection.

`models` projects the common catalog facts: recommendation, default/fallback, options,
legacy diagnostic and composite offers with permission/candidate/selectable and
effective reasoning-enabled facts,
metadata and diagnostics. The DTO has no inference URL, connection or credential
binding. Its `inference` selection comes from the common decision, without certifying
provider connectivity. A preparation is `Cache-Control: no-store` product data, never a grant or a replacement for M4.
Session responses are also no-store.

The existing `/runtime?conversation=...` checks the registered owner/space/instance/
runtime/template association inside its single admission request. Python then
checks its immutable checkpoint provenance against those canonical identifiers;
old histories without provenance still fail. No additional resolution or authority
read is added to model calls, retries or descendants. Revocation remains next-turn.
The pod's direct history GET currently checks ownership only: its current Weaver
space/admission check is a prerequisite of the later chat cutover, independent of
executable-instance state. This increment does not claim that read gate is wired.

Authorization reads the PostgreSQL role tables and immutable space placement. Mutations
check permission under the same platform/organization locks and SQL transaction as
their writes. Discovery, inference and streaming stay outside SQL transactions.

`POST /authorize/scope` returns the requested `space_id` anchor and the exact readable
`space_ids` subset of its ancestor path. Knowledge Flow applies that corpus directly.
Decision endpoints accept authenticated people or trusted person/run/agent delegation,
evaluate the person's admission and rights, and return `Cache-Control: no-store`.


## Background tasks

`control-plane serve` supervises HTTP, storage cleanup, the processing dispatcher
and configured lifecycle tasks in one process. Lifecycle is disabled by default.
See [activation and policy configuration](../../docs/architecture/A3-manager-operations.md#space-deletion-lifecycle).

## Changing it

A change described in the dossier updates its chapter in the same commit. A test that
proves an invariant carries `// Proves: I<n>` above it. Keep deployed SQLx migrations
immutable; add a numbered transaction for a supported upgrade, preserving constraints,
indexes, reader grants and data. Test fresh initialization and the preceding deployed
history. Never rewrite live checksums (see [Existing local state](#existing-local-state)).

## Generate the frontend contract

```sh
make generate-openapi                       # writes ignored openapi.json
make -C ../frontend update-control-plane-api  # regenerates schema, RTK endpoints and types
```

Generation runs without configuration, credentials or services. The frontend's
`update-all-apis` includes control-plane. Commit the regenerated
`src/slices/controlPlane/controlPlaneOpenApi.ts` with changes to routes or DTOs;
never edit it by hand. The slice uses the shared bearer/refresh base query and
Redux store. Its enhancement encodes the generated import argument as multipart
FormData, retaining the generated URL, method and completed-report type.
Bootstrap and import never retry automatically on 401; expiry can follow committed effects.
Frontend consumers use `controlPlaneApiEnhancements`. Background tasks establish
their Temporal connections independently of HTTP serving.

## Platform and space roles

`GET /me` reports effective platform roles. Platform admins list direct grants
with `GET /users/platform-roles`, and grant/revoke with
`PUT`/`DELETE /users/{subject}/platform-roles/{role}`. Any platform admin names or
removes other owners; the last one cannot be revoked. `platform_observer`,
`feature_manager` and `prompt_editor` are also supported.

Admin is technical: `platform_admin` governs the platform and
`organization_admin` appoints its organization's business owners. Neither role
reads content. `owner` is the business governance role (French: **Responsable**).
Space roles `member`, `editor`, `analyst` and `owner` are business roles. They are
cumulative and apply only to the space where they are granted; no role reaches a
child space. Owner alone does not read content. A personal space inherits nothing.
Personal spaces have `kind: personal`, an organization attachment and an owner,
but no parent or child projects. `team` denotes collective teams only, including
in scope filters and lifecycle policy selectors; use `[team, personal]` explicitly
when both kinds are intended. Personal creation keeps its dedicated endpoint. Opening, listing and new Control
Plane access require a business role (`owner`, `member`, `editor` or `analyst`)
on an active organization, team or project. Technical admin alone is insufficient;
mixed admin/business roles qualify. The demo creates no personal spaces.
Organization owners create teams, team owners create projects. The last owner of a
non-personal space, and the last technical admin of an organization, cannot be revoked. Capability checks and their contracts are in the
[runtime chapter](../../docs/architecture/A1-manager-runtime.md#platform-administration-and-self-checks).

Organizations are created through the platform form (`POST /control-plane/v1/admin/organizations`)
or a provisioning ZIP. Without the frontend, use the authenticated HTTP endpoint or
`make import-provisioning BUNDLE=<zip> TOKEN_FILE=<bearer-file>` on an initialized
installation. Both paths require a platform admin; creation does not restore a lost
platform-admin role.

Platform grants and organization-admin grants require the manager's service client. The factory
provisions the `control-plane` client and its directory grants. The cluster uses
`KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET` from `fred-secrets`. To reuse that identity
on the host, set `security.m2m.client_id` to `control-plane`, set its
`secret_env_var` to `KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET`, and supply that secret
in the host `.env`.
The [deployment chapter](../../docs/architecture/A3-manager-operations.md) describes configuration.

## Import a provisioning bundle

Build the checked-in demo from the repository root or `apps/control-plane`,
without running services:

```sh
make bundle-demo
# Optional overrides (absolute paths work from either directory):
make bundle-demo DEMO_PROVISIONING_FIXTURE_DIR="/path/to/fixtures" DEMO_BUNDLE_FILE="/path/to/demo.zip"
```

The default output is `apps/control-plane/target/demo-provisioning-bundle.zip`
(path from the repository root). Both entry points delegate to the same packager.

The ZIP contains exactly `manifest.json`, `users.json`, `organizations.json`,
`teams.json` and `projects.json`. The manifest declares `format_version: 2`,
`users_schema_version: 2`, `source_platform: "swift"`. The four data files are arrays.
The demo's people, spaces and roles are listed once in
[Example people and spaces](../../docs/architecture/02-journeys.md#example-people-and-spaces);
the [fixture README](tests/fixtures/import_export/demo_provisioning/README.md) gives
its counts and test password. `make bundle-demo` is the only demo build target.
The [declaration contract](../../docs/architecture/A2-manager-contracts.md#provisioning-declarations)
defines explicit parent references and roles, including projects. Old JSON and
Python version-1 ZIPs return `not_yet_supported`; no conversion is performed.

After compatible initialization, root bootstrap and personal CGU acceptance, save a platform admin's
access token in a private file and run:

```sh
make import-provisioning BUNDLE=target/demo-provisioning-bundle.zip TOKEN_FILE=/path/to/operator-token
# Equivalent binary command:
control-plane import-provisioning /path/to/bundle.zip --token-file /path/to/operator-token
```

The CLI uses the normal configuration and the manager's Keycloak service client.
It needs neither the running HTTP server nor Temporal and never initializes or
migrates SQL. The HTTP equivalent is multipart
`POST /control-plane/v1/import-export/import`, with exactly one field named `file`
and the operator bearer. It checks platform administration before reading the upload.
A new organization declares at least one owner and one admin. Archive limits are 50 MiB compressed and
100 MiB expanded, with no filesystem extraction.

Existing identities keep their profile and password; new identities need a
nonempty password. Usernames must already be lowercase, without surrounding
whitespace or control characters. Noncanonical names and known new-user email
conflicts are rejected before any provisioning writes. All space roles are explicit: admin alone grants no content
access, and every child-role holder needs a direct parent content role. Replay
preserves committed space IDs and undeclared grants and repairs requested grants.
Success returns JSON counts only after completion. A failed run reports a safe
phase and acknowledgment counts; correct the cause and replay with a valid token.
There is no cross-system rollback, so failure does not prove absence of effects.

`make test-integration` imports the actual Make artifact over HTTP with disposable
Keycloak, PostgreSQL, verifies replay and identity preservation, and
imports a variant with a project.

### Nova coexistence bundle

For the separate Swift/Weaver exercise, run `make bundle-migration` from the
repository root or this directory. It generates
`apps/control-plane/target/nova-migration-bundle.zip` (path from the repository root)
without contacting any service. It contains only Nova, its Pilote team and three
accounts, with no project or platform grant. `nova.admin` is Nova's technical
administrator; `nova.responsable` owns Nova and Pilote and explicitly holds
`member` on Nova, as required for a team role. `nova.editeur` holds `member` on
Nova and `editor` on Pilote, allowing the document exercise while the responsible
person retains governance only on Pilote.

Follow the [Nova fixture and Chrome walkthrough](tests/fixtures/import_export/nova_migration/README.md)
for credentials, shared-SSO collision checks and the manual import steps. This
is fresh provisioning in Weaver, not a transfer of Swift data. The browser
journey remains an operator validation step.

## Import through the frontend

Fred's existing administration console exposes **Provisioning** at
`/admin/provisioning` to manager platform admins. Select the ZIP produced by `make bundle-demo` or `make bundle-migration`.
The page displays the completed server counts or an error with explicit replay
guidance. The existing Home and sidebar display own memberships, hierarchy and roles.
The account menu permits logout before and after admission. Platform admins are restricted to governance/account routes. Business users retain
the existing product UI; endpoints not yet reconstructed can fail.

From `apps/frontend`, automate this journey without touching development data:

```sh
make install-test-browser       # once: Chromium, after installing Node dependencies
make test-provisioning-browser
```

The test needs Docker, Node/npm and the Rust/protoc prerequisites above. It starts
throwaway PostgreSQL and Keycloak plus the real manager governance router
and Vite frontend, then removes its services. Starting with no root or consent,
it bootstraps through the UI, accepts CGU, imports the actual Make ZIP, replays it,
imports a project variant, then switches accounts in the same browser. It checks
consent isolation, empty root memberships, persisted hierarchy/roles, reports,
refusals, unsupported direct URLs and keyboard logout through the existing account
menu. Any control-plane, knowledge-flow or agent-runtime call fails the test. Screenshots are
written under the frontend's ignored `target/` directory. The manager's
`make test-browser` invokes the same journey and integration suite when frontend
dependencies and Chromium are already installed.

## Existing local state

The architecture dossier contains the [SQL table catalogue](../../docs/architecture/A2-manager-contracts.md#control-plane-sql-catalogue)
and [SQLx operations](../../docs/architecture/A3-manager-operations.md#sqlx-schema-initialization).

`migrations/0001_schema.sql` creates the baseline tables; `0002_cp_read.sql` creates
the consumer views and grants. `0003_cp_read_document_tree.sql` appends display
columns to three views without replacing their grants or changing stored data.
All deployed migration files are immutable. SQLx records their fingerprints in
`control_plane._sqlx_migrations`, serializes initialization and runs each migration
transactionally. `control-plane initialize-schema` creates a fresh schema or applies
pending migrations from a matching history. Repeating it preserves data. API startup
only verifies the complete fingerprint and does not apply migrations.

The k3d profile enables the pre-install/pre-upgrade `control-plane-backend-schema-init`
Job through the shared chart's `migration` settings. Back up the target database before
upgrading. The document-tree upgrade supports the original matching 0001/0002 history;
it does not convert historical draft schemas or public tables. Changed, missing or
incomplete migration history is refused without resetting data or rewriting checksums.
The view upgrade has a five-second lock timeout: a busy database fails the hook safely
and can be retried after the blocker ends. Python runtimes retain their Alembic histories.

Older binaries enforce an exact migration history and may refuse to restart after
0003 is applied. Prefer a forward fix; a database rollback requires a coherent backup
and an explicitly planned recovery, never removing SQLx history rows in place.

Role mutations, initial space grants and bootstrap commit atomically in PostgreSQL.
The service and binary are named `control-plane`; the image remains
`control-plane-backend` and the lifecycle queue/prefix is `control-plane-lifecycle`.

The frontend's `controlPlane` client targets this Rust API. `legacyControlPlane`
retains the previous API types and clients for screens not yet migrated; the
Python backend is no longer shipped.

### Email facts in document previews

The existing preview endpoint serves the published generation's `metadata.json`
with the same document read checks as its Markdown. The API schema describes the
subset used by the viewer; other metadata extensions retain their existing
contracts. Email facts are bounded and validated before final publication, outside
SQL locks, alongside the existing immutable-byte/hash and identity checks.
Publication never derives identity, uniqueness or access from an email address or
message reference. No SQL migration or catalog filter is introduced.

A conversation attachment requires `session_id` on the preview request. Control
Plane verifies the document's actual association, current space read access and
ownership of that live conversation. Without this context the drive route still
excludes attachments. The email preview in the existing conversation attachment
panel supplies it; this does not make an attachment a shared library document.
Metadata and text modes each read one published artifact, without combining fields
from different generations in one view. Missing metadata on older documents has
an explicit empty state. See the [operator note](../../deploy/release-notes/changes/weaver-email-metadata.md).

### Document search inclusion

`Document.retrievable` is the last confirmed inclusion state, separate from processing
success and caller permissions. Publication reads and verifies `metadata.json` before
persisting it in the same transaction that sets `document.published_generation`. The vector worker checks
the flag on written chunks. Existing listing and content permissions are unchanged.

`PUT /documents/{id}/retrievable` with `{"retrievable": false}` or `true` requires the
existing space write permission and a published vector generation. KF updates only
its published chunk IDs and reads them back before confirming SQL. The response is
200 only after confirmation. `retrievable_pending` drives the existing UI refresh;
503 means the outcome is not confirmed, not that the operation was rolled back.
A request matching the recorded state, whether set by publication or by a confirmed
command, returns it without delivery or mutation. While pending, the same actor can
repeat the same request; an opposite request is rejected. `null` is rejected. The
command and its phase live in the `document.retrieval_*` columns:

- `ready`: the worker must atomically claim `writing` before touching OpenSearch.
  Only one claim succeeds, including after an API restart or Temporal history expiry.
- `writing`: the mutation activity has one attempt. Its timeout, termination or
  partial failure never authorizes another writer. A lost claim response also stays
  protected, even if no write actually began.
- `applied`: a separate activity records successful writer completion. That callback
  retries independently, without an overall workflow deadline, so a temporary SQL/HTTP
  outage does not discard Temporal's evidence that the writer returned. Verification
  and confirmation then run in a separate activity (up to five attempts per run).
- `confirmed=true`: SQL contains the verified value; duplicate confirmations are
  idempotent. Every callback is fenced by the current operation ID.

Delivery uses `ALLOW_DUPLICATE_FAILED_ONLY`, with `FAIL` on a running ID and a fresh
start-request ID. A failed, timed-out, cancelled or terminated run may restart; it
reads the persisted phase and never repeats a claimed mutation. `AlreadyExists` is
described and accepted only for a running execution, not a closed failure. A completed
run is not restarted. These policies follow the
[Temporal workflow identity contract](https://docs.temporal.io/workflow-execution/workflowid-runid).

For diagnosis, use the authenticated internal GET
`/document-processing/retrievable/{id}?operation_id={operation_id}` and the matching
`manager-retrievable-{installation}-{operation_id}` Temporal history. If the phase is
`applied`, repeat the original PUT to retry verification/confirmation. If it is
`writing`, inspect whether the completion-recording activity is still retrying; it
can finish without reapplying the mutation. A closed run with `writing` or a partial
projection requires investigation of the activity and remote write. There is **no automatic repair or operator reset
endpoint** for that case. Keep pending, do not clear the command or submit the opposite
value; any repair must first establish that the old writer and remote operations
have stopped and be separately scoped. A read matching the target alone is not proof
that an uncertain writer has stopped.

OpenSearch verifies exactly the IDs derived from `manifest.vector_ordinals` with
sequential `_mget` batches of at most 500. Only `metadata.document_uid` and
`metadata.retrievable` are requested. Missing/duplicate/unexpected IDs, per-item errors,
wrong ownership and nonmatching boolean values reject confirmation. For N published
chunks and batch size B=500, each verification pass costs `ceil(N/B)` requests (zero
for N=0), with at most one in flight, instead of N full-chunk reads. A confirmation
retry before SQL succeeds can repeat this read cost; a confirmed replay performs no
vector reads. No latency or throughput measurement is claimed. Unsupported vector
backends explicitly reject both generation-scoped mutation and verification.

The manager index remains isolated from legacy search/chat.

# control-plane

Fred's service for spaces, folders, documents and their authorization. Its design,
invariants and decisions are in the architecture dossier:
[docs/architecture](../../docs/architecture/README.md). This file says how to work on it. Use the [source map](src/README.md) to locate a feature.

## Develop

Same targets as the other apps (`make help` lists them). Building needs `protoc`;
`PROTOC` defaults to `~/bin/tools/protoc/bin/protoc`.

```
cp config/.env.template config/.env   # once: the four secrets
make run                              # http://localhost:8222/control-plane/v1
make test                             # offline unit tests
make test-integration                 # throwaway Postgres, OpenFGA and Keycloak containers
make test-lifecycle-temporal          # disposable SQL/FGA/Temporal worker recovery
make code-quality                     # model parity + clippy + rustfmt
make -C ../../docs/architecture check # the dossier still matches the code
```

## Organization supervision (API only)

The existing Control Plane serves organization totals and team detail, gated by
organization ownership. The [supervision contract](../../docs/architecture/A8-organizations.md#organization-supervision)
defines counters, privacy boundaries, pagination and failure behavior; the
[read budget](../../docs/architecture/09-quality.md#organization-supervision-read-budget)
documents SQL/OpenFGA costs. The [HTTP catalogue](../../docs/architecture/A2-manager-contracts.md#organization-supervision-api)
is generated from the handlers. There is no supervision UI or separate service.

## Embedded hello-world agent

The same process serves `POST /control-plane/v1/agents/execute/stream` (under the
configured base URL). It uses the existing authentication and consent checks and
streams Fred runtime events for `agent_id: "fred.github.ralph"`. See the
[agent library](agent/README.md) for the curl command and supported request subset.
No additional server or deployment is required.

## From scratch (fred-deployment-factory)

**Host run, after `make docker-up` or `make k3d-up`:**

With `DATABASE_URL` pointing to the configured control-plane database, apply
migrations explicitly before starting the API:

```sh
cargo run --locked -- migrate
make run
```

API startup only checks the installed migration history and checksums. It does
not initialize an empty database or apply pending migrations.

**In the cluster, after `make k3d-up`**, from fred-deployment-factory:

```
make k3d-app APP=fred DIR=../fred            # build, import, sync
make k3d-app-validate APP=fred DIR=../fred   # lint and render only
make k3d-logs SVC=control-plane-backend
```

Use `ENV=secondary` for this checkout's local profile. It deploys
`control-plane-backend`, `knowledge-flow-worker` and `frontend`; HTTP and background
tasks run together as `control-plane serve`. See [the profile](../../deploy/k3d/README.md).
Open Fred, sign in, accept the CGU, then enter the deployment bootstrap secret in the UI. The local service uses `FRED_BOOTSTRAP_TOKEN` from `config/.env`.
The k3d Fred values read the cluster secret `fred-secrets` key
`CONTROL_PLANE_BOOTSTRAP_TOKEN`; use the value supplied by your deployment.

The root is platform owner and has no organization membership. Open
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
| `control-plane migrate` | Applies pending SQL migrations from `DATABASE_URL` |
| `control-plane generate-openapi` | Prints the HTTP contract, without configuration or services |
| `control-plane generate-config-schema` | Prints the configuration JSON Schema |
| `control-plane processing-schema` | Prints the wire contracts shared with the Knowledge Flow worker |
| `control-plane import-provisioning <bundle.zip> --token-file <path>` | Authenticated additive import ([below](#import-a-provisioning-bundle)) |

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
template of the same name, version `0.1.0`. This demonstration agent replies `Hello world!`
without an LLM or data access. Its `kind` is `static`: the Rust discovery field
is a free string, and no ReAct or Graph engine runs this fixed response.
`control-plane` is reserved: configuring an external source with that identifier
is rejected, even when disabled.

The existing Administration Console -> Features -> Agents tab reads this same
catalog through `GET /control-plane/v1/organizations/{organization_id}/agents`.
Admission, unique organization context, active lifecycle and `can_manage` on an
organization are required; neither organization ownership alone nor platform
roles bypass this check. The page reads projected template identities and their organization defaults.
Its existing switch writes `PUT /organizations/{organization_id}/agents/{agent_id}/default-on`.
The default starts off and is stored in OpenFGA, not SQL. Turning it off preserves
explicit team and personal-class grants. No enrollment or instance state is inferred.
The write reuses the platform/organization locks and guards after discovery; no
runtime call holds a SQL transaction. Templates declaring tool dependencies cannot
be enabled by this initial integration. The supplied local configuration disables the
external fred-agents source; with no enabled external source the embedded catalog
requires no fred-agents process. An explicitly enabled source still fails the
whole discovery if unavailable.

This operator command uses a 10-second timeout per source and exits with an error
if any source fails, without printing a partial catalog. It does not start the API,
connect to SQL/OpenFGA, persist definitions or enroll instances. `serve` does not
poll runtimes. This command does not enroll or execute agents.

## Platform model inventory and organization administration

`platform.model_sources` defaults to `[]` in the schema. The host development
configuration and checkout-owned k3d overlay opt into the Mistral test source;
see [the local model setup](../../deploy/k3d/README.md#models-for-local-testing).
`serve` applies these non-secret
approvals to SQL after checking migrations; it performs no model discovery.
Organization APIs expose this inventory and persist explicit choices. There is no
model CLI, polling or runtime enforcement. The internal `configure_sources`,
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
`mixed_capabilities_v1` trusts only boolean `capabilities.completion_chat`.
Missing/invalid mixed-source metadata stays unknown, and `false` still retains
the inventory member. Metadata records chat provenance, optional `name` or
`display_name`, positive integer `context_length`/`max_model_len`/
`max_context_length`, `max_input_tokens` and `max_output_tokens`. Invalid optional
fields become unknown. Labels are bounded to 256 bytes, limits to positive i64;
these remain source-reported facts. No tools, reasoning, modalities or limits are
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
| `GET /organizations/{organization_id}/models` | One repeatable-read snapshot of all persisted sources (including disabled ones), observations, retained offers and only this organization's policy. `advertised`, chat qualification/provenance, discovery state/revisions and permission are separate facts. |
| `POST /organizations/{organization_id}/model-sources/{source_id}/refresh` | No body or destination override. Only an enabled source in this replica's approved configuration can be refreshed, and it must exactly match SQL. 204 on publication; 404 unknown; 409 disabled, obsolete or superseded; 502 invalid/incomplete discovery; 503 unavailable discovery. Failures retain the last success. |
| `GET /organizations/{organization_id}/model-policy` | Explicit permitted composite keys, optional default/fallback, revision and creation/update attribution. Absent policy is revision 0, empty set, null choices and null attribution. |
| `PUT /organizations/{organization_id}/model-policy` | Full replacement with `expected_revision`, `permitted`, `default` and `fallback`; all four fields required. Null clears each optional choice. 200 returns the saved policy; 409 on revision conflict or a newly selected unavailable offer; 422 on malformed policy, duplicates, unknown offers or choices outside the permitted set. |

PUT accepts at most 4096 distinct exact offer keys. Revision increments on every
successful write, including a no-op; callers must reload after a conflict. Default
and fallback must belong to the submitted permitted set, so revoking a selected
offer also requires explicitly clearing or replacing that choice. No default,
fallback, name-based match or permission is inferred.

Only additions to `permitted` and changed non-null default/fallback selections
need fresh eligibility: known offer, enabled source, `state=ok`,
`snapshot_source_revision=source_revision`, advertised presence and `chat=true`.
The affected source/offer rows are share-locked until commit. Retained choices are
not revalidated as new selections: outage, changed configuration, unknown/non-chat
metadata and confirmed withdrawal remain diagnosable without blocking permission
reductions or explicit clearing. Refresh never rewrites policy; reappearance never
restores a revoked permission. Permission alone establishes no execution readiness.

Refresh checks admission/Manage before claiming a SQL token, commits, then performs
HTTP without a SQL connection. After HTTP it reacquires the existing platform and
organization locks, rechecks admission/placement/lifecycle/Manage and fences FGA
before calling the publication store on that same transaction. Revocation refuses
publication of both successes and failures. Configuration equality and latest-token
checks still fence M1 publication; an unauthorized or cancelled attempt leaves its
token harmlessly supersedable by a later explicit refresh.

Migration `0016_organization_model_policy.sql` adds policy and permission tables;
0015 and earlier files are unchanged. Composite offer foreign keys retain diagnostic
references; deferred membership foreign keys ensure atomic default/fallback
consistency. A trigger restricts the policy owner to an organization. Policy and
permissions cascade only on physical organization purge, not retirement or a user's
departure. No model OpenFGA objects are introduced.

Neither migration was applied in these increments. Use the existing migration
procedure before deploying this binary; startup checks the full sequence. Technical
quality/generation evidence and **unexecuted** functional cases are in the existing
OpenSpec [M1-M3 checklist](../../openspec/changes/simplify-weaver-runtime-authorization/tasks.md#platform-model-catalog-accepted-sequence-decision-5e).
Instance settings and resolver data are described below. Model selection UI/chat and
invocation enforcement remain separate M4/M5 work.

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

`models.policy` includes revision, permitted keys and explicit default/fallback;
`recommendation`, `options`, `legacy_profile_id` and `requires_reselection` describe
saved settings. `offers` is the union of permitted keys and retained references.
Each entry separates `permitted`, `candidate`, `selectable`, typed diagnostics,
known metadata and source/snapshot revisions and dates. A candidate requires known
presence/chat, current source revision, enabled source, permission and compatible
known option limits. It does not prove pod support, credentials, connectivity or
upstream authorization. After discovery failure a retained candidate may remain;
`selectable` is false until successful current discovery. Withdrawn, non-chat,
disabled, revoked, unknown and obsolete-source references are not candidates.

Only a trusted workload with the existing validated person/run/agent delegation
receives candidate `connection` objects: approved provider, inference root and
pod-local inference credential-binding reference. Person calls omit that property.
No discovery URL/authentication/credential reference or secret value is exposed.
Organization inventory and ordinary instance responses remain connection-free.
The legacy profile is removed from the resolver's configuration copy and exposed
only as `models.legacy_profile_id`; persisted tuning and ordinary reads retain it.

This is data resolution, not model selection or invocation authorization. The
consumer contract remains explicit choice, then recommendation, then organization
default; a legacy-only profile requires re-selection. No first-offer default or
substitution of a forbidden explicit choice is allowed. A fallback reference is
not an instruction to use it: only confirmed withdrawal of a still-permitted choice,
with current approved source facts and a permitted/advertised/locally usable fallback,
can justify it. Discovery failure alone never triggers fallback. M4 must check the
actual choice before every invocation and compose any invocation overrides there;
this binding is not an authorization lease. No Python routing or SQL access is added.


## Conversation metadata and browser preparation (M5a)

These are backend APIs with generated clients, not a connected or functionally
validated chat journey. All paths below are relative to the configured CP prefix.

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

Migration `0017_session_metadata.sql` is additive and unapplied. This private
index is distinct from shared instances and contains no messages or checkpoints.
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
`chat_controls=[]`. Active capabilities return 422, other execution families 409.
No unsupported control is replaced with a default or hidden tool selection.

`models` projects M3 `resolve(false)`: recommendation, default/fallback, options,
legacy diagnostic and composite offers with permission/candidate/selectable facts,
metadata and diagnostics. The DTO has no inference URL, connection or credential
binding. It does not select a model or certify provider connectivity. A preparation
is `Cache-Control: no-store` product data, never a grant or a replacement for M4.
Session responses are also no-store.

The existing `/runtime?conversation=...` checks the registered owner/space/instance/
runtime/template association inside its single admission request. Python then
checks its immutable checkpoint provenance against those canonical identifiers;
old histories without provenance still fail. No additional resolution or authority
read is added to model calls, retries or descendants. Revocation remains next-turn.
The pod's direct history GET currently checks ownership only: its current Weaver
space/admission check is a prerequisite of the later chat cutover, independent of
executable-instance state. This increment does not claim that read gate is wired.

Authorization cost follows existing owners. Let R be the number of paginated FGA
Read requests for `roles_of(user)` (filter `user:user_id, object:space:`, followed
through every continuation token). A space authorization adds one `can_read`
Check after that organization-context lookup. List/read use R+1 calls, independent
of session count. Registration/patch perform two such authorizations plus two
guard revision Reads under the existing platform/organization lock; new creation
adds one template `can_use` Check and one fence Write, PATCH one fence Write, and
an existing-row replay neither. Thus successful calls cost 2R+6, 2R+5 and 2R+4
respectively when both role reads have R pages. Fence replaces the two revision
tuples (two deletes/two writes), creating no session FGA tuple. Preparation performs
two space authorizations and two template Checks (2R+4), with bounded discovery
between them and outside SQL. Model offers cause no extra FGA checks. Template
Use has one contextual placement tuple for team spaces, two for personal spaces.
SQL lock duration for mutations includes guard/recheck/fence calls and short SQL
reads/writes, never discovery, inference or streaming. Role cardinality drives R;
session count drives list SQL/serialization only. These are client RPC counts,
not measurements of server evaluation cost. M4 adds one scoped SQL association
read within its existing admission, never within an LLM loop. No latency or load
measurement is claimed; SQL behavior remains functionally unexecuted.


## Background tasks

`control-plane serve` supervises HTTP, storage cleanup, the processing dispatcher
and configured lifecycle tasks in one process. Lifecycle is disabled by default.
See [activation and policy configuration](../../docs/architecture/A3-manager-operations.md#space-deletion-lifecycle).

## Changing it

A change described in the dossier updates its chapter in the same commit. A test that
proves an invariant carries `// Proves: I<n>` above it. Applied SQL migrations are
immutable, including comments and whitespace. Add the next numbered SQL file under
`migrations/` for each schema change; preserve existing data
(see [Existing local state](#existing-local-state)).

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

`GET /me` reports effective platform roles. Platform owners list direct grants
with `GET /users/platform-roles`, and grant/revoke with
`PUT`/`DELETE /users/{subject}/platform-roles/{role}`. Any platform owner names or
removes other owners; the last one cannot be revoked. `platform_observer`,
`feature_manager` and `prompt_editor` are also supported.

Owner is technical: on the platform, and on each organization, where it names the
organization's admins and reads nothing. Platform owners name organization owners.
Space roles `member`, `editor`, `analyst` and `admin` are business roles. They are
cumulative; admin alone does not read content. Editor, admin and analyst also apply
to every descendant space; member stays local, and a personal space inherits nothing.
Personal spaces have `kind: personal`, an organization attachment and an owner,
but no parent or child projects. `team` denotes collective teams only, including
in scope filters and lifecycle policy selectors; use `[team, personal]` explicitly
when both kinds are intended. Personal creation keeps its dedicated endpoint.
Organization admins create teams, team admins create projects. The last admin of a
non-personal space, and the last owner of an organization, cannot be revoked. Capability checks and their contracts are in the
[runtime chapter](../../docs/architecture/A1-manager-runtime.md#platform-administration-and-self-checks).

Organizations are created through the platform form (`POST /control-plane/v1/admin/organizations`)
or a provisioning ZIP. Without the frontend, use the authenticated HTTP endpoint or
`make import-provisioning BUNDLE=<zip> TOKEN_FILE=<bearer-file>` on an initialized
installation. Both paths require a platform owner; creation does not restore a lost
platform-owner role.

Platform grants and organization-owner grants require the manager's service client. The factory
provisions the `control-plane` client and its directory grants. The cluster uses
`KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET` from `fred-secrets`. To reuse that identity
on the host, set `security.m2m.client_id` to `control-plane`, set its
`secret_env_var` to `KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET`, and supply that secret
in the host `.env`.
The [deployment chapter](../../docs/architecture/A3-manager-operations.md) describes configuration.

## Import a provisioning bundle

Build the checked-in demo, without running services:

```sh
make build-demo-bundle
# Optional overrides, with the same names as control-plane:
make build-demo-bundle DEMO_PROVISIONING_FIXTURE_DIR="/path/to/fixtures" DEMO_BUNDLE_FILE="/path/to/demo.zip"
```

The ZIP contains exactly `manifest.json`, `users.json`, `organizations.json`,
`teams.json` and `projects.json`. The manifest declares `format_version: 2`,
`users_schema_version: 2`, `source_platform: "swift"`. The four data files are arrays.
The demo contains 15 identities, one organization, three teams and an empty project
array. Demo passwords are test credentials. The
[declaration contract](../../docs/architecture/A2-manager-contracts.md#provisioning-declarations)
defines explicit parent references and roles, including projects. Old JSON and
Python version-1 ZIPs return `not_yet_supported`; no conversion is performed.

After compatible initialization, personal CGU acceptance and root bootstrap, save a platform owner's
access token in a private file and run:

```sh
make import-provisioning BUNDLE=target/demo-provisioning-bundle.zip TOKEN_FILE=/path/to/operator-token
# Equivalent binary command:
control-plane import-provisioning /path/to/bundle.zip --token-file /path/to/operator-token
```

The CLI uses the normal configuration and the manager's Keycloak service client.
It needs neither the running HTTP server nor Temporal and never initializes or
migrates SQL/OpenFGA. The HTTP equivalent is multipart
`POST /control-plane/v1/import-export/import`, with exactly one field named `file`
and the operator bearer. It checks platform ownership before reading the upload.
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
Keycloak, PostgreSQL and OpenFGA, verifies replay and identity preservation, and
imports a variant with a project.

## Import through the frontend

Fred's existing administration console exposes **Provisioning** at
`/admin/provisioning` to manager platform owners. Select the ZIP produced by `make build-demo-bundle`.
The page displays the completed server counts or an error with explicit replay
guidance. The existing Home and sidebar display own memberships, hierarchy and roles.
The account menu permits logout before and after admission. Platform owners are restricted to governance/account routes. Business users retain
the existing product UI; endpoints not yet reconstructed can fail.

From `apps/frontend`, automate this journey without touching development data:

```sh
make install-test-browser       # once: Chromium, after installing Node dependencies
make test-provisioning-browser
```

The test needs Docker, Node/npm and the Rust/protoc prerequisites above. It starts
throwaway PostgreSQL, OpenFGA and Keycloak plus the real manager governance router
and Vite frontend, then removes its services. Starting with no root or consent,
it accepts CGU, bootstraps through the UI, imports the actual Make ZIP, replays it,
imports a project variant, then switches accounts in the same browser. It checks
consent isolation, empty root memberships, persisted hierarchy/roles, reports,
refusals, unsupported direct URLs and keyboard logout through the existing account
menu. Any control-plane, knowledge-flow or agent-runtime call fails the test. Screenshots are
written under the frontend's ignored `target/` directory. The manager's
`make test-browser` invokes the same journey and integration suite when frontend
dependencies and Chromium are already installed.

## Existing local state

The architecture dossier contains the [SQL table catalogue](../../docs/architecture/A2-manager-contracts.md#control-plane-sql-catalogue)
and [SQLx operations](../../docs/architecture/A3-manager-operations.md#sqlx-schema-evolution).

SQLx records applied versions and checksums in `_sqlx_migrations`. Before upgrading,
inspect that history and back up the database. The `control-plane migrate` command
applies pending SQL files. API startup only verifies that the migration history
matches the binary's embedded versions and checksums, and refuses an incompatible
or uninitialized database. The k3d factory profile enables the chart's
pre-install/pre-upgrade migration Job. Rebuilding the Rust
image embeds new migration files; no manual SQL command is needed for this upgrade.

Migrations 0010/0011 classify existing personal spaces as `personal`, including
retired rows, without changing their IDs, content or OpenFGA tuples. The conversion
holds an exclusive lock on `space` and restores its placement immutability trigger
within the same transaction. Deploy matching API and generated clients together;
older binaries/clients only understand the three previous kinds. Review custom
`space_kind: team` retention rules: they no longer select personal documents.

`0001_manager_schema.sql` creates the initial schema; later numbered files evolve it.
A database whose recorded
versions or checksums differ from the embedded files is refused by the API and by
`migrate`; recreate it explicitly. Do not edit applied files or replace stored checksums.

The OpenFGA model still follows its separate pre-release replacement policy.
The [deployment chapter](../../docs/architecture/A3-manager-operations.md#authorization-store-publication)
describes publication and retry rules.

A role mutation that loses its authorization revision returns a conflict; replay
rechecks current authority. Timeout is not rollback. Roles and permission evaluation
remain in OpenFGA; SQL holds only the active store/model binding.

## Existing environment identifiers

The service and binary are named `control-plane`; the image remains
`control-plane-backend`. The current defaults use OpenFGA store `control-plane`
and lifecycle queue/prefix `control-plane-lifecycle`. Existing persisted resources
are not renamed or migrated by deployment. These defaults require a fresh
secondary installation or an explicit migration of existing state; application
reset is not supported for the Rust ingestion profile.

The frontend's `controlPlane` client targets this Rust API. `legacyControlPlane`
retains the previous API types and clients for screens not yet migrated; the
Python backend is no longer shipped.

### Document search inclusion

`Document.retrievable` is the last confirmed inclusion state, separate from processing
success and caller permissions. Publication reads and verifies `metadata.json` before
persisting it in the same transaction as the final manifest. The vector worker checks
the flag on written chunks. Existing listing and content permissions are unchanged.

`PUT /documents/{id}/retrievable` with `{"retrievable": false}` or `true` requires the
existing space write permission and a published vector generation. KF updates only
its published chunk IDs and reads them back before confirming SQL. The response is
200 only after confirmation. `retrievable_pending` drives the existing UI refresh;
503 means the outcome is not confirmed, not that the operation was rolled back.
Repeating an already confirmed request returns its durable result without delivery or
mutation. While pending, the same actor can repeat the same request; an opposite
request is rejected. The command and its phase live in `document.retrieval_command`:

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
can finish without reapplying the mutation. A closed run with `writing`, a partial
projection, or an old command without a phase (`uncertain`) requires investigation
of the activity and remote write. There is **no automatic repair or operator reset
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

Migration `0004_document_retrievable.sql` adds state without adopting pre-existing
vector data. Before considering an old document's indicator repaired, an authorized
writer must explicitly call the same route with `{"retrievable": null}`. This restores
only a document with no prior inclusion command, using the verified published
metadata and checking every published chunk; it does not rewrite vectors or ingest
again. A mismatch fails instead of guessing from counts. Apply it per selected ID,
not as an automatic startup sweep. This action was prepared but not run for the
reported PDF. The manager index remains isolated from legacy search/chat.

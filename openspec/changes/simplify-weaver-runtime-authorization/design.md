## Context

Planning baseline: branch `weaver`, with existing uncommitted version, deployment and security-instruction changes preserved. See proposal.md for scope. These documents describe a target, not a functioning managed-agent journey.

Observed sources (paths relative to repository root):

| Existing owner | Evidence and consequence |
| --- | --- |
| `apps/control-plane/src/fga/migration.rs` | `authorization_store` publishes `configured_store`, `active_store`, `model_id`; binding validation pins an exact model. Reuse this authority. |
| `apps/control-plane/src/spaces.rs::scope` | Authorizes the conversation space and returns its ancestor path; no separate ancestor read checks. Preserve this rule. |
| `apps/control-plane/src/fga/agents.rs::can_use_agent` | Exact-model, higher-consistency checks with trusted contextual tuples; currently team/personal only, not project execution. |
| `apps/control-plane/src/agents.rs` | Catalog discovery/defaults exist; templates with unavailable dependencies are refused. This does not implement managed execution. |
| Swift reference `origin/swift` at `6348ad2cfd0b5b96292f51c79bba3461be555133`: `control_plane_backend/models/agent_instance_models.py`, `agent_instances/store.py`, `product/service.py` and `product/api.py` under `apps/control-plane-backend/` | A discovered template becomes a persisted `agent_instance`, with source runtime/agent identity and validated tuning; CRUD, preparation and runtime binding use that record. Rust has no replacement yet. |
| Same Swift reference: `models/session_metadata_models.py`; current `TeamAgentsPage`, `useManagedChat`, `useChatSse` | Control Plane stores the session index/metadata, not messages. The UI still depends on instance CRUD, session metadata, preparation and runtime history URLs. Preserve that split instead of relocating it. |
| `libs/fred-runtime/fred_runtime/app/agent_app.py` | `_authorize_and_resolve` owns execution admission; managed binding calls `/teams/{team_id}/agent-instances/{id}/runtime`; startup requires Swift account-status schema and platform-access tables. |
| `libs/fred-core/fred_core/security/delegation.py` | Trusted workload plus person/run/agent assertion, not a user identity inferred from a service token. |
| `libs/fred-runtime/fred_runtime/common/outbound_credentials.py` and `libs/fred-pod/fred_pod/security/backend_to_backend_auth.py` | Credential providers, run lifetime, coordinated renewal and bounded authentication retry are reusable. |
| `libs/fred-runtime/fred_runtime/integrations/v2_runtime/adapters.py` | Search/read depend on Knowledge Flow HTTP clients; replace that dependency, not the entire agent execution engine. |
| `apps/control-plane/src/processing/publication.rs`, `retrievable.rs`, `documents/reads.rs`, `lifecycle/` | SQL owns publication, inclusion and retirement; vectors are a projection, not an access authority. |

Existing OpenSpec changes about folder-derived document authorization still target Swift tags, document checks and Knowledge Flow APIs. Extending them would mix incompatible models. This change is the single Weaver runtime/search contract; legacy specifications must not cause compatibility code to be retained.

## Goals / Non-Goals

**Goals:** restore the existing Custom Assistant journey with the least change to its definition, form, tuning and execution; provide its missing management backend in Rust; replace ReBAC/admission with one trusted context and operation gate. Keep the established template/instance/session concepts and configuration semantics. Local document access follows in its own delivery lot. Preserve credential/transport/storage mechanisms and remove replaced authorization paths.

**Non-Goals:** no general policy engine, new signed grants, user permission snapshots, per-tool authorization REST, polling-based revocation, schema auto-repair, Swift fallback, data migration or extra service. No promise of security accreditation equivalence without evidence. Project execution is not added incidentally to the Bob/fredlab slice.

## Decisions

### 1. Replace the Swift path in place

Weaver libraries use one model and one vocabulary (`space_id`, canonical organization/user/template identifiers). Do not retain `team_id` aliases or infer personal placement from `personal-{uid}`. Migrate live in-branch callers together or leave their functionality explicitly unavailable; do not hide an unported caller behind a legacy mode. No database reset, deletion of applied migrations or rewriting historical data is authorized.

Each lot removes the path it replaces. Shared files with other live consumers are convergence candidates, not proven dead. Record imports, factories, registry strings, configuration and deployment consumers before removing an entire module. Do not port unrelated capabilities merely to preserve all startup registrations.

### 1a. Restore the missing Swift management boundary in Rust

Dimi's clarified constraint is to keep the Custom Assistant as close to Swift as
possible: change ReBAC and its integration, not the agent product/configuration
logic. This supersedes suggestions to drop managed instances, limit their schema
to name/prompt, or move the session index into the runtime.

The precise gap is between discovery and execution:

| Responsibility | Existing Swift contract to preserve | Rust work in the next lot |
| --- | --- | --- |
| Template definition | Python `GeneralAssistantDefinition`, its fields/defaults and pod catalog | Reuse discovery and expose the space-authorized projection expected by the existing form. No persistent copy of executable templates. |
| Configured agent instance | Stable instance ID, source runtime/agent, display metadata, enabled state and validated `ManagedAgentTuning` compatible with `AgentTuning` | Persist the equivalent space-owned record and implement list/create/read/update/delete. Preserve name uniqueness and partial-update semantics. No FGA object per instance. |
| Save-time validation | Agent FieldSpec validation and pod-owned capability `validate-config`; stored versioned envelopes | Keep the same division: validate form values, relay selected capability config to its pod authority, persist the validated result without inventing a second capability schema in Rust. |
| UI execution preparation | `ExecutionPreparation`: ingress-relative runtime/history URLs, supported chat controls and effective model/configuration facts | Supply this contract from trusted discovery and the saved instance; preserve preparation before streaming. Rust does not proxy the stream or mint a signed execution grant. |
| Runtime binding | Instance resolves to its template and effective tuning at execution time | Add a space-scoped resolver using the same source record, trusted identity/delegation and the canonical Weaver context below. |
| Conversation index | `session_metadata`: user, scope, instance/runtime, title and lifecycle metadata | Reimplement the routes used by create/list/reopen/rename and the existing availability checks. Runtime message history/checkpoints remain in place. No new cross-store synchronization engine. |

Use the existing space route vocabulary: instance management and runtime binding
under `/spaces/{space_id}/agent-instances`, template projection under the same
space, and session metadata under `/spaces/{space_id}/sessions`; preparation stays
an instance operation. Replace callers and generated API bindings together, rather
than retain `/teams` authorization aliases or parallel Swift endpoints. The
endpoint shapes may adapt to canonical placement; the agent tuning, capability
envelopes and chat event contracts do not need a redesign.

The persisted configuration retains role/description, usage statement, tags,
FieldSpecs and values, recommended chat profile, capability selection and validated
capability configuration. Preserve omitted/null/empty-list distinctions: omitted
PATCH fields keep stored values, null capability selection inherits defaults,
and `[]` selects none for selectable templates. GET reads the saved tuning snapshot
without discovery. Edits touching tuning/capabilities refresh only FieldSpecs from
the pod; saved values and other settings never revert to template defaults.
Preserve model-routing behavior and only the management facts needed by the journey;
do not silently drop stored settings or replace them with pod defaults.
Unconnected settings backed by another service must return an explicit unsupported
or unavailable result until that dependency is connected; they do not justify
rebuilding all Swift administration in this lot.

Instance editing uses the existing space write permission; reading/execution
uses space read plus canonical template use. Template governance remains governed
by the existing management permissions. Dependency validity is still enforced;
removing per-capability/model FGA does not make arbitrary providers/endpoints usable.
Person departure semantics do not remove the operator's agent enabled/disabled
state or failure reporting for an unavailable configured capability.

First target: `fred.github.assistant`, whose actual default capability tuple is
empty. Use that existing behavior for the first acceptance path, with the normal
form and configuration machinery retained. Do not rewrite `general_assistant.py`
or ReAct to achieve it. The only later agent targets are
`fred.github.deep_assistant` and `fred.github.test_assistant`. Planning currently
defaults to document/tabular and constructs conversation files and a child agent;
its integration follows the first Custom. Test Assistant contains both no-LLM
transport scenarios and real model/document operations; those operations require
the same gate and actual dependency support. Rico and other agents are outside
this migration scope, not prerequisites to startup or acceptance.

### 1b. First persistence increment (task 1.1, storage only)

The additive `0012_agent_instances.sql` migration introduces `agent_instance`:
none of the existing space/document/operational tables represents a configured
agent. The record keeps its caller-supplied stable UUID, canonical space/template
UUIDs, source runtime/agent keys, display metadata, enabled flag and nullable actor
attribution. SQL supplies creation/update timestamps together on insertion.
`agent_instances.rs` exposes only create, get-for-space and list-by-space, using
the existing SQLx executor pattern so callers can use their pool or transaction.
Reads include disabled instances and always require a space. Name writes trim
surrounding whitespace; a unique `(space_id, lower(display_name))` index arbitrates
concurrent collisions. SQLx retains the named constraint error for the future API.

Tuning is an opaque JSONB payload (`Json<Value>` on read), with no field projection,
default injection or template merge: unknown fields, nested capability envelopes,
JSON null and empty arrays survive. JSON layout/key order is not a byte-preservation
contract. The caller owns business/capability validation, canonical identity,
authorization and lifecycle admission; persistence is not an execution gate.

Agent configurations belong to their space and follow its existing retention.
The space foreign key retains its default NO ACTION behavior, without a cascade.
At physical purge, the lifecycle worker explicitly deletes `agent_instance` rows
for the exact space being purged, immediately before deleting that space in the
same SQL transaction, after the existing locks and lifecycle/FGA checks. A deletion
request or an unexpired retention period removes no instances. Organization purge
keeps its existing descendant ordering; other spaces, histories/checkpoints and
user-departure behavior are unchanged. The migration is not applied; a binary
embedding it requires the new schema through the existing startup migration check.

### 1c. Space template catalog increment (task 1.1, read only)

`GET /spaces/{space_id}/agent-templates` uses `AdmittedUser` and
`spaces::authorize(Read)` before discovery. Only team/personal spaces are accepted;
other kinds return 400 after the normal authorization/lifecycle checks. Canonical
SQL placement supplies the organization for `template_id` and `can_use_agent`.
Each discovered template gets one template-use check, with the existing FGA read
concurrency bound of eight. A denial omits that template; discovery, metadata or
FGA failures propagate through the existing error conversion, never as an empty
or partial successful catalog. No SQL transaction spans discovery or these checks.

`AgentTemplateSummary` projects the Swift form contract directly from runtime
metadata: identity/provenance, labels/translations, category/tags, tuning fields,
capability descriptors, selection support and declared defaults. FieldSpecs and
capability descriptors remain complete JSON objects; no capability-specific schema
or separate capability/model FGA check is introduced. Swift's product-application
quarantine (`kind=app` or `app__` namespace) remains effective. Discovery requests
only public templates and exposes no `include_non_public` override; explicit
non-public/non-instantiable metadata is also excluded. The embedded hello-world
catalog marks its existing lack of managed-instance support explicitly.

The route and response schema share the existing Rust router/OpenAPI registration.
The frontend and generated clients remain untouched. Catalog availability is not
execution readiness; instance creation and the space-deletion lifecycle
are outside this catalog increment. Task 1.1 remains incomplete.

### 1d. Creation and saved-state read increment (tasks 1.1/1.2 remain incomplete)

Only POST /spaces/{space_id}/agent-instances and GET
/spaces/{space_id}/agent-instances/{agent_instance_id} are added. Creation uses the
Swift request fields with canonical Weaver UUIDs, server-generated instance identity
and authenticated author. Discovery resolves the configured source and reuses the
catalog's visibility/quarantine rules. The complete default_tuning is preserved,
including tags, FieldSpecs, translations and UI hints; enrollment overrides only
Swift's metadata, submitted known values and effective capability configuration.
Omitted/null/empty tuning values retain pod values; a nonempty map replaces them
with its validated known entries. No field defaults or required-form rules are
injected into values. The local validator checks types without coercion, numeric
bounds, enums, full-string patterns, scalar containers and reserved prompt tags.
Patterns use the existing Rust regex dependency; unsupported syntax fails closed
as invalid pod metadata (the current Custom declares no pattern).

Omitted/null capabilities inherit the catalog defaults; [] selects none for a
selectable template, while fixed capabilities remain required. Any effective active
capability or explicit nonempty selection returns 422 agent_capabilities_not_connected;
a non-null profile returns 422 agent_chat_profile_not_connected. Empty effective
selection is stored as [], with empty capability_config; unselected configuration
is ignored. No capability/model ReBAC or validate-config call is introduced.

AdmittedUser and active team/personal placement are required. Creation checks space
write and canonical template use before discovery, then repeats both after the
existing lock_for/authorize_locked protocol, fences and inserts in that transaction.
Retirement during discovery therefore blocks insertion. A name collision returns
409 agent_name_conflict. GET checks space read and stored template use, searches by
both space/instance IDs and projects only the saved row, including disabled state.
It performs no discovery and asserts no runtime availability. Swift's enrollment
validation and record projection move to Rust; space admission/use replace the old
team checks, with no per-instance tuples or trust in caller provenance/attribution.

Dimi's proposed evidence: prompt create/read equality; omitted/null/[] defaults;
case-insensitive trimmed name conflict; foreign instance/space and retired space,
including retirement during discovery; explicit unsupported tool/profile errors.
No dynamic validation, Python/frontend edits, other instance routes, resolver,
sessions, execution or client generation are included in this increment.

### 1e. Partial instance editing (tasks 1.1/1.2 remain incomplete)

PATCH /spaces/{space_id}/agent-instances/{agent_instance_id} returns the same saved
summary as POST/GET. Omitted/null metadata is unchanged; an empty description is
explicit. Tuning values distinguish omission (keep), null/{} (clear), and an object
(replace with validated known entries), using the existing TuningValue/FieldSpec
validator. Role and prompt survive renaming. Status edits enabled in this route.
A recommendation is kept when omitted, cleared by null, and otherwise refused in
422 until connected. Identity, provenance and attribution remain server-owned.

Editing starts from the saved JSON, including unknown metadata. Only edits touching
tuning/capability settings fetch the saved source's catalog, outside SQL; only
fields are refreshed. Tuning-only edits may fall back to saved fields if that
catalog/source/template is unavailable or missing. Canonical permission failures,
HTTP 401/403 and explicit template visibility refusals never fall back. Capability
selection/config edits require the current catalog even for null/empty requests.
Omitted selection stays unchanged, null resolves current defaults, [] selects none
only where selection is supported; fixed template defaults cannot be cleared to
accept a save. Active selections remain 422. An unchanged selection with omitted
config keeps its envelopes; changed selection or explicit config drops unselected
values. No validate-config, upload or tool port is introduced. Metadata-only edits
do not reject untouched, unconnected settings or consult discovery.

Swift's update template gate maps to canonical can_use_agent, and team write maps
to AdmittedUser plus active team/personal space write. After discovery, the existing
lock_for/authorize_locked protocol rechecks lifecycle/write, rereads the scoped row,
checks its template use, applies the patch to that current row and fences the SQL
UPDATE. No added lock/version/retry mechanism; omitted concurrent edits survive.
UPDATE RETURNING supplies the response, preserving UUID/source/creation attribution;
updated_at/updated_by change only when editable data differs. Name collisions reuse
409 agent_name_conflict. Foreign instances remain 404. GET still reads only SQL.

Static source inspection only; Dimi owns prompt edit/read, omission/null/{}, rename,
status toggle, no-op attribution, name collision, foreign/retired scope, concurrent
omitted-field preservation and unsupported-setting validation. No UI journey,
execution readiness or completion of tasks 1.1/1.2 is claimed.

### 1f. Instance deletion (step 6; tasks 1.1/1.2 remain incomplete)

DELETE /spaces/{space_id}/agent-instances/{agent_instance_id} requires AdmittedUser
and an active canonical team/personal space with Write. Reuse lock_for,
authorize_locked and the existing fence before a SQL DELETE scoped by both IDs,
then commit. A removed row returns 204 without a body; an absent/foreign instance,
including a repeated deletion, returns 404. Enabled and disabled instances can be
removed, freeing their space-local name. As in Swift, template use is not required:
revoked template access does not prevent removal while space Write remains.

Only agent_instance configuration is deleted. No catalog/runtime calls, business
FGA tuple mutations, extra lock, retry, soft delete or tombstone are added; the
existing fence retains its technical revision updates. Space purge is unchanged.
Messages/checkpoints are untouched. Session metadata and last-name preservation
will be handled when that metadata is integrated into this Control Plane.

### 1g. Saved instance list (step 7; tasks 1.1/1.2 remain incomplete)

GET /spaces/{space_id}/agent-instances returns 200 with an array of the existing
ManagedAgentInstanceSummary, including enabled and disabled instances in persisted
created_at, agent_instance_id order. Reuse list_by_space and record_to_summary so
each visible item has exactly the individual GET's saved projection. No catalog,
runtime or FieldSpec refresh participates; enabled is not execution availability.

Apply AdmittedUser, spaces::authorize(Read) on the active canonical space and
require_instance_space. Check each distinct saved template_id once per request
with can_use_agent, using the agent-templates route's buffered/try_collect mechanism
and crate::fga::READ_CONCURRENCY. A false decision omits its instances; a technical
FGA error fails the request, never producing an empty or partial success. SQL and
authorized-instance projection errors propagate. An authorized space with no
visible instances returns []. No mutation lock, SQL transaction, connection held
during FGA checks or cross-request cache is added. DELETE remains unchanged:
space Write still permits removal after template revocation, without a visibility
exception or new management status. Dynamic validation remains the next milestone.

### 2. Consume one published authorization binding

At startup, use configured PostgreSQL access to read the singleton binding. Validate configured identity and the exact fetched model against the canonical Weaver contract; pin `active_store` and `model_id` on every check. Reuse the checked-in Control Plane model artifact; do not maintain a second hand-written Python schema.

Missing/mismatched binding, unsupported model or unavailable dependencies prevent readiness. Runtime does not select latest, create a store, synchronize a schema or fall back. Tuple checks use higher consistency and no cross-operation authorization cache. Binding replacement is not hot-reloaded: a future model rollout must coordinate consumers; it is not authorized here.

### 3. Resolve canonical context; keep credentials outside it

Preserve the credential provider on the existing runtime-to-Control-Plane interaction. The receiver must support either an authenticated person or a verified delegation-capable workload plus the existing person/run/agent assertion. Validate issuer, audience, client restrictions, delegation role and service-account requirements; never accept assertion parameters from an ordinary bearer as authority. Python and Rust must agree on canonical subject mapping (Rust also maps non-UUID OIDC subjects).

The proposed resolver request contains only requested `space_id` and
`agent_instance_id`. Identity comes from verified credentials/delegation;
run and request correlation use existing authenticated call/trace mechanisms.
Do not accept organization/team/project placement, permissions or arbitrary
configuration from the caller. Resolve the instance within the requested space.

The response is one canonical binding with three groups:

- `subject_id`: canonical person identity, checked against the verified caller.
- `space`: `id`, `kind`, `organization_id`, `team_id`, `project_id`. All keys are
  present; absent hierarchy levels are null. For fredlab, team_id equals id and
  project_id is null. Personal spaces have null team/project and never inherit
  organization document scope. These fields are canonical placement, not aliases
  treating every execution space as a team.
- `agent`: `instance_id`, `runtime_id`, `template_id` (organization-qualified FGA
  identity), `template_key` (registry lookup), and effective `configuration` using
  the existing configuration contract. Do not invent a second capability or model
  configuration vocabulary. No secrets or tokens in this response.

Runtime checks that the response belongs to the requested instance/space and the
local runtime, then binds it once into its existing immutable execution context.
Preserve existing identifier ownership: the UI can create the session ID as in
Swift, Control Plane registers its metadata, and runtime owns run/trace execution,
messages and checkpoints. Preparation verifies the session association when a
session is supplied; runtime independently retains ownership checks and binds its
history/checkpoint to the resolved instance/space/person. A mismatch is rejected
before context loading or execution, including resume. The instance resolver need
not echo a session ID or duplicate messages. Restoring the existing lightweight
metadata store is explicitly in scope and preserves the existing chat lifecycle.

The binding contains no roles, allowed-document IDs, cached permission results,
FGA store/model IDs or bearer tokens. Existing display/configuration fields remain
ordinary product data, never authorization evidence. Current rights and
lifecycle are checked locally; a context is not an authorization lease. Derive
document search scope once through the shared primitive from canonical placement,
not through per-capability organization/team/project branches.

The instance source is the Rust persistence described in decision 1a; it is missing
today and is an explicit implementation task, not an unspecified product decision.
Reuse the runtime's existing credential provider and admission order where possible;
the Rust receiver must support its verified delegation path. Do not force a
human-bearer-only resolver or rewrite renewal merely to avoid implementing that
receiver. The canonical wrapper is adapted at the boundary; effective tuning and
the runtime's model/capability configuration machinery remain intact.

### 3a. Rich telemetry from the same canonical context

Use the existing `fred_core.logs.context` request/operation scopes and KPI event
pipeline. One central binder projects `organization_id`, `team_id`, `project_id`,
`space_id`, `space_kind`, and existing user/session/run/instance/template/runtime
and trace identifiers into structured logs and applicable KPI events. Keep current
latency, token, cost, status, model and tool details. No per-tool placement lookup or
manual enrichment. Treat team/project as genuine hierarchy dimensions, not legacy
team-context compatibility. Logging context is never an authorization source.

Bind authoritative dimensions only after resolution; pre-resolution refusals keep
verified identity/trace and explicitly untrusted requested identifiers, without
claiming a verified hierarchy. Isolate concurrent runs and clear context on teardown;
terminal/cancellation logs retain their own resolved snapshot. Retrieving a TSN
document from a fredlab run must not change the run's team attribution; source-space
metadata, if needed, is a separately named field.

Index organization/team/project dimensions as queryable exact-match fields in the
existing product KPI store and structured log backend. Null/absent project means
no project, never a fabricated sentinel. Queries support TSN totals, fredlab totals
including its projects, and a specific project. Names are resolved for display;
IDs remain stable through renames. Do not propagate credentials or document text
into this enrichment. Existing telemetry access boundaries remain required.

Prometheus currently has an explicit allow-list excluding team/user/instance
product dimensions. Preserve it in this slice: rich searchable logs/product KPIs
do not require putting every identity into platform-wide metric labels. No second
telemetry system or new authorization model for analytics is introduced.

### 4. Check once per protected operation

At run admission and before each protected operation, including each model invocation and capability access, evaluate `can_read(Bob, fredlab)` and `can_use(fredlab, canonical_template)`, plus current applicable admission/lifecycle facts and the operation's permission. Build contextual tuples only from trusted placement. Reuse identical decisions inside that operation; independent checks can be grouped. A search is one operation, not one check per returned chunk; a later document read is another operation. No check per SSE token, no TTL cache across operations.

A refusal blocks storage access, terminates the run and invalidates its delegation. Dependency failure blocks the operation with a distinct technical error, not a denial disguised as empty results. The LLM cannot catch an authorization failure and continue through another tool. Preserve cancellation/terminal run enforcement and existing credential renewal; an authorization denial never triggers credential refresh as a recovery tactic.

Revocation is observed at the next operation boundary. An already authorized operation may finish; data already emitted cannot be recalled. A generation using previously obtained data is not promised instantaneous revocation. No polling/notification system is introduced.

### 4a. Revocation is departure, not reversible suspension

Dimi's explicit clarification: there is no requirement to preserve a suspended
person's access/context for later restoration. A return follows ordinary newcomer
admission and does not automatically restore former memberships, runs or authority,
even if the identity provider reuses the same subject. Scope-specific access removal
must not accidentally remove unrelated access; departure revokes the applicable
whole Fred access scope.

The accepted maximum is five minutes after effective access revocation for
already-running activity and its run/delegation cleanup. This
relaxes the need for instantaneous cancellation, not the agreed next-operation
checks. Do not introduce an authorization cache or polling system on that basis.
Specify how existing run/delegation lifetime controls enforce that bound before
implementation: token expiry alone does not bound a renewing service credential
or a generation with no further protected operations. First inspect and reuse the
existing cancellation/timeouts rather than inventing new infrastructure.

Static inspection found that `RunScope` and the delegated run record have terminal
state but no automatic authorization deadline. A transport read timeout alone
does not bound a continuously streaming generation or retries. Close this concrete
gap through bounded active-operation/run lifetime and existing cancellation; any
chosen maximum turn duration must be explicit as a product limit. This plan does
not impose the audit's illustrative 240-second limit or authorize a new revocation
service. A bound cannot be claimed solely because model/tool gates exist.

Cleanup means ending affected runs/delegations, releasing runtime resources and
removing effective access so stale credentials cannot restore it. It does not
implicitly authorize purging shared documents, audit records or persisted histories;
data ownership, retention and erasure are a separate explicit contract. No new
reversible `suspended` relation or frozen-account restoration feature is required.
The mapping of the old account check to actual Weaver departure/revocation remains
to establish; the business requirement is now decided.

### 5. Derive document visibility from placement and publication

For team fredlab: authorize fredlab, derive `[TSN, fredlab]` from SQL placement, and restrict with any requested levels/folders. Do not require Bob to have a separate `can_read(TSN)`. For a project, document scope is organization/team/project; a team conversation never searches descendants. Personal scope is itself. Never widen to every space Bob can access.

The shared primitive owns mandatory storage filters and does not accept raw authorization scope from tool arguments. For each hit, the minimal verifiable provenance is document identity, containing space, published generation and chunk identity/ordinal. Confirm how existing index records carry these fields before changing an adapter; missing provenance is not accepted through a legacy fallback.

OpenSearch: prefilter by permitted spaces and inclusion projection, then batch-check candidate documents and generation/chunk membership against authoritative SQL publication/lifecycle facts before any external reranking, LLM exposure, citations or content-bearing logs. pgvector can perform equivalent SQL joins. Do not materialize the entire corpus as a list of document permissions. Bounded candidates may yield fewer results after filtering; no unbounded refill/recovery loop is required.

Proposed conservative inclusion semantics: require `retrievable=true` and no unconfirmed inclusion command. Exclude retired/deleting documents and spaces, missing publication, stale generations and chunks outside the committed manifest. Validate the same boundary for follow-up reads/citations. This adds no document FGA tuples. Inspect source/manifest identifiers rather than treating processing status or vector count alone as publication proof.

### 5a. Reuse Swift capabilities and models; change only the ReBAC boundary

Accepted by Dimi: activating a template authorizes the dependencies attached to
its trusted effective configuration, for execution under that template. Reuse
Swift declarations, registry, configuration format, dependency construction, model
selection/routing, clients and credential providers. Do not rewrite these systems
for elegance, introduce a new dependency framework, or port unrelated tools.

At activation, establish that the declared local capability/model dependencies
are actually supported and configured. At resolution/execution, reject missing or
unavailable dependencies and enforce the trusted binding's configured set. Existing
routing can choose within that set; browser/model tool arguments cannot add a
capability, provider/model, arbitrary endpoint or credential. Keep operational
limits and any existing non-ReBAC restrictions. Dependency availability is not
proof of Bob's rights: the common space/template gate still applies.

Remove the scoped Swift independent capability/model FGA enablement calls once
these checks replace them; add no capability/model types or tuples to Weaver.
Capabilities still enforce operation/data rights through the common primitive.
An unexpected additional Swift security restriction must be identified before
removal, not silently discarded or turned into a new policy subsystem.

The current blanket `agent_dependencies_unavailable` refusal is replaced only for
dependencies with real configured-set/availability checks. The first Custom has
no default tools and must not wait for document access; a model is still required.
Document selection becomes usable with the subsequent local-document lot. Unsupported MCP,
artifact or other dependencies remain refused. No substitute catalog registration
mechanism, general capability management UI or model-routing redesign belongs here.

### 6. Preserve guarantees and remove old owners

| Swift guarantee / enforcement | Weaver owner / replacement | Removal or proof condition |
| --- | --- | --- |
| JWT and asserted-principal checks in `security/delegation.py` / OIDC | Existing auth plus canonical identity mapping and Rust trusted-delegation receiver | Retain mechanism; prove person/service confusion and forged assertion rejection |
| Credential renewal and live-run providers | Same providers and run lifetime | Retain; prove refresh works without extending a revoked/completed run |
| `organization.suspended`, `platform_access_*`, old user/team admission | Canonical Weaver admission and account-state enforcement | Departure/revocation replaces reversible suspension; establish bounded cleanup and no automatic restoration, without restoring old tables |
| `_authorize_execution_or_raise`, team/personal/service shortcuts | Shared space/template operation gate | Replace together; no service-token or platform-role content bypass |
| `agent_instance`, tuning validation, CRUD and preparation | Rust management with the existing product/configuration semantics | Add missing persistence/routes; adapt space/authz boundaries, not the agent definition or tuning language |
| Session metadata and session/checkpoint ownership | Rust keeps the metadata/index; runtime retains messages/checkpoints and enforces the canonical association | Reconnect the current chat; no runtime-history rewrite or second message store |
| `capability_authz.py`, legacy model/capability enablement | Template-authorized configured dependencies, using existing registry/routing | Replace scoped FGA enablement calls with configured-set and availability checks; keep operation/data restrictions |
| Knowledge Flow search/read authorization and HTTP clients | Local shared document primitive | Replace scoped consumers, then remove unused clients/registrations; unrelated live consumers require their own lot |

## Risks / Trade-offs

- **Missing managed-agent APIs** -> Lot 1 restores their identified Swift responsibilities in Rust. Catalog discovery is not instance persistence or execution readiness. The work includes backend endpoints/schema and frontend bindings, not only a Python ReBAC adapter.
- **Bounded revocation enforcement** -> Reuse lifetime/cancellation mechanisms and close the identified deadline gap in lot 1. Do not claim the five-minute bound from JWT renewal or transport timeouts.
- **Templates depend on unavailable capabilities/models** -> Preserve refusal until the actual local dependency path is implemented and configured. Template authorization covers only configured dependencies; the document filter does not authorize arbitrary model selection.
- **SQL and vector projections differ** -> Mandatory SQL verification rejects stale candidates; no distributed transaction or repair subsystem is introduced.
- **Broad legacy module consumers** -> Delete replaced behavior incrementally, measure owned production additions/deletions separately from tests/generated/config/docs. No numeric savings claim before the implementation diff exists.
- **Project agent inheritance** -> Documentary scope is settled; current template use helper excludes projects. Specify project execution separately rather than treating its support as already implemented.

## Migration Plan

No data migration in this change. Weaver 5.x is a breaking development line. New additive schema migrations for the Rust instance/session metadata are allowed; existing applied migrations and user data remain intact. No Swift compatibility mode, conversion scripts, migration of running runs, FGA store replacement or deployment is delivered. Dimi will validate development deployments after the relevant lots; data migration and release receive separate planning.

## Definitive lot boundaries and remaining technical work

The immediate delivery is lot 1 in tasks.md: the existing Custom's configured
instance, form, preparation, conversation and model execution under Weaver rights.
Its no-tool acceptance path does not change the configuration semantics. Restore
the identified Rust management responsibilities and retain the Python engines.
No document-worker/index changes or unrelated agent port are prerequisites.

Lot 2 adds local documents to that same Custom. Lot 3 connects Planning through
the same owners. Test Assistant accompanies the supported scenarios; it is not
permission to port all its dependencies or change the production agent behavior.
The exact additive schema/DTO implementation and the bounded cancellation detail
are implementation work within these boundaries, not a new instance product,
polling service or authorization framework.

Conservative exclusion during unconfirmed document inclusion remains the documented
implementation proposal for lot 2. It does not justify a new publication subsystem.

Deletion is incremental: remove replaced call paths and configuration in the lot
that replaces them. Delete a whole shared module only after verifying static and
dynamic consumers; no claimed line reduction from merely listing candidates.
Reuse current storage/model adapters. No dedicated broad cleanup, all-capability
port, data migration, changed applied migration or OpenFGA model replacement.

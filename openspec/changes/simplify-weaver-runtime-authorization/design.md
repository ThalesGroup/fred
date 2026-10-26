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

**Goals:** restore the existing Custom Assistant journey with the least change to its definition, form, tuning and execution; provide its missing management backend in Rust; replace ReBAC/admission with one trusted context per turn and local operation checks. Keep the established template/instance/session concepts and configuration semantics. Local document access follows in its own delivery lot. Preserve credential/transport/storage mechanisms and remove replaced authorization paths.

**Non-Goals:** no general policy engine, new signed grants, permission snapshots reusable across turns, per-tool authorization REST, polling-based revocation, schema auto-repair, Swift fallback, data migration or extra service. No promise of security accreditation equivalence without evidence. Project execution is not added incidentally to the Bob/fredlab slice.

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

### 1h. Agent management UI sub-lot of 1.7 (2026-10-25)

Reuse TeamAgentsPage, its cards and full tabbed form with the generated Rust
space contracts. Resolve route identity against /me/spaces, admit only team and
personal spaces and ask the existing authorize endpoint for Write. List/GET remain
independent of the management catalog and its failures. Keep space-scoped RTK
cache tags and discard open selections when scope changes. Edit from GET and send
only changed fields, preserving saved tuning and unsupported capability/profile
settings. Keep adjacent unsupported actions visible and explicitly unavailable,
without legacy calls. Preserve other shared-component consumers.

The user authorizes focused frontend regression tests, TypeScript and frontend
build for this sub-lot. No backend changes, deployment, migration, commit or push.
Execution preparation, sessions and chat remain outside this delivery; task 1.7
stays open. Dimi owns validation after redeployment; no arc42 boundary expansion.

### 1i. M5a: private conversation metadata and browser preparation (2026-10-26)

This accepted increment restores only the API boundary of task 1.3. The browser's
session identifier is the global index key, preserved verbatim; owner comes from
AdmittedUser, while space, instance, template and runtime come from the saved
instance. A separate metadata table is necessary: instances are shared space data,
whereas conversations are private, survive instance deletion and contain no tuning
or messages. Immutable provenance identifiers have no cascading foreign keys; space
purge must not erase them or become blocked by retained history. A missing/retired
space still prevents access through the existing authorization owner.

Registration under /spaces/{space_id}/sessions uses the existing organization
mutation lock and FGA fence. A retry of the same owner's association returns the
original row without changing title/activity, including after instance removal.
A foreign ID is 404; an incompatible owned association is 409. PATCH accepts only
title/activity, never owner or provenance. Activity is monotonic and capped at
server time, title-only edits do not reorder the list. List order is activity
descending then session ID. Read/list/rename require admission, current space Read
and private ownership, independently of template use or instance execution state.

POST instance /prepare-execution verifies current Read/template Use, enabled state,
approved runtime, current template support and optional registered session. It
uses an explicit platform public_base_url (canonical same-origin ingress path),
never internal base_url or browser/catalog destinations. Discovery is bounded and
outside SQL. Only no-tool react/graph preparation is supported; no capability
controls or HITL integration are advertised. M3 resolve(false) supplies model facts
through a browser DTO that cannot contain inference connections/credential bindings.
No new model selection policy or readiness guarantee is introduced.

The existing M4 resolver checks the canonical registered association in its one
turn-start request. The pod then compares that association to its immutable local
checkpoint binding before loading content; no synchronization or per-invocation
authority read is added. Metadata creation alone never adopts existing runtime
history: M4 still refuses missing/incompatible provenance.

Runtime history GET currently filters by authenticated owner only. Enforcing current
Weaver space access on that independent read is a prerequisite of the later chat
cutover, distinct from execution admission and from this CP-only increment. The
existing endpoint must retain history readability after instance deletion without
calling the executable-instance resolver. No Python history gate is silently added
here. UI binding, context prompts, attachments, history purge and old-conversation
migration are excluded. Functional cases remain prepared, unexecuted.

### 1j. M5b: independent private-history consultation (2026-10-26)

The existing M5a GET is sufficient. Pod readers derive placement from the persisted
M4 binding and compare its owner, session key, space, instance, template and runtime
with the authenticated person and M5a result. M5a's owner-filtered SQL provides the
person comparison on the Control Plane side; SessionDetails intentionally need not
add an owner field. Runtime ID must also identify the receiving pod. No new public
API, Python permission matrix, grant, SQL authority view or message proxy is needed.

Use the existing own-person credential provider and configured Control Plane URL.
M5a is not the resolver's delegation receiver: service-only and asserted-person
requests are refused, with existing JWT/admission checks retained. Do not create a
run, reuse an old run's authority or borrow its delegated credentials for history.
One fresh M5a GET is made per eligible conversation per consultation, with no auth
cache, inherited HTTP auth, redirects or transparent retry. The existing bounded
HTTP pool is reused and the provenance SQL connection is released first.

The shared guard covers message reads, session lists and checkpoint detail/index.
Local list candidates are owner-filtered; each is checked serially to bound pool
pressure, before any content read/return. Unknown, foreign, revoked, missing or
incompatible provenance is uniformly 404; indexes omit only those refusals.
Authentication failure and technical failure abort instead of fabricating empty or
partial successful history. A bound authorized conversation with zero messages is
empty; a metadata-only session without M4 provenance is unavailable until execution
creates its initial legitimate binding. Reads never adopt existing unbound data.

Instance deletion/disablement or unavailable template does not participate in M5a
read authorization. Execution preparation and M4 remain separate and stricter.
Aggregate checkpoint statistics have no conversation identifiers/content; mutation
and lifecycle APIs are unchanged. No frontend wiring or arc42 expansion to an
unvalidated journey. Evidence and unexecuted cases are in tasks.md and F25.

### 2. Consume one published authorization binding

At startup, use configured PostgreSQL access to read the singleton binding. Validate configured identity and the exact fetched model against the canonical Weaver contract; pin `active_store` and `model_id` on every check. Reuse the checked-in Control Plane model artifact; do not maintain a second hand-written Python schema.

Missing/mismatched binding, unsupported model or unavailable dependencies prevent readiness. Runtime does not select latest, create a store, synchronize a schema or fall back. Tuple checks use higher consistency and no cross-operation authorization cache. Binding replacement is not hot-reloaded: a future model rollout must coordinate consumers; it is not authorized here.

### 2a. Deliver core ReBAC before global admission filtering

On 2026-10-25, after reviewing the Swift admission rules, Dimi explicitly retained
all global admission features but deferred their port to a subsequent lot. The
next increment targets core Weaver ReBAC and its runtime integration. Rebuilding
the recent global filtering feature is not a prerequisite for that increment.

The deferred scope includes the filtering switch, identity-attribute allow/block
policies with all/any conditions, access-manager admission, individual exceptions,
authorized-team admission and Free-link-derived admission. Preserve the rules'
alternative admission paths and the verified-person semantics of delegated calls
when porting them. This is retained work, not removal of the product requirement.
Dimi did not select organization membership alone as a substitute global policy.

JWT validation, person/workload separation, trusted delegation, CGU, space/template
permissions and applicable lifecycle controls remain required within their agreed
scopes. Departure without automatic restoration remains required. The later
2026-10-26 turn-boundary arbitration in decision 5e supersedes the previously
accepted five-minute revocation bound for agent turns; it does not reinstate
reversible suspension. It does not pull conversation/run implementation into the
current startup increment.

Do not add a catalog mode, compatibility flag, temporary execution refusal or
replacement admission policy while waiting for filtering. Remove replaced legacy
wiring only within the implemented scope, preserving unrelated controls and shared
consumers. Earlier sequencing that made a complete filtering port a prerequisite
for core ReBAC is superseded. Core ReBAC progress must not be reported as complete
Swift admission parity, a working startup or a validated user journey without the
corresponding evidence. Tasks 1.4 and 4.1 track the separate deliveries.

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

The binding contains no roles, allowed-document IDs, FGA store/model IDs or bearer
tokens. Existing display/configuration fields remain ordinary product data.
Decision 5e adds trusted policy facts for one turn only: local operations enforce
that context, which cannot be reused as authority for a later turn. Derive
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

### 4. Resolve authority once per turn; enforce it locally

The accepted 2026-10-26 arbitration in decision 5e replaces per-operation authority
refreshes. The existing Control Plane resolver supplies one complete authorized
context at the start of each turn: canonical person/space/instance/template and
applicable admission/lifecycle/model-policy facts. Failure prevents that turn.
There is no second authorization HTTP call and no additional SQL/OpenFGA lookup
to refresh these decisions before LLM invocations, retries or child steps.

Every operation enforces the resolved limits locally. ReAct/Graph, structured
calls, reused clients, retries and descendants share the same turn context and
cannot broaden or renew it. Unknown authority never becomes unrestricted None.
Explicit cancellation, terminal-run checks and existing execution limits remain.
Resource-specific storage/publication filters and receiving services' own checks
are preserved; they are not permission to add a turn-authority refresh loop.
A refusal cannot become an ordinary tool result used to bypass the same boundary.

Revocation, source/instance/template disabling and confirmed model withdrawal
after admission are observed at the next turn. A started turn may finish with its
resolved context; data already emitted cannot be recalled. No polling or new
revocation service is introduced.

### 4a. Revocation is departure, not reversible suspension

Dimi's explicit clarification: there is no requirement to preserve a suspended
person's access/context for later restoration. A return follows ordinary newcomer
admission and does not automatically restore former memberships, runs or authority,
even if the identity provider reuses the same subject. Scope-specific access removal
must not accidentally remove unrelated access; departure revokes the applicable
whole Fred access scope.

The 2026-10-26 decision explicitly accepts next-turn detection for these changes.
It supersedes the prior five-minute revocation deadline and next-operation
authority rechecks for an admitted agent turn. No maximum turn duration is added
to recreate that deadline. Explicit cancellation, terminal cleanup and ordinary
execution limits remain separate requirements; a service-token renewal does not
start a new turn or revive a terminal run.

RunScope and delegated run records provide reusable terminal/cancellation state.
Their lack of an automatic authorization deadline is no longer an M4 gap to fill.
No claim of bounded provider-side cancellation is made.

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

### 5b. Organization administration and pod-owned capabilities

Dimi's accepted direction (2026-10-26) supersedes the no-tool-first delivery
sequence and the exclusion of capability/model administration in 5a. Complete
the Agents, Models and pod-scoped Capabilities administration contract first;
Applications and Knowledge Bases remain outside this slice. The arc42 introduction
and administrator journey express the agreed behavior, not implemented coverage.

An offered capability has exactly one logical runtime owner. Its identity is the
pair (runtime_id, capability_id); version and configuration describe that offering.
Two pods installing the same Python package do not create one global executable
capability. Templates can select only capabilities of their own runtime; validation
and execution return to that owner. The owner may be inherited from a trusted
enclosing instance rather than repeated in every stored configuration envelope.
SQL constraints and generated contracts must preserve this identity when the
data-model lot is implemented. This decision does not introduce a capability
microservice, dynamic loading or an OpenFGA object per capability.

The purpose is independent adoption of shared libraries, not proliferation of
capability variants. With three deployed pods using the same library, one team
can integrate, validate and deploy its new release without coordinating a rebuild
of the other two. Each pod retains responsibility for its configurations and the
supported runtime contract; a catalog entry must not impose a global library
version or replace another pod's declaration.

Organization administrators authorize agents and restrict eligible models;
activation never expands that model set. Existing routing must enforce it for
defaults, overrides and fallbacks. Capabilities explain functions, configuration,
dependencies and consumers under their pod; no independent user/capability grant
or grant-all-dependencies confirmation is retained. Template availability alone
does not approve new external destinations, credentials or data access. Platform
ownership of external connection configuration remains distinct from organization
choices. Resource/operation checks remain required; turn authority follows the
accepted admission boundary in decision 5e.

The same-name/two-pod case, isolation between organizations, forbidden-model
fallback and an unavailable external connection are acceptance cases for the
forthcoming implementation plan. Do not infer a completed physical SQL schema,
runtime wiring or performance gain from the conceptual ownership diagram.

### 5c. First administration increment: pod-owned catalog storage

The additive `0014` migration stores observations in `runtime_catalog`, offerings
in `runtime_capability`, and consumers in `runtime_template_capability`. Composite
primary/foreign keys preserve `(runtime_id, capability_id)`; one runtime key binds
the template's local identifier and its offered capability. Templates remain
executable pod definitions, not stored code. Instance tuning keeps its existing
trusted source runtime; this increment adds no instance-selection foreign keys.

`agents::catalog` validates complete normalized snapshots and replaces one pod's
inventory in a transaction, serialized by its runtime row. Duplicate identities,
conflicting descriptor provenance and links to absent offerings fail before writing.
Disappeared offerings are retained as unadvertised; failed discovery preserves the
last inventory and separately records unreachability. Version changes update only
that pod's offering. Neither observation flag proves execution readiness, installed
replica uniformity, configuration compatibility or permission.

The following increment connects this storage through the existing Python registry
and organization administration routes. No Swift catalog consumer is removed.

### 5d. Complete inventory and organization read/refresh

`GET /agents/capabilities` declares all installed registry entries of kind `tool`,
including entries without a consuming registered template. It reuses manifest
projection and template compatibility/selection rules. Agent/model/Application/KB
projections are excluded. Registered template links describe eligible consumers and
whether each is selected by default, not observed executions. A missing registry
fails in 503; `complete=true` and both collections are mandatory on the wire.
Field values/defaults, choices, patterns and UI hints are omitted from the inventory;
no MCP connection configuration or instance settings are read.

Control Plane resolves runtime identity and destination exclusively from platform
`runtime_catalog_sources`. GET `/organizations/{organization_id}/capabilities`
reads configured pods, including disabled sources, in one repeatable-read SQL
snapshot. Each row includes trusted runtime identity, enabled state, observation
(`not_observed`, `observed`, `unavailable`), timestamps, retained offers and links.
`advertised=false` means withdrawn in the last successful inventory; unavailability
never rewrites it. This shared deployment metadata contains no organization choices
and establishes neither execution readiness nor permission.

POST `/organizations/{organization_id}/capabilities/{runtime_id}/refresh` targets
one configured enabled source. Unknown sources return 404, disabled ones 409. The
non-redirecting request has a ten-second timeout and a two-MiB response limit.
Complete typed descriptors, local identities, provenance, duplicate entries/links
and dangling links are checked before SQL mutation. Valid snapshots commit in 204;
invalid responses return 502, HTTP/transport failures 503. Both failures record an
unavailable observation without deleting the last successful inventory.

Both administrative operations require AdmittedUser, organization placement,
active lifecycle and Manage through the existing space gate, with no platform-role
exception. After discovery, refresh reacquires the existing organization lock,
authorizes again and fences before persisting within that transaction. The store
accepts that transaction's connection, so authorization and catalog changes commit
together. No SQL connection survives the pod call. Read authorization is rechecked
after the SQL snapshot. Runtime identity is never accepted from browser connection
parameters; descriptor provenance is checked against the configured source.

No migration is added or applied, no instance/history/configuration or agent/model
permission is changed, and no external destination is approved. Runtime and Control
Plane OpenAPI/client generation accompany the routes. Functional checks remain
manual; administration UI and configuration saving are separate increments.

### 5e. Platform model catalog: accepted direction and M1-M3 scope (2026-10-26)

**Status:** Dimi accepted the arbitration below. M1-M3 are implemented locally:
platform discovery/persistence, organization policy, instance settings and resolver data.
Functional validation and migration application have not been performed. These
decisions supersede pod-owned model inventory/manual profiles in earlier sections,
not capability increments 5c/5d. M3 does not enforce policy in the runtime. The M4 implementation and final static
quality results are recorded at the end of this decision; M5 has not started.

#### Acquired direction and observed starting point

**Acquired:** approved discovery APIs are the only source of agent model offers.
Control Plane owns inventory and administrative decisions; an offer's identity is
`(source_id, upstream_model_id)`, independent of pods. Platform controls destinations
and credentials; pods execute. No per-pod manual model catalog, independent model
OpenFGA objects, Rust inference proxy, new orchestrator or second routing engine.
Agent authorization never expands organization model permission, including defaults
and fallbacks. Sources without compatible discovery are outside this initial scope.
Knowledge Flow embeddings and document processing are unchanged.

**Current code on weaver, inherited from Swift:**

| Evidence | Observed behavior and consequence |
| --- | --- |
| `libs/fred-runtime/fred_runtime/model_routing/catalog.py`: `resolve_discovery*`, `_resolve_discovery_payload`, `to_policy` | Pod fetches `/models` with `OPENAI_API_KEY`, 5 s/1 MiB/no redirects; hashes the upstream ID under a source namespace into chat profiles. Missing modality metadata is accepted; explicit non-chat entries are skipped. Common settings are merged; chat defaults must be manual. Identity construction is useful, ownership and defaults must change. |
| `libs/fred-runtime/fred_runtime/app/agent_app.py`: `_build_chat_model_factory`, `/models-catalog`, `/refresh`, `/detail`, `_resolve_agent_instance` | File/startup inventory, per-source prepare/activate/rollback and managed-turn URL refresh still exist. `base_url_from_models_url` derives inference from catalog URL. These are Swift paths present in the tree, not an integrated Weaver model journey. |
| `libs/fred-runtime/fred_runtime/model_routing/provider.py`: `select`, `_pod_fallback_selection`, `build_for_chat` | Forced platform binding wins; disappearance fallback selects a manual profile, then the manual default. Both `PLATFORM_BINDING` and `POD_FALLBACK` skip the final `usable_model_ids` check. Weaver must remove these exceptions, not just filter a picker. |
| `libs/fred-core/fred_core/model/factory.py`; `libs/fred-sdk/fred_sdk/contracts/context.py`: `ModelBinding` | Existing provider clients and strict non-secret settings are reusable. OpenAI construction requires process-wide `OPENAI_API_KEY`; per-source credential selection is not already supplied by the binding. |
| `apps/control-plane/src/agent_instances/{runtime,tuning}.rs`; `agents/{catalog,inventory}.rs` | Rust resolver returns canonical person/space/instance/template and saved tuning, without model policy. Explicit profile recommendations remain unconnected. Capability inventory/storage is already implemented locally and stays intact. |

The archived `discover-models-from-endpoint`, `configure-model-discovery-url` and
`normalize-model-discovery-catalog` changes explain this history; their manual
defaults, URL derivation, multi-pod activation and compatibility choices are not
the Weaver target. The specified journey in `02.3-agent-administration.md` is not
evidence of model enforcement. Its pod-profile wording is superseded here only;
update arc42 when the corresponding behavior is implemented and accepted.

#### Proposed ownership and minimal data

| Owner / record | Minimum meaning |
| --- | --- |
| Platform / approved source | Immutable `source_id`; approved discovery URL and protocol; separately approved inference API root/provider; catalog visibility scope and completeness contract; enabled state and revision. Discovery credential reference and pod inference credential binding are separate. Provision through platform deployment configuration initially; organization APIs cannot edit these values. |
| Control Plane / observation | Per source: `checked_at`, `last_success_at`, observation result (`not_observed`, `ok`, `unavailable`, `invalid`, `incomplete`), sanitized error and successful snapshot revision. Network work outside SQL, bounded; compare source revision before atomic publication. |
| Control Plane / discovered offer | Composite key, upstream ID preserved exactly; normalized optional metadata with provenance; `first_seen_at`, `last_seen_at`, `advertised`, `withdrawn_at`. Keep withdrawn rows for saved references. Display names never identify offers. |
| Control Plane / organization policy | Canonical organization ID, explicit set of permitted offer keys, revision and audit attribution; optional default and one disappearance fallback, both from that set. Missing policy/empty set permits none; discovery creates no grant. |
| Control Plane / instance configuration | Optional recommended offer key and bounded invocation options in the existing saved configuration; no URL, secret or independent model definition. Omitted PATCH preserves, null clears/inherits, explicit empty selections stay empty. |
| Agent Pod / execution | Supported clients, local source-to-credential bindings, network reachability and invocation checks. This connection configuration enumerates sources, not model lists or organization permission. |

Source/offer records cannot reuse `runtime_capability`: identity and lifecycle have
no runtime owner. Keep model policy separate from tool settings, with composite
references to observed offers; reuse existing instance storage and authorization
gates. These are logical contracts, not an approved SQL migration design.

**Profile decision:** no separately administered profile entity in this lot.
One offer plus approved connection settings and bounded invocation options covers
the demonstrated need. Preserve `ModelProfile`/`ModelRoutingPolicy` as internal
Python routing representations derived from the trusted binding, never as a second
catalog. A future need for several named, reusable configurations of one offer
would justify a profile; none has been established here. Transport timeouts remain
pod settings; temperature/token options do not change model identity or permission.

#### Discovery, credentials and the changed trust boundary

Propose one initial adapter: explicit `GET` catalog URL returning HTTP 200 and a
JSON object with `data[]` and unique, bounded, nonblank `id` strings. Do not normalize
IDs or follow redirects. Reuse the 5 s/1 MiB bounds initially. Reject invalid IDs,
duplicates, malformed/truncated responses and pagination/partial-result markers
unsupported by this adapter; never publish a partial replacement.

The [OpenAI list contract](https://developers.openai.com/api/reference/resources/models/methods/list)
provides IDs, creation/owner metadata and an optional shutdown date, not portable
modality, tools, reasoning levels or context/token limits. Retain Swift's typed
optional label/limit extensions as source-reported information; absent or invalid
optional values remain unknown. An announced shutdown is not observed withdrawal.
No inference from names, and no raw provider response exposed as configuration.

For initial chat use, accept either an approved source-wide chat guarantee or
supported, trustworthy per-model metadata from a mixed source. Retain inventory
membership separately from chat eligibility: failure to establish chat capability
is not evidence of model withdrawal. Unknown-modality offers remain inventory-only.
Tools, reasoning and limits remain unknown unless explicit supported metadata or
an approved source-wide guarantee establishes them; requirements needing unknown
features prevent readiness. No manually entered per-model catalog compensates for
missing discovery facts. Qualification is an explicit source contract or supported
metadata, not a fact proved by a successful GET.

Prefer a discovery-only bearer credential injected into Control Plane by platform
secret provisioning; store only its reference. Distinct credentials do not by
themselves establish distinct rights: record the provider's actual scopes. Public
discovery is an explicit source mode, never the default. Pod inference secrets stay local through
existing provider clients/provisioning; Fred person/service delegation tokens are
for the trusted Control Plane exchange, never credentials for arbitrary gateways.
Discovery and inference uses remain separately approved. Unsupported discovery
authentication waits for an agreed adapter; no silent use of a pod's inference key.

Rust now gains outbound gateway access and a discovery credential: this expands
its trust boundary. If the provider cannot separate list/inference rights, a
credential with inference authority requires explicit platform acceptance for that
source. Such a source is supported conditionally, not automatically excluded or
approved by this general design decision. Multiple OpenAI-compatible sources with
different inference keys also require a narrow
source-bound secret lookup before the existing factory, without mutating global
environment variables. Current factory behavior alone cannot safely provide it.

Approve `(catalog URL, inference root, provider, credential scopes)` together.
Do not strip `/models` to invent an inference destination. Validate destinations
against platform-approved routes, including internal gateways and their egress/TLS
policy; reject redirects, embedded credentials and caller-supplied overrides.
Bind each inference credential to its approved source/destination; a trusted binding
does not authorize sending an arbitrary local key to a new host.

#### Observation lifecycle and source changes

Propose explicit refresh on onboarding/admin action, no polling service. Reads use
the persisted snapshot. A valid complete snapshot updates `last_success_at` and
observed offers atomically; omission confirms withdrawal only under the approved
source's completeness contract for the same visibility scope. The standard list
has no universal completeness proof: a 200 response alone cannot establish it.
An endpoint silently truncating its list cannot be detected from IDs alone; without
that upstream guarantee, it is ineligible for authoritative withdrawal in this lot.

Failure, invalid data or an explicitly incomplete result updates attempt status
only, preserving last success, offers and permissions. Empty is authoritative only
under the same completeness guarantee. Reappearance restores observation of the
same key, not a new grant; retained choices may work again only if still permitted.
Revoked choices stay revoked. Successful refresh never edits saved selections.

Retain existing permitted selections during a discovery outage while
the source remains approved and the last successful snapshot advertises the offer;
label it stale and block new selections until refresh succeeds. Actual inference
may still fail. An outage never activates disappearance fallback. Source disabling
or confirmed withdrawal is accounted for in the next turn's resolution. An already
admitted turn keeps its fixed context; provider failures can still stop inference.

Do not reuse a source ID for another destination, provider account, visibility
scope or model namespace. Such changes create a new approved source and require
explicit re-selection/re-authorization; old references remain diagnosable. In-place
credential rotation with unchanged scope, or label changes, may retain identity
with revision fencing. An in-flight old refresh cannot publish over a new revision.

#### Administrative and pod contracts

Proposed routes: `GET /organizations/{id}/models`,
`POST /organizations/{id}/model-sources/{source_id}/refresh` (no URL in the body),
and `GET/PUT /organizations/{id}/model-policy` for permitted keys, default and
fallback, with expected revision on writes to prevent lost updates.
Reuse AdmittedUser, active placement/lifecycle and organization Manage, including
post-fetch reauthorization/fencing. Source provisioning remains platform-owned.
Refresh is a shared observation, never an organization grant. Organization responses
contain identities, safe metadata/status and that organization's choices, not URLs,
secret references or other organizations' policies. Runtime selection uses the
canonical owning organization, including for a personal-space instance; missing or
ambiguous ownership is refused, never inferred from a browser organization field.

Rust validates known composite identities, current advertised/source state, policy
membership, default/fallback/recommendation consistency and typed allowed options
when saving. Revocation preserves settings/history and exposes affected choices as
unusable; revocation must not be blocked by an old default/recommendation.
Metadata-only edits preserve these references without making them executable. Rust
cannot prove a particular pod's credentials, connectivity, provider compatibility
or current upstream execution permission from discovery.

Extend the existing authenticated runtime resolver, not a new execution service:
canonical context plus policy/source/snapshot revisions, allowed candidate offer
keys, resolved non-secret connection settings, declared feature facts and explicit
recommendation/default/fallback references. Browser input supplies only a requested
offer key and allowed options. Resolve it against trusted data; never accept a
browser binding, destination, credential reference or permission set.

The pod adapts those candidates to the existing router/clients. Selection precedence
is explicit user choice, instance recommendation, organization default; no arbitrary
first-model default or privileged forced binding. A template requirement can narrow
the set or make it unavailable, never expand it. An explicit forbidden choice is
refused. A confirmed withdrawn but still permitted choice may use the configured
fallback only if that fallback is itself advertised, approved, permitted and locally
usable; otherwise explicit failure. Record requested/actual keys and fallback reason.

#### M4 turn-boundary arbitration (2026-10-26, accepted)

Dimi explicitly chooses one clear, complete call to the existing Control Plane
resolver per turn, followed by local enforcement. Enrich that interaction; do not
add a second call at turn start or query SQL/HTTP/OpenFGA to refresh authority on
each LLM invocation. Ten LLM calls in one turn cause no additional turn-authority
reads. This replaces the earlier narrow SQL view/role/connection proposal; no such
M4 read access or grant is to be implemented.

The context fixes the authorized person, space, instance/template and model set,
recommendation/default/fallback, known features, options and approved connections
for that turn. Check the actual selected offer locally on every invocation with
no platform/fallback exemption. ReAct/Graph steps, structured calls, reused
clients, retries and descendants must remain within that same context. They do
not constitute a new turn, acquire broader rights or renew its authority. A child
target not covered by the admitted context must not gain authority implicitly.
The next turn obtains its own context; no reuse after turn termination.

Permission revocation, decommissioning of a person/instance/template/source and
model withdrawal after admission are accepted until the next turn. A started turn
may finish. This supersedes the previous next-invocation recheck and five-minute
revocation guarantee for these changes. Explicit cancellation, terminal-run
checks, ordinary execution limits and resource-specific data/service checks remain
distinct. No timer, maximum turn duration or periodic authority check is added to
restore the superseded guarantee. Credential renewal cannot revive a completed
turn. A turn-start resolver refusal/failure prevents execution; it never permits
reuse of a previous turn's context.

Fallback is based on confirmed withdrawal in the turn's resolved facts and the
explicit allowed fallback; provider errors or mid-turn discovery failures cannot
invent a withdrawal or broaden the set. Initial inference support is limited to
OpenAI-compatible sources, as accepted by Dimi. Bind each source's inference
credential locally without process-wide environment mutation; other provider
adapters remain explicitly unavailable until separately connected.

Static framing found that the pod still calls the Swift /teams/... resolver while
Weaver exposes /spaces/..., computes usable models once per turn, and retains the
platform/fallback bypasses. Existing RunScope cancellation and credential providers
are reusable. M4 must replace the scoped resolver/routing consumers and enforce the
complete turn context; no shared per-invocation remote gate is presumed to exist.
This is accepted framing only: no runtime change or validation is claimed.

#### Accepted arbitration and deferred execution detail

| Decision | Accepted direction and consequence |
| --- | --- |
| Discovery access | Prefer genuinely read-only discovery rights. If the provider cannot separate them, require explicit platform acceptance of Rust's broader authority for that source; no automatic exclusion or secret transfer from pods. |
| Qualification and withdrawal | Accept chat-qualified sources and mixed sources with reliable supported per-model metadata. Completeness is required to confirm absence; chat eligibility is independent of inventory membership. |
| Outage behavior | Keep existing last-known permitted selections, block new selection writes, no outage fallback or automatic inventory expiry. Authorize at turn start; resolver failure blocks that turn. |
| Selection | Direct offer references for user choice, recommendation, organization default and one removal fallback; no administrable profile or privileged forced binding. |
| Turn authority | One complete resolver call per turn; every invocation/retry/descendant enforces its fixed context locally, without platform/fallback exemptions or additional authority reads. Changes take effect next turn; no M4 SQL projection/grant. |

M1-M3 are implemented locally; M4-M5 remain separate. No real source, credential
grant, deployment or runtime access is approved implicitly.

#### M1 implementation boundary (2026-10-26)

`model_catalog::{config,discovery,store}` owns the rules. Migration 0015 adds only
`model_source` (approved non-secret configuration plus observation) and
`model_offer` (composite source/upstream identity with exact C collation). Pod
capability tables cannot represent this independent owner/lifecycle. Existing
migrations and capability work are preserved. `platform.model_sources` is empty
by default; `serve` only synchronizes approvals, never discovers models.

Configuration changes require a strictly higher positive revision; same revision
with different content and old revisions are refused. Destination/provider/scope
changes require a new source ID. Sources must be disabled at a higher revision
before omission; retained disabled rows prevent identity reuse. Configuration
application is atomic and serialized in SQL; each refresh uses a per-source token.
Last-started refresh wins, even if the newer attempt fails or is cancelled: older
results cannot overwrite it. Cancellation leaves the previous observation/snapshot
intact, and a subsequent explicit refresh supersedes the abandoned token. All
network work occurs between two short SQL transactions. The publication lock
rechecks configuration equality and the token, then updates offers and observation
together; failures touch the observation only. Reads use repeatable read.

The implemented adapter is deliberately conservative about completeness: unknown
envelope keys and HTTP pagination/range headers are incomplete. Only a configured
full-list guarantee allows publication, including an empty inventory. Mixed-source
chat qualification supports exactly boolean `capabilities.completion_chat`;
missing/invalid values remain unknown without dropping inventory members. Typed
label/token-limit extensions retain source provenance; tools/reasoning and other
unsupported feature facts remain unknown. The [component contract](../../../apps/control-plane/README.md#platform-model-inventory-and-organization-administration)
defines configuration, bounds, supported fields and operator revision semantics.

`refresh` and consistent `inventory` remain internal Rust operations; M1 grants no
user authority. M2 routes use the split claim/publication operations described below
rather than the independently committing internal refresh wrapper. Discovery credentials reuse ENV_FILE/process lookup only; SQL
stores references and typed metadata, never bearer values or raw response bodies.
Account/namespace and actual credential rights remain platform attestations;
neither GET nor a separate key proves them. No real source is configured.
Quality/generation evidence and unexecuted manual cases are in tasks.md and F25.

#### M2 implementation boundary (2026-10-26)

The four proposed administrative routes above are implemented in `model_catalog/http.rs`;
the [component contract](../../../apps/control-plane/README.md#platform-model-inventory-and-organization-administration)
is authoritative for payloads, status codes and limits. No source provisioning API,
manual offer route, model OpenFGA object, UI or runtime consumer is added.

Migration 0016 adds `organization_model_policy` and `organization_model_permission`.
Neither existing capability data nor shared source observations can hold these
organization decisions without mixing owners/lifecycles. Offer references are
composite foreign keys; deferred policy-to-permission foreign keys enforce that
both explicit choices belong to the same organization's permitted set. A trigger
requires organization placement. Policy/permissions cascade on physical organization
purge; retirement and person departure do not erase these organization decisions.
Revision starts at 0 for an absent policy and increments on each atomic replacement;
SQL timestamps and verified subject record creation/update attribution.

PUT runs under the same platform/organization locks and FGA guard/fence as capability
administration. Expected-revision comparison and SQL mutations share that transaction.
Only new permissions and changed non-null choices require an enabled source,
successful current-revision observation, advertised presence and established chat
qualification. Candidate rows are locked in source/key order against refresh and
configuration changes. Retained unavailable choices do not block reductions or
clearing; a revoked default/fallback must explicitly be cleared or replaced in the
same request. Failed discovery, configuration revisions and withdrawals never edit
policy or choose a substitute. Reads pair retained references with diagnostics.

M1 now exposes transaction-scoped `claim` and `publish` internally. Administrative
refresh authorizes before claim, commits and releases SQL before HTTP. On completion
it reacquires platform/organization locks, captures the guard, rechecks current
consent, placement, active lifecycle and Manage, fences, then publishes using that
same transaction. No publish-then-authorize path exists. M1 exact configuration,
latest-started token, source isolation and last-success retention rules still apply.
Denied completion leaves the last snapshot unchanged and its token supersedable.

Authorization cost uses existing primitives: each gate performs paginated FGA
Read of the subject's direct `space:` roles, SQL placement, and one Manage Check.
GET has two gates; PUT two gates plus one pair of platform/organization guard Reads
and one fence Write; refresh three gates plus two such guard/fence phases. Counts
are client operations, not server evaluation cost; role pages scale with subject
memberships, not offers. Fences change only existing scope revision tuples (two
deletes and two writes), never model grants. The existing global lock also serializes
these short administrative writes across organizations, as in capabilities. SQL
holds those locks during FGA calls and bounded local mutations, never discovery.
Inventory reads use four SQL queries in one snapshot regardless of source count;
policy candidate validation is one batch query, bounded to 4096 permitted offers.
These are code-derived costs, not performance measurements.

Swift's source authority and secret isolation become platform configuration in M1;
M2 reuses Weaver admission/organization Manage for SQL administration, replacing no
runtime enforcement point. Security and concurrency evidence remains the unexecuted
M2 acceptance cases in tasks.md, not a claim of Swift runtime equivalence. Migration
application, provider calls and functional tests were deliberately not performed.

#### Convergence and limits

Reuse identity validation/deterministic internal IDs, per-source atomic publication,
revision fencing, sanitized failures, strict `ModelBindingSettings`, provider/client
construction, credential renewal/delegation, the router and invocation telemetry.
Do not port model enablement through Swift capability FGA grants.

Replace consumers before removing their old owners, in the same scoped cutover:

| Obsolete target path | Consumers to adapt before deletion |
| --- | --- |
| Agent-pod `ModelCatalog` file loading/discovery and `/agents/models-catalog{,/refresh,/detail}`; prepare/activate/rollback across pods | `agent_app.py` startup and `_resolve_agent_instance`, `RoutedChatModelFactory` refresh state, pod configuration loader, image/catalog mounts; FeaturesPage discovery/detail/manual tabs and legacy capability projections. Rust must not aggregate pod model inventories. |
| `default_profile_by_capability.chat`, agent overrides, manual disappearance fallback, free-form platform binding | SDK context/binding and `AgentTuning.recommended_chat_profile_id`, provider/resolver inputs, Rust instance tuning/resolution/preparation, form recommendations and chat selectors. Defaults/fallbacks become explicit discovered offer references; absent replacement fails, never recreates a hidden manual profile. |
| `usable_model_ids` model FGA and platform/fallback exceptions | Shared model gate, ReAct/Graph/structured and creation-assistant client paths; adapt retained consumers or keep their feature unavailable. `build_chat_for_profile` alone is not an authorization check. |

Existing saved profile IDs require explicit unambiguous mapping/re-selection in
the future cutover; never guess by display/wire name or silently reset settings.
No parallel compatibility mode, dual authority or automatic data migration here.
Shared catalog/provider modules may have non-agent consumers: remove only the
replaced agent paths after checking them, preserving Knowledge Flow embeddings.
Provider-specific discovery, arbitrary detail passthrough, manual models, inference
probes, UI/chat/Applications/KB adaptation and execution changes are outside this
framing sub-lot. Later wiring is mandatory before calling the target executable.

#### M3 implementation boundary (2026-10-26)

Dimi authorizes exactly `temperature`, `max_tokens`, `top_p`, plus targeted frontend
contract adaptations preserving the current UX. Instance POST/PATCH/GET reuse tuning
JSON, space Write/template Use, the existing platform/organization transaction and
M2 `require_selectable`. New recommendations are composite keys. Options replace as
one typed object; omitted PATCH fields preserve, null recommendation clears, null
options resets. No schema migration, source activation or provider request is needed.
Detailed wire semantics, bounds and diagnostics have one home in the
[component contract](../../../apps/control-plane/README.md#instance-recommendations-and-resolver-data-m3).

Changed non-null recommendations validate the current owning-organization policy
inside the write transaction, then share-lock the selected source/offer using M2's
selection rule. Policy writers use the same organization lock; source configuration
and publication cannot invalidate the locked facts before commit. Options are checked
structurally and against known recommendation/default output/context bounds. These
bounds are necessary, not proof of provider support or a prompt's remaining budget.
Metadata edits and explicit clears preserve other settings and do not depend on
successful discovery. Retained forbidden/withdrawn references never become candidates.

The existing resolver reads instance, policy, offers, source revisions and approved
connections in one repeatable-read snapshot. It returns permitted keys, candidates
according to known facts, selection freshness, typed diagnostics and explicit
recommendation/default/fallback references; it chooses no model. Outage retains
last-known candidates at the same source revision but prevents new selections.
Unknown local support and credentials remain the pod's responsibility. Explicit
choice precedence, forbidden-choice refusal and withdrawal-only fallback remain
the M4 invocation contract, not claimed enforcement in M3.

Swift's authenticated person/workload distinction remains at `RuntimeCaller` and
`RuntimeQuery::subject`; canonical placement, consent, template Use and instance
state still gate resolution. The only added connection disclosure is to already
trusted delegated workloads, for candidate offers. Person calls, instance CRUD and
organization administration receive no connections. SQL supplies the approved
inference destination and provisioning reference; discovery authentication never
enters the DTO and no secret is resolved. Initial and final authority checks happen
outside the snapshot transaction. M3 returns data only; M4 will bind that trusted
response to one admitted turn under the later arbitration above, never across turns.

Old `recommended_chat_profile_id` values remain in SQL/ordinary reads as diagnostics;
non-null new writes are rejected. They are removed only from the resolver's
configuration copy, with the original string in `models.legacy_profile_id` and
`requires_reselection` when no composite recommendation exists. Explicit re-selection
does not silently erase the old string. No legacy resolution or automatic conversion.
The existing form displays the composite key or legacy string in the same disabled
text control, updates its explanation, and omits model settings on save. No new
selector, option control, organization flow, chat wiring or layout change.

Verification and unexecuted acceptance for the M3 delivery are recorded in tasks.md
and F25. The following M4 increment supersedes that delivery's runtime starting point.

#### M4 implementation and technical close-out (2026-10-26)

The Python admission path now calls `/spaces/{space}/agent-instances/{instance}/runtime`
once with the existing delegated workload credential. Rust echoes the admitted run
and conversation identifiers; Python checks subject, space, instance, runtime,
conversation, template and the complete typed model snapshot. Missing, denied,
incomplete or inconsistent resolution refuses admission, without Swift fallback.
The resolver also refuses an unavailable configured runtime, preserving the native
Rust runtime. Connection disclosure remains restricted to trusted delegated workloads.

A turn begins at external execute/stream/evaluate admission and owns one RunScope.
The private TurnAuthority is single-use and never part of RuntimeContext, graph
state or checkpoints. Provider/middleware retries and internal descendants reuse it;
only the resolved template is covered, so other template invocations are refused.
Terminal completion, cancellation, disconnect and a HITL pause close it. A later
resume is a new admitted turn with a new resolver result. Retained model clients
cannot authorize subsequent sends from another scope or a terminated scope.
Revocation or withdrawal after admission takes effect next turn; there is no
five-minute deadline, authority refresh, watcher or per-token SSE check.

The existing model resolver/factory selects explicit composite choice, instance
recommendation, then organization default. Forbidden choices and old profiles are
refused. Only confirmed withdrawal can select the explicit permitted, usable
fallback. Availability or provider failures cannot select another model. ChatOpenAI
invocation guards and request guards on shared HTTP transports retain these checks
through bind_tools, structured output and SDK retries: source, destination,
credential, actual model and supported options remain bound to the active turn.
Source credentials are locally provisioned by reference and environment-variable
name, never fetched from Control Plane or switched in the process environment.
Knowledge Flow retains the core factory's default behavior.

Conversation provenance extends the existing `checkpoint_thread_owner` table with
nullable `binding_json` (subject/space/instance/runtime/template identifiers only).
It grants no model authority and causes no per-invocation SQL read. The existing
lazy table setup contains the additive DDL; it was not applied in this work.
Existing conversations without that provenance are refused rather than rebound.
Clearing owner/checkpoint provenance while retaining history also requires an
explicit migration/recovery decision; no silent reconstruction is provided.

Removed: Swift team resolver execution, pod model discovery/catalog/authz modules,
YAML profiles and their startup/Docker/Helm wiring, local policy/profile contracts,
PLATFORM_BINDING/POD_FALLBACK bypasses and their obsolete profile/catalog tests.
Prepared Weaver cases are retained. After Dimi explicitly authorized the public
contract removal, the three old `/models-catalog` routes and their four private DTOs
were deleted too. The runtime OpenAPI and RTK client were regenerated; no handwritten
application consumer remains. There is no compatibility execution or discovery.
OpenAI direct-template and creation-assistant execution return explicit 503 until
connected; skill metadata uses a separate person-authenticated read of `/spaces`
without admission or trusted inference connections, requiring canonical space.

Canonical SDK, runtime/Control Plane OpenAPI clients and pod/chart schemas were
updated. Technical results and precise remaining work are in tasks.md and F25.
Dimi subsequently requested final technical closure: all six affected component
quality checks passed, along with chart/schema checks, strict OpenSpec and diff
whitespace validation. Corrections removed stale catalog fixtures/examples and
updated API descriptions; affected checks were rerun. M3 recommendations and
three instance options remain in the central resolver snapshot and are consumed
directly by the local router/factory, independently of prompt/capability tuning.
Functional scenarios remain prepared and unexecuted. No tests, providers,
migrations, deployment, commit or push were run. M4 is technically complete;
the chat/UI journey is not validated and M5 is out of scope.

### 6. Preserve guarantees and remove old owners

| Swift guarantee / enforcement | Weaver owner / replacement | Removal or proof condition |
| --- | --- | --- |
| JWT and asserted-principal checks in `security/delegation.py` / OIDC | Existing auth plus canonical identity mapping and Rust trusted-delegation receiver | Retain mechanism; prove person/service confusion and forged assertion rejection |
| Credential renewal and live-run providers | Same providers and run lifetime | Retain; renewal does not widen the admitted turn or revive completed authority |
| `organization.suspended`, `platform_access_*`, old user/team admission | Canonical Weaver admission and account-state enforcement | Departure/revocation replaces reversible suspension; apply the accepted next-turn boundary and no automatic restoration, without restoring old tables |
| `_authorize_execution_or_raise`, team/personal/service shortcuts | Turn-start resolution and local context enforcement | Replace together; no service-token or platform-role content bypass |
| `agent_instance`, tuning validation, CRUD and preparation | Rust management with the existing product/configuration semantics | Add missing persistence/routes; adapt space/authz boundaries, not the agent definition or tuning language |
| Session metadata and session/checkpoint ownership | Rust keeps the metadata/index; runtime retains messages/checkpoints and enforces the canonical association | Reconnect the current chat; no runtime-history rewrite or second message store |
| `capability_authz.py`, legacy model/capability enablement | Template-authorized configured dependencies, using existing registry/routing | Replace scoped FGA enablement calls with configured-set and availability checks; keep operation/data restrictions |
| Knowledge Flow search/read authorization and HTTP clients | Local shared document primitive | Replace scoped consumers, then remove unused clients/registrations; unrelated live consumers require their own lot |

## Risks / Trade-offs

- **Missing managed-agent APIs** -> Lot 1 restores their identified Swift responsibilities in Rust. Catalog discovery is not instance persistence or execution readiness. The work includes backend endpoints/schema and frontend bindings, not only a Python ReBAC adapter.
- **Accepted revocation latency** -> An admitted turn may finish after authority changes. Detect changes at the next turn; do not claim a five-minute bound or add remote per-invocation reads. Preserve explicit cancellation and terminal cleanup.
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

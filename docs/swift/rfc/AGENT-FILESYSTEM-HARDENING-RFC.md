# RFC: Agent Filesystem Hardening and Completion

**Status:** proposed follow-up; no implementation approved by this RFC alone
**Author:** Dimitri Tombroff
**Date:** 2026-06-26
**ID:** AGENT-FILESYSTEM-HARDENING
**Tracked items:** `FILES-04`, `FILES-05`; linked security dependency `RUNTIME-07`
**Related docs:** `docs/swift/design/FILESYSTEM.md`, `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` §8.11

---

## 1. Problem

The agent filesystem is now largely implemented. The previous broad target RFC was
removed so the current knowledge lives in two places only:

1. `docs/swift/design/FILESYSTEM.md` for as-built behaviour;
2. this RFC for fixes and completion work.

This split avoids keeping old `/workspace`, `/agent/<agent-id>`, and broad target
material around as competing implementation guidance.

The main architectural gap is that agent isolation is currently enforced by the v2 runtime
adapter, while the raw Knowledge Flow `/fs` boundary still sees a normal user token and
team ReBAC. That is acceptable for a trusted first-party runtime path, but it is not the
final security model for classified or multi-tenant deployments.

## 2. Current as-built baseline

The shipped product model is:

```text
/corpus/...                                                  # Resources, read-only
/teams/{team}/users/{uid}/...                                # Mon espace
/teams/{team}/shared/...                                     # Espace d'equipe
/teams/{team}/agents/{agent_instance_id}/users/{uid}/...     # Agents
```

The v2 runtime adapter maps bare agent writes to the current agent instance's own
`agents/{agent_instance_id}/users/{uid}` subtree and rejects writes outside that subtree.
Knowledge Flow enforces team `CAN_ACCESS_FILES`, team `CAN_UPDATE_RESOURCES` for `shared/` writes,
and uid ownership for `users/{uid}` and `agents/{agent}/users/{uid}`.

Provenance is path-derived. Share-by-copy exists and writes into
`teams/{team}/shared/files/{basename}` with a deterministic suffix on name collisions.

## 3. Findings

### F1 - Raw `/fs` does not validate a signed agent filesystem principal

Runtime SDK isolation is implemented, but Knowledge Flow receives only a
`KeycloakUser`. It cannot know whether a write to:

```text
/teams/{team}/agents/{agent_instance_id}/users/{uid}/...
```

was made by the matching runtime agent instance or by another first-party caller using
the user's bearer token. It also cannot distinguish a human caller from an agent caller
for `shared/` writes. This is the deferred G1b gap from FILES-04.

### F2 - The filesystem principal depends on ExecutionGrant hardening

> ⚠️ **Dependency changed (2026-06-27 — RUNTIME-07 rev. 2, RFC D5).** `RUNTIME-07` no longer
> produces a **signed grant**. The agent filesystem principal must therefore derive from the
> caller's **Keycloak JWT identity + the pod's verified execution scope** (the same
> JWT+OpenFGA context the pod authorizes with), **not** from a control-plane-signed grant.
> Any "signed execution grant" reference in F2/P1 below is obsolete — re-spec against the new
> model in `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` §8.11.

The filesystem should not invent a parallel identity system. The correct source of agent
identity is the managed execution grant and runtime context. This RFC therefore depends
on `RUNTIME-07` for a signed grant and runtime-verifiable execution scope.

### F3 - SDK and runtime docs still describe stale bare-path semantics

Several docstrings and contracts still say a bare path is the acting user's private
space or that `shared/` can be used to write to the team. Current runtime behaviour is
different:

- bare write -> current agent's Agents subtree;
- `shared/...` -> readable team shared path;
- write/delete to `shared/...` -> rejected by runtime adapter.

This is documentation drift that can mislead agent authors.

### F4 - Graph runtime template resolution is not aligned with ToolContext

`ToolContext.resolve_template(name)` checks:

1. Mon espace `templates/{name}`;
2. Espace d'equipe `templates/{name}`.

Graph runtime still checks `templates/{name}` through `read_bytes`, which now resolves to
the agent's own Agents subtree, then `shared/templates/{name}`. This is probably an
incomplete migration.

### F5 - `read_resource` is a surface placeholder

`ctx.read_resource(path)` exists for the desired Resources/corpus helper, but currently
raises `NotImplementedError`. Agents must use search/RAG tools for corpus content.

### F6 - Share-copy provenance is incomplete

The current implementation derives `shared_copy` from the destination path
`shared/files/...`. It does not persist:

- original source path;
- original origin/producer;
- `shared_by`;
- `shared_at`.

Earlier target notes claimed those fields would be added; the implementation does not
yet do that.

### F7 - Share-copy no-clobber is not atomic

The service lists existing names, chooses a suffix, then writes. Concurrent copies of the
same filename can race and select the same destination.

### F8 - Large file transfer buffers in memory

`/fs/upload` reads the whole multipart file before writing. `/fs/download` reads all bytes
and returns `Response(content=data)`. This is acceptable for current templates/decks but
not for large files.

### F9 - Browser path encoding is weaker than runtime path encoding

The runtime client percent-encodes reserved path characters while preserving `/`.
The Files UI uses `encodeURI(...)` in some `/fs/download` and copy-to-shared paths.
Filenames containing `#` or `?` may be interpreted as fragments or query delimiters.

### F10 - SDK `FsEntry` does not expose provenance

Knowledge Flow stamps provenance on file list/stat responses. The SDK `FsEntry` model
currently exposes only `path`, `size`, and `is_dir`, so SDK authors cannot see the same
origin signal the UI shows.

## 4. Proposed work packages

### P1 - Signed workspace principal at the `/fs` boundary - SUPERSEDED (2026-09-02)

**Do not build this.** The finding it answers (F1) is real and still open, but the
solution is abandoned: it depends on a signed `ExecutionGrant` that RUNTIME-07 rev. 2
dropped, and `#1853` is closed. Building an ad-hoc signature scheme for a surface that is
being deleted would be work spent twice.

F1 is closed structurally instead, by the scoped WorkspaceService of `#2328` (§9 below):
the Workspace contract has no "list the teams" operation at all, and the namespace is
derived server-side rather than asserted by the caller. The `can_access_files` relation
merged in `#2476` already closed the narrower gap - marketplace visibility no longer
doubles as filesystem access.

The original proposal is kept below for the record only.

Introduce a narrow runtime-to-Knowledge-Flow workspace principal derived from the signed
execution grant:

```text
actor_type = "agent" | "human"
team_id
user_id
agent_instance_id   # required when actor_type = agent
grant_id / jti
expires_at
signature
```

Knowledge Flow uses it only for filesystem authorization. It must not replace normal
Keycloak authentication; it adds the missing actor scope.

Rules:

- agent writes are allowed only under
  `/teams/{team}/agents/{agent_instance_id}/users/{user_id}/...`;
- agent delete follows the same rule;
- agent reads may include its own agent space and allowed team/user helper reads;
- agent writes to `/teams/{team}/shared/...` are rejected even if the user has
  `CAN_UPDATE_RESOURCES`;
- human calls keep the existing ReBAC behaviour.

This should be implemented after or alongside `RUNTIME-07`, not as an independent signing
scheme.

### P2 - Align SDK, graph runtime, and docs with shipped path semantics

Update the SDK/runtime documentation and helper implementations so they say and do the
same thing:

- bare `write` means agent output;
- explicit `read_user` means Mon espace;
- explicit `read_team` means Espace d'equipe;
- graph `resolve_template` should match `ToolContext.resolve_template` unless a separate
  agent-space template override is deliberately desired and documented.

### P3 - Complete share-copy metadata or document it as intentionally lightweight

Choose one of two paths:

1. Keep path-derived share-copy provenance only and amend the broad RFC accordingly.
2. Add stored metadata for `source_path`, `source_origin`, `shared_by`, and `shared_at`.

If metadata is added, list/stat should merge stored metadata with path-derived defaults.

### P4 - Atomic no-clobber copy

Replace list-then-write suffix selection with backend-supported conditional creation when
available, or a small retry loop that detects destination conflicts and re-suffixes.

### P5 - Large-file transfer decision

Resolve FILES-05 with one of:

- true streaming proxy through Knowledge Flow;
- hybrid presigned URLs for S3/GCS-style backends plus streaming fallback;
- explicit size caps until streaming lands.

### P6 - Browser path encoding hardening

Adopt a shared frontend helper equivalent to the runtime client's path encoding:

```text
encode each segment with encodeURIComponent, then join with "/"
```

Use it for download, upload, delete, mkdir, share, and copy-to-shared route paths.

### P7 - SDK provenance exposure

If provenance is an author-facing feature, extend `FsEntry` and runtime parsing to expose:

```text
origin
producer
created_by
modified
```

If provenance remains UI-only, keep `docs/swift/design/FILESYSTEM.md` explicit that this
is a UI/KF response signal, not an SDK listing contract.

## 5. Recommended sequencing

1. **P2 + P6 first.** Low risk, fixes misleading contracts and path buglets.
2. ~~**P1 with RUNTIME-07.**~~ Superseded - see P1 and §9.
3. **P5.** Decide streaming/presigned before large deployments rely on `/fs`.
4. **P3 + P4.** Share-copy metadata and atomicity are correctness polish.
5. **P7.** Decide whether SDK provenance is product surface or UI-only.

## 6. Contract impact

- `docs/swift/design/FILESYSTEM.md`: already rewritten as the as-built source.
- `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`: the M2M workspace binding of §9.1
  (`team_id`/`agent_instance_id`/`user_id`/`session_id`/`exchange_id`) travels as
  `RuntimeContext` fields already defined there - no new field is added; a dated entry is
  required once the runtime's M2M client wiring (§9.10) ships, documenting how the binding
  is attached to the outbound Knowledge Flow call.
- `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`: required once §9.5's internal
  binding-validation endpoint exists - a dated entry documenting it, following the existing
  service-agent team gate precedent (EVAL-03/RFC EVAL-AUTH, Solution A).
- `fred-sdk` contracts: `WorkspaceFsPort` loses `delete` (§9.3) and `link_for` returns a
  durable reference (§9.6); update the docstrings and optionally `FsEntry`.
- `fred-runtime`: `DeepAgentRuntime`'s `FredWorkspaceBackend` (§9.8) is new adapter code in
  a later PR, not a `fred-sdk` change.
- `knowledge-flow-backend` OpenAPI: the Workspace routes are new surface, and `/fs/share`
  is removed - regenerate the client in the same change.

## 7. Test plan

- SDK tests: stale doc fixes do not need tests, but any helper behaviour change does.
- Frontend tests: reserved-character filenames in download/share/copy paths.
- Large file tests: streaming or size-cap tests depending on FILES-05 decision.
- Share-copy tests: concurrent collision test if atomicity is implemented.
- Deep Agents adapter tests (§9.8 `edit`/`glob`/`grep` composition, bounded traversal
  limits): scoped to that later PR, not this one.

**§9.5 binding validation, split by the boundary each test actually exercises:**

Control Plane tests:
- only the exact configured Knowledge Flow M2M client can call the internal validator;
- another `service_agent` client (e.g. the evaluation worker's) is refused;
- a token with no `azp`/client-ID claim, an empty claim, or a claim that does not match
  the configured expected client is refused, even carrying `service_agent`;
- an unknown, unowned, or otherwise mismatched session is refused;
- an unknown, wrong-team, disabled, or suspended agent instance is refused (the shared
  usability predicate, §9.5);
- a valid binding succeeds.

Knowledge Flow tests:
- only the exact configured runtime/agentic M2M client can present an agent binding;
- another `service_agent` client, and every human JWT, are refused on `write`;
- a token with no `azp`/client-ID claim, an empty claim, or a claim that does not match
  the configured expected client is refused, even carrying `service_agent`;
- a control-plane denial, timeout, connection failure, or malformed response all fail
  closed, identically;
- the Workspace operation is not performed after a validation failure - not even partially;
- both actors per §9.7/§9.1a - human read-only (`list`/`read`/`link` only, `write`
  rejected outright before any ReBAC check), agent read-write, a user token refused as an
  agent caller, a mismatched `agent_instance_id` rejected, human `/fs` behaviour preserved;
- the `workspace.binding_validation_latency_ms` KPI is emitted with only bounded
  (`PROMETHEUS_ALLOWED_LABELS`) dimensions.

Runtime tests:
- keep existing path isolation tests; add graph `resolve_template` parity tests;
- the outbound Workspace call authenticates with the runtime's M2M provider, never the
  human's access token;
- binding fields (`team_id`, `agent_instance_id`, `user_id`, `session_id`, `exchange_id`)
  and trace context are propagated onto that call correctly;
- `LocalRegistryAgentInvoker` preserves the parent's `agent_instance_id` when constructing
  the child's execution request (§9.4) - not `None`;
- `user_id`, `team_id`, and `session_id` remain consistent between parent and child across
  that same delegation;
- a delegated child sees the same authorized workspace subtree as its parent - the
  `TODO.md` proof holds across at least one level of `TeamAgent` delegation, not only for a
  top-level execution;
- a missing or inconsistent binding on a delegated child fails closed, per §9.4;
- invoking a different child `agent_id` does not by itself mint or select a different
  workspace `agent_instance_id`.

## 8. Decision needed

Before implementation, decide:

1. ~~Does P1 live inside `RUNTIME-07`...~~ Closed 2026-09-02: neither. See §9.
2. Is share-copy provenance intentionally path-only, or do we need stored metadata?
3. Should SDK `FsEntry` expose provenance, or is provenance only a Files UI signal?
4. Does graph runtime template resolution intentionally include agent-space templates, or
   should it match `ToolContext`?

---

## 9. Workspace contract (2026-09-02, revised 2026-09-04) - the replacement for P1

Scope of this section: the not-yet-built part of `#2328`. The `can_access_files` gate is
already shipped (`#2476`) and is documented in `FILESYSTEM.md`, not here.

The model only ever sees `/workspace/...`. Knowledge Flow maps that onto the **existing**
physical prefix `teams/{team}/agents/{instance}/users/{uid}/...`, with no new segment - so
bytes already stored stay addressable and there is no migration. The namespace is derived
server-side from the execution scope; it is never assembled by the caller. That is the
whole point: today the SDK adapter builds team-rooted paths client-side, which is why the
raw `/fs` boundary cannot tell one actor from another.

### 9.1 Identity model

The governing rule:

> The bearer authenticates the caller; it does not identify the workspace owner.

Today those two collapse into one token, and that collapse *is* F1. Agent I/O currently
travels on the end user's Keycloak token, so Knowledge Flow sees "Alice" and cannot tell
whether Alice's browser or Alice's agent is writing.

For agent I/O the target is the runtime's own Keycloak M2M service identity - minted via
the existing `M2MTokenProvider` (client-credentials grant), never the end user's token.
The binding carried alongside that identity uses only names that already exist in this
codebase's `RuntimeContext` - no new identity concept is introduced:

```text
team_id             # required - RuntimeContext.team_id
agent_instance_id   # required - RuntimeContext.agent_instance_id
user_id             # required - RuntimeContext.user_id; mandatory in Workspace v1, see §9.4
session_id          # required for interactive v1 agent operations - binds authorization
                     # to the conversation, carries no partitioning meaning
exchange_id         # required - audit and artifact attribution only, carries no
                     # partitioning meaning
```

The physical storage partition is `team_id / agent_instance_id / user_id` - unchanged from
the existing prefix (§2). `session_id` and `exchange_id` never widen or narrow that
partition: two exchanges in the same session, or two sessions for the same `(team,
instance, user)`, land in the same subtree by design - that is what keeps a `TODO.md`
readable across turns (§9.4). They exist so a write can be authorized against a live
conversation and attributed to the turn that produced it, nothing more.

An ownerless scheduled execution - no `session_id`, no `user_id` - remains unsupported in
v1 (§9.4); it is not parked under a service-account uid as a workaround.

There is deliberately no `owner_user_id`, `run_id`, or `workspace_id` field. `owner_user_id`
and `run_id` already name different things in this codebase: `ManagedAgentRuntimeBinding.
owner_user_id` is the personal owner of an agent-instance *definition* (always `None`
today, since `owner_scope` is fixed to `"team"`), and `run_id` already names a Temporal
workflow or evaluation run. Reusing either name here would collide with an existing,
differently-scoped meaning instead of adding one.

Knowledge Flow must **verify** this binding against control-plane before honouring it -
see §9.5. Human I/O is unchanged: the user's Keycloak token, the existing ReBAC checks -
see §9.1a for the actor-permission boundary this makes explicit.

### 9.1a Actor permissions

| Actor | Operations | Scope |
| --- | --- | --- |
| Human (Keycloak user JWT) | `list`, `read`, `link` | that user's own workspace subtree only |
| Runtime M2M actor with a verified binding | `list`, `read`, `write`, `link` | the bound `(team_id, agent_instance_id, user_id)` subtree only |

A human JWT presented on the agent-write path is rejected as the wrong actor type, not
merely left unauthorized by ReBAC - `write` never reaches a ReBAC check at all for a
human-authenticated caller. Caller-supplied values never form a physical object-store
prefix in either case: prefix derivation happens only after authorization succeeds, and
only server-side. This is the same rule the rest of §9 already states for the namespace as
a whole; this subsection names it as a per-actor, independently testable requirement - see
§9.7.

### 9.2 The four operations, and what justifies each

| Operation | Consumer that justifies it |
| --- | --- |
| `list` (bounded, actor-scoped) | `TODO.md` proof (`ls` tool), `WorkspaceFsPort.ls`, Agents viewer |
| `read` | `TODO.md` proof, `resolve_template`, `resources.fetch_text`, agent assets, Agents viewer |
| `write` (create / replace) | `TODO.md` proof, `artifacts.publish_text`, ppt-filler, save-time asset store |
| `link` (durable reference) | artifact chips, PPT preview, `link_for`, Agents viewer |

This list was five operations until 2026-09-04. `delete` was dropped - see §9.3.

### 9.3 Deliberately excluded - this list is a stop signal

`edit` (the Deep adapter does read + replace + write), `glob`, `grep`, `mkdir`, `rename`,
`copy_to_shared`, `stat`, paginated `cat`, per-type stats.

`delete` joins them, for a reason worth writing down. Its only consumer was
`AgentConfigAssetsAdapter.delete`, and agent config assets do not belong in Workspace at
all: they live at `teams/{team}/agents/{instance}/config/{key}`, which is **instance-wide
and has no `users/{uid}` segment**. They never fitted the Workspace prefix declared above.
They keep their own path and their existing team-scoped ReBAC (read gated on membership,
write on `CAN_UPDATE_RESOURCES`), outside this contract. No capability calls
`WorkspaceFsPort.delete`, so removing it costs no retained use case.

The SDK helpers `ctx.read_user` and `ctx.read_team` are excluded on the same grounds. They
read *outside* the Workspace namespace - `teams/{team}/users/{uid}` and
`teams/{team}/shared` - which are exactly the two tabs `#2328` deletes, and no capability
calls either of them: only the adapter implements them. Keeping them would mean the
contract has a hole through which an agent reaches the user's private space, to serve no
retained use case.

None of these found a retained consumer. If one comes back "for parity" with `/fs`, that is
the stop signal `#2328` calls for: stop and re-evaluate the retained use cases rather than
widen the contract.

`edit`, `glob`, and `grep` stay excluded from *this remote list* for the same reason - no
Knowledge Flow route exists for them - but a Deep Agents adapter may still compose them
locally from `list`/`read`/`write` without adding a route; see §9.8.

### 9.4 Ownership and visibility in v1

**Every workspace is user-scoped.** The physical prefix carries a mandatory `users/{uid}`
segment, and a team-owned or agent-owned workspace would need a new one - that is a
migration, which this contract rules out. A scheduled run with no human owner is therefore
**not supported in v1**; it is not stored under a service-account uid as a workaround.

**Everything is private to the triple (team, instance, owner uid), and v1 has no
visibility transition.** There is no `shared/` inside Workspace and no `copy_to_shared`.
The consequence is worth stating plainly, because it diverges from the usual publish
model: the agent writes directly into the owner's own subtree, and `/fs/download` already
re-checks uid ownership there, so the owner can read those bytes from the moment they
land. There is no agent-private state to publish out of, and `link` is therefore a
*reference* to something the owner may already read - not a permission change.

Two consequences of that, named rather than glossed:

- **Agent-private scratch space has no home in v1.** Material the agent wants to keep to
  itself would need a sibling segment under the instance, outside `users/{uid}`. Not in
  this contract.
- **A child delegated inside an interactive managed execution MUST reuse the parent
  workspace binding - `team_id`, `agent_instance_id`, `user_id`, and `session_id`.** The
  child may run a different agent template/`agent_id`, but that must never create or
  select a different workspace `agent_instance_id` - a fresh instance id would move the
  child to a different subtree, and a parent's `TODO.md` would stop being readable by its
  children, breaking the Deep Agents proof `#2328` is built on. Per-child isolation, if it
  is ever wanted, is a sibling segment, not a different instance id.

  **This is a contract requirement, not an as-built invariant across every child
  invocation - a real gap exists today.** Some graph-runtime paths do recover
  `agent_instance_id` from portable baggage (`graph_runtime.py:1925,2193`,
  `portable.baggage.get("agent_instance_id")`), which is the mechanism that makes the
  requirement above hold *when the baggage was populated correctly upstream*. It is not:
  `LocalRegistryAgentInvoker.invoke` (`fred_runtime/app/agent_app.py`) constructs the
  child's `_AgentExecuteRequest` with `agent_instance_id=None` explicitly, and
  `_iterate_runtime_event_payloads` builds the child's `PortableContext.baggage` from that
  same top-level `request.agent_instance_id` field - not from the parent's own
  `RuntimeContext.agent_instance_id`, which is present elsewhere in the dumped context but
  never read for this purpose. A `None` value is filtered out of `baggage` entirely (the
  dict comprehension keeps only `isinstance(value, str) and value`), so a `TeamAgent` child
  invoked through this in-process path loses its parent's `agent_instance_id` outright, not
  merely inherits a stale one. Propagation is therefore an **implementation obligation**
  this contract states and the vertical slice must close (§9.10), not a property already
  guaranteed by today's code.

  **Workspace operations must fail closed if the binding cannot be preserved or
  validated.** A child that cannot establish a consistent `(team_id, agent_instance_id,
  user_id, session_id)` binding must be refused Workspace access, not silently fall back to
  no instance scope, a service-account uid, or a newly minted instance id.

### 9.5 How Knowledge Flow verifies the M2M binding

Resolved. Knowledge Flow validates the binding through a narrow, internal control-plane
endpoint, called before every M2M Workspace operation - not a signed token, and not a
Knowledge-Flow-side registry.

**Mechanism.** Knowledge Flow accepts a delegated Workspace binding only from the exact
configured runtime/agentic M2M client, and control-plane accepts this internal
binding-validation call only from the exact configured Knowledge Flow M2M client - at both
boundaries, `service_agent` alone is necessary but not sufficient, since that role is
shared by several FRED backend service identities and the evaluation worker
(`fred_core/security/structure.py:41-44`). Exact caller identity comes from a
signature-verified JWT client claim - `azp` / client ID - never from `preferred_username`
or an unverified header: `preferred_username` identifies a human-readable account name, not
which client authenticated, and an unverified header is not evidence at all. `KeycloakUser`
(`fred_core/security/structure.py:20-26`) does not carry `azp` today - only `uid`,
`username`, `roles`, `email` - so the implementing PR must either add the verified client
claim to the typed authentication principal or expose an equivalent verified-client
dependency; this RFC does not invent a Workspace-specific signed token to work around that
gap. An M2M token with no `azp`/client-ID claim, an empty claim, or a claim that does not
match the configured expected client fails closed at either boundary - even when the token
carries `service_agent`. The role is a coarse identity marker only; it is never a
substitute for the exact-client check above.

With exact caller identity established at both boundaries, Knowledge Flow calls the
control-plane endpoint passing `(team_id, agent_instance_id, user_id, session_id,
exchange_id)`. Control-plane validates, against data it already owns:

- the session identified by `session_id` exists;
- `session.user_id` is non-null and equals the presented `user_id`;
- `session.team_id` equals the presented `team_id`;
- the agent instance identified by `agent_instance_id` exists and belongs to `team_id`;
- the session's own `agent_instance_id`, when the session has one recorded, equals the
  presented `agent_instance_id`;
- the instance passes the same usability predicate `prepare_execution` already applies -
  `enabled` and not `suspended` (`product/service.py:3208-3226`, the `#1975` suspension
  guard - today inline in `prepare_execution`, not a standalone function). No two
  independent implementations of this rule: if it is not already extracted into one, the
  implementing PR must extract it so `prepare_execution` and this validator call the same
  predicate.

`exchange_id` is logged by Knowledge Flow on every validated call for audit and artifact
attribution - it is not one of the values control-plane independently validates; there is
no per-exchange record to check it against.

**Failure mode - fail closed.** An unknown session, a session with no `user_id`, a
`user_id`/`team_id`/`agent_instance_id` mismatch, an unknown, wrong-team, disabled, or
suspended instance, a caller that is not the exact configured client at either boundary, or
a control-plane call that cannot be completed all produce the same outcome: the Workspace
operation is refused. Never optimistic, never partially honoured.

**Inline, awaited, cache-free.** The first implementation performs this validation inline -
awaited before the Workspace operation it gates, on every M2M operation - and stays
cache-free in v1. A cache is not part of the initial contract; it may be proposed later, in
its own change, only after validation latency is measured against a real workload, and only
with explicit revocation/invalidation semantics stated at that time - if proposed, its
identity key must include at minimum `team_id`, `agent_instance_id`, `user_id`, and
`session_id`.

The implementation must use asynchronous HTTP I/O end to end and reuse one
application-scoped `httpx.AsyncClient` rather than constructing one per request - the
existing precedent for a pod-wide client of this shape is fred-runtime's own
`initialize_control_plane_client()` (`fred_runtime/app/context.py:148-153`, built once at
pod startup for control-plane runtime-binding calls), not the per-request `async with
httpx.AsyncClient(...)` pattern used elsewhere in control-plane's own outbound calls. The
call needs an explicit bounded timeout and must fail closed on timeout, connection error,
or an invalid response - same failure mode as above, no special case. This RFC does not
pick that number: the only existing precedent for a pod-to-control-plane binding-lookup
client is fred-runtime's own `_CONTROL_PLANE_CLIENT_TIMEOUT = httpx.Timeout(10.0)`
(`context.py:45`), set for a once-per-execution-preparation call - not evidence for a bound
on a call made on every Workspace operation, which needs a tighter budget. The implementing
PR chooses and justifies its own bound.

The implementation must emit `workspace.binding_validation_latency_ms` and use only the
existing bounded `status` dimension (`PROMETHEUS_ALLOWED_LABELS`,
`fred_core/kpi/prometheus_kpi_store.py:60-75`) as a Prometheus label - `trace_id` and
`correlation_id` stay in trace or audit data only; neither is in that allowlist today, and
this metric must not add them. Verify the metric is Prometheus-visible under
`PROMETHEUS_ALLOWED_LABELS` before shipping with writes enabled.

This does not restore or generalize `ExecutionGrant`, and needs no new signing or
cryptography beyond the exact-client-identity check above: every check is a live read
against control-plane state at call time, consistent with `RUNTIME-EXECUTION-CONTRACT.md`
§8.11's model of no control-plane-issued token.

**What this trust boundary is, stated plainly, so it is not read as more than it is.** The
configured runtime service account is the trusted delegation boundary - every Workspace
operation from every agent instance, in every session, across the whole runtime pod fleet,
authenticates as that one client identity. This design does not claim per-pod or
per-execution credential isolation: it verifies *what* the caller asserts (the
`team_id`/`agent_instance_id`/`user_id`/`session_id` tuple) against live control-plane
state, not *which specific execution* is asking. Compromise of that one runtime credential
would have service-wide impact - every workspace it can construct a plausible tuple for,
not just one execution's. Introducing execution-scoped grants (a distinct, narrower
credential minted per turn or per instance) would be a separate threat-model and
architecture change of its own, not something this tuple-validation design silently
provides. If that stronger isolation is ever required, it is future work, not implied by
anything in this section.

Agent writes must not ship gated behind "M2M PR later" as a deferred flag, and must not
ship before this validation path is complete end to end - see §9.10.

### 9.6 `link` is a durable, authenticated route - not a bearer capability

`link` returns a **durable, origin-relative Knowledge Flow reference**. It is not a bearer
capability: the href itself carries no embedded download credential, no token, nothing
that stands in for authorization on its own. Every access re-authenticates the requester
and re-evaluates their current ReBAC authorization, exactly like any other Knowledge Flow
route. Stated precisely: a leaked or persisted URL grants nothing by itself. An
authenticated requester receives only what
their own current ReBAC authorization permits; the URL adds no authority. A short-lived
signed URL may
still exist afterwards as an internal delivery optimisation (a just-in-time redirect to
object storage); it must never be the artifact identity, be persisted in agent or run
state, or be what `link` itself returns.

**This replaces the current 600-second HMAC `download_token.py` model** (`/fs/share`).
Naming both designs' properties:

| | `/fs/share` token (today) | `link` durable reference (this contract) |
| --- | --- | --- |
| Credential shape | HMAC token bound to `(path, uid, expiry)`, carried in the query string | none - the href alone grants nothing |
| Expiry | 600 seconds from mint | none of its own - validity tracks the requester's live authorization |
| What gates access | the token signature/expiry **and** live session ReBAC, both checked | live session ReBAC alone |
| Observed failure | a valid owner's own link 403s roughly ten minutes after being posted into chat, because the token expires before the owner's actual authorization does | none of that class - the link stays usable exactly as long as the holder remains authorized |
| What a leaked copy (chat export, screenshot, log) grants | nothing after 600 seconds, regardless of the holder's authorization at that later time | nothing by itself; an authenticated requester receives only what their own current ReBAC authorization permits - the URL adds no authority |

Steps 3 and 4 of that comparison are already shipped: `/fs/download` requires a Keycloak
session and re-runs ReBAC on every request, so the signed token has never been a
standalone credential - it is bound to path + uid and useless to anyone else. The problem
this contract fixes is expiry running the wrong way: `/fs/share`'s token makes the request
*stricter* than its absence would, entitling a link to fail for its own rightful owner.
`ppt_preview` already uses the durable tokenless href and has none of this.

T3 therefore removes `/fs/share` and `download_token.py` and moves `link_for` onto the
durable href, rather than porting the token machinery into Workspace.

### 9.7 Two actors, one namespace

The human actor is not new - `/fs` is already called from the browser with the user's token
(`AgentsWorkspace` -> `useLsQuery`). The agent actor, with its server-derived namespace and
its own M2M identity, is the newcomer. That both travel the same routes with the same token
today is precisely the cause of `#2113`. Isolation tests must therefore cover **both**: the
human read-only, the agent read-write, and the case that motivates §9.1 - a user token
presented directly to a Workspace agent route must not be accepted as an agent caller.

### 9.8 Deep Agents integration target

Adapter implementation work for a later Deep Agent PR - not this documentation change, see
§9.10. This section names the target and its operation mapping only.

The integration target is `deepagents.backends.protocol.BackendProtocol`, via
`CompositeBackend`, wired into `DeepAgentRuntime` (`fred_runtime/deep/deep_runtime.py`).
Constructor shape, verified against the installed `deepagents==0.6.12`:

```python
CompositeBackend(
    default=StateBackend(),
    routes={"/workspace/": FredWorkspaceBackend(...)},
)
```

`StateBackend` owns ephemeral scratch, unchanged from its existing LangGraph-thread-scoped
semantics - no Workspace involvement. `FredWorkspaceBackend` owns durable `/workspace`
only.

**The remote Workspace API stays exactly the four operations of §9.2** - `list`, `read`,
`write`, `link`. Nothing in this section adds a Knowledge Flow route.

`BackendProtocol` does not derive `edit`, `glob`, or `grep` from `list`/`read`/`write` - it
is an `ABC` with no enforced abstract methods; an unimplemented method raises
`NotImplementedError` at call time, and nothing synthesizes a scan or an edit
automatically (`StateBackend` implements its own `glob`/`grep` from scratch, over its own
in-memory state, for the same reason). `FredWorkspaceBackend` will implement these methods
itself, entirely client-side, by composing the four Workspace operations - no new remote
surface:

- `edit`: `read`, verify the expected match, `write` the replacement;
- `glob`: bounded recursive `list` traversal against the pattern;
- `grep`: bounded `list` + `read` traversal, with an explicit file-count limit and a
  content-size limit per file, so a single tool call cannot force an unbounded scan of the
  owner's subtree.

`link` remains a separate Fred-authored tool, not a `BackendProtocol` method - the protocol
has no equivalent operation for it (it is not one of
`ls/read/grep/glob/write/edit/upload_files/download_files`).

`execute` stays disabled - no conforming `SandboxBackendProtocol` backend exists for
Workspace, and none is proposed here. No exposed filesystem tool may terminate in
`NotImplementedError`: a tool the model can call must actually be served by
`FredWorkspaceBackend`'s own implementation above, or it must not be exposed at all.
`execute` is the one case that is not exposed, for exactly that reason.

### 9.9 Convergence and migration

The Workspace API is frozen at four operations - `list`, `read`, `write`, `link` (§9.2).
`#2498` and `#2328` currently still say five; both need a wording correction to match,
outside this RFC.

Every `/fs` route this contract does not replace stays in temporary coexistence with
Workspace until a named follow-up removes it - not indefinitely, and not as a second
permanent implementation:

| Route/component | Removal owner | Removal condition | External-consumer check |
| --- | --- | --- | --- |
| `/fs/share`, `download_token.py`, `link_for` (old form) | T3 follow-up | Workspace `link` ships; `ppt_filler` and every `LinkPart` producer re-pointed to it | Required - a public HTTP route; this repository's own search cannot rule out an out-of-repo caller |
| `/fs/list`, `/fs/upload`, `/fs/delete`, `/fs/copy-to-shared`, `/fs/mkdir`, `/fs/rename`, `/fs/stats` | T3 follow-up + a dedicated frontend change | Mon espace/Espace d'equipe UI tabs removed; `ppt_filler`'s write path re-pointed to Workspace `write` | Required for the write-side routes; the UI-removal half is fully verifiable in this repository |
| `/fs/stat`, `/fs/cat`, `/fs/page`, `/fs/edit`, `/fs/glob`, `/fs/grep` | T3 follow-up | No remaining UI or capability caller in this repository | Required, explicitly - these route names match `deepagents`' own native tool names, so an out-of-repo MCP/agent client is a real possibility a repository search cannot rule out |
| `ctx.read_user`/`ctx.read_team` SDK helpers | Same change as the Mon espace/Espace d'equipe deletion | Their only targets are deleted | Not required - call sites are confined to this repository |

No route above is claimed safe to delete on the strength of a repository search alone;
each row's "External-consumer check" column says explicitly whether one is still owed.

`writable_document` stays out of T3. It has its own router and its own table, and no
reference to `WorkspaceFsPort`, `FredWorkspaceFs`, or `/fs` anywhere in its package -
nothing in the current code makes it part of this migration.

**What Workspace guarantees, and what it does not.** Workspace guarantees authorized,
durable bytes: a write that succeeds is really there, under a namespace no caller can
spoof, readable only by whoever the binding authorizes. It does not guarantee that an
agent's own prose matches what it actually wrote - that a model's claim to have produced a
file corresponds to a real `write` call at all. That is a separate, later invariant,
enforced elsewhere: chat file UI is produced only from a verified, typed, server-side
artifact publication (an actual tool result), never inferred from message text. Nothing in
this contract changes that today, and nothing here proposes solving it with a
natural-language classifier - it is out of scope for Workspace and named here only so it
is not mistaken for solved.

### 9.10 Implementation sequencing

The first code PR is one functional vertical slice, not a sequence of
independently-mergeable fragments:

- the internal control-plane binding-validation endpoint (§9.5);
- Knowledge Flow's `list`/`read`/`write`/`link` WorkspaceService;
- the runtime's M2M client wiring (§9.1, §9.5);
- `FredWorkspaceFs` migrated off the human bearer token and off caller-constructed
  physical prefixes;
- server-derived namespace end to end;
- `LocalRegistryAgentInvoker` fixed to preserve the parent's workspace binding
  (`team_id`/`agent_instance_id`/`user_id`/`session_id`) onto a delegated child's
  execution request, instead of the current `agent_instance_id=None` (§9.4) - this is
  part of the vertical slice, not a follow-up, because a delegated `TeamAgent` child
  cannot pass the `TODO.md` proof without it;
- generated-contract regeneration for every public API this touches (below);
- isolation and actor-permission tests (§9.1a, §9.7, §7);
- validation-latency instrumentation (§9.5).

**Generated contracts.** Required, unconditionally: `cd apps/frontend && make
update-knowledge-flow-api` for the new WorkspaceService routes, and `cd apps/frontend &&
make update-control-plane-api` for the internal binding-validation endpoint (§9.5) - it
stays in control-plane's OpenAPI surface. Its M2M authorization (exact-client identity,
above) is the security boundary; hiding a route from OpenAPI is not a security mechanism
and is not a reason to skip regeneration. The generated frontend client may end up
carrying a binding for this endpoint that no UI code calls - that is preferable to a
hand-written duplicate transport DTO or a new shared contract invented solely to avoid
regenerating. No hand-written DTO duplicates a generated one on either side of either
call - the same rule this codebase already enforces for every other backend/frontend
boundary.

Agent writes must not ship disabled, waiting on a separate later M2M PR - and must not
ship before every item above exists together. Both directions matter: shipping the
WorkspaceService with writes flagged off invites the flag to become permanent load-bearing
state; shipping writes before validation exists recreates the human-JWT-as-agent-credential
gap this contract closes.

Out of this first PR, named explicitly so scope does not drift into it: the Deep Agents
`CompositeBackend` integration (§9.8), chat drawer changes, general artifact-truth
enforcement (§9.9), `writable_document` migration, and unrelated dead-code cleanup. Each is
either a later slice (§9.8) or explicitly out of scope for Workspace altogether (§9.9).

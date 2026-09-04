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
- `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`: the M2M workspace scope of §9.1 is
  runtime execution context - a dated entry is required once §9.5 is decided.
- `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`: required only if §9.5 lands on
  candidate 1, where prepare-execution mints the scoped token.
- `fred-sdk` contracts: `WorkspaceFsPort` loses `delete` (§9.3) and `link_for` returns a
  durable reference (§9.6); update the docstrings and optionally `FsEntry`.
- `knowledge-flow-backend` OpenAPI: the Workspace routes are new surface, and `/fs/share`
  is removed - regenerate the client in the same change.

## 7. Test plan

- Runtime adapter tests: keep existing path isolation tests; add graph
  `resolve_template` parity tests.
- SDK tests: stale doc fixes do not need tests, but any helper behaviour change does.
- Knowledge Flow tests: both actors per §9.7 - human read-only, agent read-write, and a
  user token refused as an agent caller; reject a mismatched `agent_instance_id`;
  preserve human `/fs` behaviour.
- Frontend tests: reserved-character filenames in download/share/copy paths.
- Large file tests: streaming or size-cap tests depending on FILES-05 decision.
- Share-copy tests: concurrent collision test if atomicity is implemented.

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

For agent I/O the target is a short-lived M2M token authenticating **the runtime**, with
the workspace scope carried alongside it:

```text
team_id             # required
agent_instance_id   # required
owner_user_id       # optional; delegated ownership, never impersonation
run_id              # required when a run/job exists
```

`owner_user_id = alice` means "this runtime is acting on Alice's behalf", not "this
caller is Alice". Knowledge Flow must **verify** that scope against the managed instance
or job before honouring it: IDs asserted by a shared service account are not
authorization by themselves. How that verification works is the one question this RFC
leaves open - see §9.5.

Human I/O is unchanged: the user's Keycloak token, the existing ReBAC checks.

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
- **Child agents inherit the parent's `agent_instance_id`, not just `owner_user_id`.**
  This is as-built, not a proposal: the graph runtime reads `agent_instance_id` from the
  portable baggage (`graph_runtime.py`), so a child lands in the *same* subtree as its
  parent. That is precisely what keeps a parent's `TODO.md` readable by its children -
  minting a fresh instance id per child would move it to a different subtree and break
  the Deep Agents proof `#2328` is built on. Per-child isolation, if it is ever wanted,
  is a sibling segment, not a different instance id.

### 9.5 Open question - how Knowledge Flow verifies the M2M binding

This is the only design question this RFC still leaves open. The requirement is settled:
Knowledge Flow must verify that the caller is entitled to the `(team_id,
agent_instance_id, owner_user_id)` it presents, and must never accept it as asserted. The
mechanism is not.

Two candidates, neither chosen:

1. **Per-execution token minted by control-plane**, carrying the binding as signed claims.
   Knowledge Flow validates the signature and reads the claims; no callback, no registry
   lookup on the write path. The cost is honest: this re-creates a grant-shaped artifact
   very close to the one RUNTIME-07 rev. 2 deliberately dropped, so choosing it means
   reopening that decision rather than quietly working around it.
2. **Shared runtime service account plus a Knowledge-Flow-side lookup** against the agent
   instance registry, checking that `agent_instance_id` belongs to `team_id` and, when a
   `run_id` is present, that the run is live and owned by `owner_user_id`. No new signing
   scheme, but it puts a lookup on every workspace write and requires a registry Knowledge
   Flow can read - which it does not have today.

Agent writes must not be enabled on the Workspace routes before this is decided.

### 9.6 `link` is a durable reference, not a signed URL

`link` returns a **durable, origin-relative Knowledge Flow reference**. Authorization is
re-checked at access time against the caller's current identity, so a stale or leaked
reference grants nothing on its own. A short-lived signed URL may exist afterwards as an
internal delivery optimisation (a just-in-time redirect to object storage); it must never
be the artifact identity, be persisted in agent or run state, or be what `link` returns.

Steps 3 and 4 of that model are already shipped: `/fs/download` requires a Keycloak
session and re-runs ReBAC on every request, so the signed token has never been a
standalone credential - it is bound to path + uid and is useless to anyone else.

The problem is expiry, and it runs the opposite way to the usual signed-URL worry.
`/fs/share` appends a token with a 600-second TTL, and `link_for` - what agents put in
artifact chips - uses it. That href is persisted in the chat history, so ten minutes later
the chip returns **403 to its own owner**, on a file they are still entitled to read: the
presence of the token makes the request stricter than its absence. `ppt_preview` already
uses the durable tokenless href and has none of this.

T3 therefore removes `/fs/share` and `download_token.py` and moves `link_for` onto the
durable href, rather than porting the token machinery into Workspace.

### 9.7 Two actors, one namespace

The human actor is not new - `/fs` is already called from the browser with the user's token
(`AgentsWorkspace` -> `useLsQuery`). The agent actor, with its server-derived namespace and
its own M2M identity, is the newcomer. That both travel the same routes with the same token
today is precisely the cause of `#2113`. Isolation tests must therefore cover **both**: the
human read-only, the agent read-write, and the case that motivates §9.1 - a user token
presented directly to a Workspace agent route must not be accepted as an agent caller.

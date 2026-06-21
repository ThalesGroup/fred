# RFC: Unified Virtual Filesystem — one layout over every backend

**Status:** draft — awaiting developer confirmation
**Author:** Dimitri Tombroff (drafted with Claude Code)
**Date:** 2026-06-20 · rev. 2026-06-21 — adds §7.2–§7.6: the full path-addressed SDK surface, the
download-link primitive, generic-ReAct/MCP parity, and the two **canonical user↔agent file
scenarios** that define this Swift version. The scope-based publish/fetch SDK is confirmed
**removed** (§8 status).
**ID:** AGENT-FILESYSTEM-UNIFIED-LAYOUT
**Tracked item:** `FILES-04`
**Completes:** `AGENT-FILESYSTEM-RFC.md` (`FILES-01`) — concretises its "MCP-filesystem-first" decision
**Supersedes:** the interim *template-exchange*, *team-partitioning*, and *unified-layout* addendums (consolidated here)
**Contract impact:** **breaking, by intent.** No backward compatibility. Duplicate file abstractions are deleted, not migrated. Existing physical backends are unchanged.

---

## 1. Decision

There is **one** way to address any file-like thing in the platform: a path in a single
**virtual filesystem**.

```
/etc/…                         platform configuration (technical admin)
/teams/{team}/…                everything else — config, resources, agents, user spaces
```

The virtual filesystem is a **view**, not a new datastore. Every physical backend stays
exactly where and how it is today — corpus blobs keep their uuid-keyed S3 layout, config
stays in Postgres and YAML, workspace blobs stay in object storage. The filesystem is the
*projection* that makes all of them look like one coherent, team-partitioned tree.

Three consequences, all intended:

1. **One mental model, one API surface.** Users, admins, agents, and graph nodes read and
   write by path. The duplicate "artifact vs resource vs MCP path vs scope-enum" story from
   `FILES-01` §2 collapses into addressing-by-path. We **delete** the redundant
   abstractions rather than wrap them.
2. **The team is the confidentiality perimeter, geographically.** `team_id` is the root of
   every non-platform path. Cross-team access is impossible by *construction* and, as
   today, still checked by ReBAC at the single enforcement point. The personal team is just
   `teams/personal-{uid}/` — no special case anywhere.
3. **The view is the migration tool.** Kea→Swift imports map onto this namespace without
   reshaping physical storage (§11). "Drop a template, get a deck" is just *write path →
   read path → write path* (§5).

This RFC is explicitly a **simplification with breaking changes**, which `FILES-01` already
authorised ("breaking SDK/runtime simplification allowed; no legacy generated-content
migration"). The target is *less code*, not more.

---

## 2. Core principle — the filesystem is a view over unchanged backends

The virtual path namespace is a **router**. Each top-level area maps to the backend that
already owns that data. Nothing physical moves; nothing is re-keyed.

| Virtual path | Backed by (unchanged) | Mode | Today's code |
| ------------ | --------------------- | ---- | ------------ |
| `/etc/...` | platform config — YAML + Postgres | read (admin-write via console) | `configuration_*.yaml`, control-plane stores |
| `/teams/{team}/etc/...` | per-team config — Postgres | read (admin-write via console) | `agent_instance`, `prompt`, `TeamMetadataStore`, … |
| `/teams/{team}/resources/...` | **corpus content store — S3, uuid-keyed** | read-only view | `BaseContentStore` / `FileSystemContentStore` / Minio; `/corpus` area |
| `/teams/{team}/shared/...` | workspace object storage | read/write | `WorkspaceFilesystem` (team root) |
| `/teams/{team}/users/{uid}/...` | workspace object storage | read/write | `WorkspaceFilesystem` (user root) |
| `/teams/{team}/agents/{agent_id}/users/{uid}/...` | workspace object storage | read/write | `WorkspaceFilesystem` (agent-user root) |

The point of the table: **the corpus keeps its uuid-named S3 buckets/keys** and is merely
*exposed* under `/teams/{team}/resources/`, exactly as `/corpus` already synthesises a
read-only view today. Configuration keeps its transactional Postgres home and is *exposed*
(in admin views, §10) under `etc/`. The unification is in the **addressing and the UX**, not
in the bytes.

> Design rule: a backend is added to the view by writing a router branch, never by copying
> data into a second store. If a path would require duplicating authoritative state, it does
> not belong in the writable tree — it is a read view of its real owner.

---

## 3. The layout

```
/etc/                                   ← platform configuration (technical admin)
   models/                              ← catalogue: models that EXIST on the platform
   quotas/                              ← global quota policy

/teams/
   personal-{uid}/                      ← a user's solo team — identical layout to any team
      etc/                              ← config of my personal space
      resources/                        ← my personal corpus (S3 view)
      shared/                           ← degenerate (solo) == my space
      users/{uid}/                      ← my files
      agents/{agent_id}/users/{uid}/    ← an agent's space, for me

   fredlab/                             ← a real team — sealed box
      etc/                              ← team config (business admin)
         models/                        ← SELECTION: which catalogue models fredlab uses
      resources/                        ← fredlab corpus (S3 view, uuid-keyed underneath)
      shared/                           ← fredlab shared team space
      users/{uid}/                      ← personal-in-fredlab (partitioned; EDF notes ≠ BNP)
      agents/
         rico/users/{uid}/              ← the 'rico' instance in fredlab, my space
         slide-builder/users/{uid}/

   edf/                                 ← another team — fully sealed from fredlab
      etc/ resources/ shared/ users/{uid}/ agents/rico/users/{uid}/ …
```

Two model rules, both matching code that already exists:

1. **An agent is one sealed instance per team.** `rico@fredlab` and `rico@edf` are distinct
   subtrees sharing nothing — managed agent instances are already team-scoped
   (`agent_instance` keys on `team_id`). No cross-team agent state exists.
2. **The personal team is a team like any other.** `teams/personal-{uid}/` follows the same
   layout — consistent with the *implemented* `CTRLP-10` (`personal_team_id(uid)`). No
   `if personal` branch anywhere.

---

## 4. Partition law and acting context

- **`team_id` is the root of every non-platform path and comes only from the verified
  session context** — the team selected in the UI / bound in the runtime context. It is
  **never** agent-supplied and never overridable.
- A request that carries an explicit team that disagrees with the session team is a **hard
  error**, never a redirection.
- **Structural *and* enforced.** The path root prevents cross-team key *construction*; the
  existing `ScopedAreaFilesystem` ReBAC check (`TeamPermission.CAN_READ` /
  `CAN_UPDATE_RESOURCES`) still runs before any byte is served. Neither layer is removed —
  the path is not a substitute for the membership check.
- Path traversal stays blocked (`normalize_virtual_path` rejects `..`).

This is the single most important invariant in the system. It is enforced in exactly **one**
place (§6).

---

## 5. Folder convention and template resolution

Inside any writable team area, three reserved folders — same words everywhere:

```
<area>/
├── templates/    # inputs an agent READS to generate (pptx, docx, xlsx, …)
├── uploads/      # raw user-dropped inputs not yet classified
└── outputs/      # deliverables an agent WROTE → returned to chat as download links
```

Folders are a convention, not a schema. `resolve_template(name)` resolves **first match
wins**, most specific to most general — all team-rooted, no cross-team escape:

1. an explicit path passed this turn (an attached file) — always wins;
2. `/teams/{team}/users/{uid}/templates/{name}` — my personal-in-team override;
3. `/teams/{team}/shared/templates/{name}` — the team default;
4. a **code-bundled default shipped with the agent** — the platform fallback (replaces the
   deleted `agent-config` scope; lives with the agent code/pod, not in storage).

---

## 6. Permissions — derived from the path, enforced once

Permission is a pure function of *(path, session identity)*. There is no separate scope
parameter to get wrong.

| Area | Read | Write / Delete |
| ---- | ---- | -------------- |
| `/etc/...` | platform admin | platform admin (via console) |
| `/teams/{team}/etc/...` | team members (`CAN_READ`) | team business admin (via console) |
| `/teams/{team}/resources/...` | `CAN_READ` | ingestion pipeline only (read-only in the view) |
| `/teams/{team}/shared/...` | `CAN_READ` | `CAN_UPDATE_RESOURCES` |
| `/teams/{team}/users/{uid}/...` | the owning user | the owning user |
| `/teams/{team}/agents/{id}/users/{uid}/...` | owning user + that agent | owning user + that agent |

Hard rules:

- **One enforcement point.** All access — human HTTP and agent MCP — funnels through the
  `ScopedAreaFilesystem` / `WorkspaceFilesystem` router, which is the only place ReBAC runs.
  No bypass, no second code path.
- **The acting identity is always (user, team) from the session.** An agent never escalates
  to a team or user it is not running for. `users/{uid}` is reachable only by that uid;
  cross-user-in-team access does not exist.
- Quota: team areas → team quota; user areas → user quota (`TeamMetadataStore.check_quota`,
  unchanged).
- **Corpus is read-only in the view.** The **ingestion pipeline is the sole writer** to
  `/teams/{team}/resources/`; agents and users never write there. Agent-generated files go
  to `outputs/` (a writable workspace area), never into the corpus view.

---

## 7. Agent & app file API — path-addressed, scopes deleted

The SDK exposes the filesystem by path. Scope enums and per-scope verbs are **removed**, not
deprecated.

```python
# read / write by path (team comes from session context, not an argument)
data  = await ctx.read("shared/templates/corporate-2026.pptx")
link  = await ctx.write("outputs/q3-review.pptx", deck_bytes)   # returns a LinkPart
files = await ctx.ls("shared/templates")
tpl   = await ctx.resolve_template("corporate-2026.pptx")        # §5 order
```

- `write(...)` returning a `LinkPart` preserves the existing chat download-link render path
  (`PublishedArtifact.to_link_part`) — that concept stays; only the scope dispatch is gone.

### 7.1 Path grammar — team-relative by default (decided)

Security rule, not a preference. The agent must be unable to *express* a team other than
its session team, so the team can only ever come from the verified session context (§4).

- **Agent paths are team-relative.** `"shared/templates/x.pptx"` resolves against
  `/teams/{session_team}/`. The agent never types a team id, so it cannot select one.
- **An absolute `/teams/{t}/...` path is accepted only if `t` equals the session team** — a
  redundant restatement, never an override. A non-session team is a **hard error**, never a
  redirect. This mirrors the `target_team_id`-must-match rule in §4.

  ```python
  ctx.read("shared/x")                  # ✅ relative → session team
  ctx.read("/teams/fredlab/shared/x")   # ✅ only when session team IS fredlab
  ctx.read("/teams/edf/shared/x")       # ❌ hard error in a fredlab session
  ```

- **`/etc/...` is the one teamless grammar:** platform config is addressed absolutely and
  gated by platform-admin permission (§6), outside the team-relative rule by design.

### 7.2 The full SDK surface (authored tools)

This is the **complete** file capability an authored (Python, `fred-sdk`) tool gets. The team
and the user are injected from the verified session context (§4); they are never parameters.
A **bare path is the user's private space**; a **`shared/`** prefix is the team space.

| Call | Returns | Meaning |
| ---- | ------- | ------- |
| `await ctx.read(path)` | `str` | one file as text |
| `await ctx.read_bytes(path)` | `bytes` | one file as raw bytes (binary-safe, e.g. `.pptx`) |
| `await ctx.write(path, content, *, content_type=None, title=None)` | `PublishedArtifact` | write a file; the result carries a download `href` |
| `await ctx.ls(path="")` | `list[FsEntry]` | list a directory (`path`, `size`, `is_dir`) |
| `await ctx.resolve_template(name)` | `bytes` | find a named input by §5 order (attached → my `templates/` → team `shared/templates/` → code default) |
| `ctx.link(artifact, *, text="")` | `ToolOutput` | render a written artifact as a chat download link |
| **`await ctx.link_for(path, *, text="")`** *(new, §7.3)* | `ToolOutput` | render an **existing** file as a chat download link — no copy |

Everything else from the old surface — `ArtifactScope`/`ResourceScope`, `publish_bytes`,
`read_resource`, per-scope verbs — is **gone** (§8). There is exactly one verb per intent.

### 7.3 Returning a deliverable — the user's space first, a *signed* link second (decided)

Two decisions, taken together, for a hardened-platform posture:

**(1) The deliverable channel is the user's own space, not a URL.** Every agent deliverable is
written under the user's `outputs/` (§5). That copy is **durable, ReBAC-gated, and retrievable
at any time from the Files UI**, which already downloads through the single enforcement point
(§6). This needs **no new primitive**: `await ctx.write("outputs/…", bytes)` is the entire
contract. If we built nothing else, Scenarios 1 and 2 (§7.5) still work — the user simply
fetches the result from their space. This directly answers "could we get away with nothing?":
**yes for retrieval** — the space *is* the deliverable.

**(2) V1 ships an in-chat download link, and it is a *signed, short-TTL* URL** — never an
unsigned session href. We **reuse the mechanism we already have**:
`ContentStore.get_presigned_url(key, expires=…)` (the same presigning that already mints
~1-minute URLs for markdown media). On a secure platform a bounded, signed URL is the
established posture; and because the file also lives in `outputs/`, an **expired link is never
a dead end** — the user re-downloads from Files.

So the `/fs/download/{path}` origin-relative href that uploads currently return
(`_download_href`) is **not** what backs a chat link. The link primitive mints a presigned URL:

- **SDK (V1):** `await ctx.link_for(path, *, text="") -> ToolOutput`
  and the link returned by `ctx.write(...)` both build `PublishedArtifact.href` via
  `get_presigned_url(workspace_key, expires=<short TTL>)`. Composable split available —
  `ctx.workspace_link(path) -> PublishedArtifact` + existing `ctx.link(...)` (§15-Q2a).
- **`WorkspaceFsPort`:** one op, `presigned_url(path, expires) -> str` (or `link_for(path) ->
  PublishedArtifact`). No bytes copied; the artifact in `outputs/` is the long-lived object,
  the URL is a short-lived pointer to it.
- **Dev / filesystem-backed stores** have no presigning: fall back to the session-authed
  `/fs/download` stream, exactly as `_replace_with_presigned` already skips presigning
  off-MinIO. Signed in prod, session-authed in dev — never an unsigned URL handed outside the
  session in prod.

Net: nothing heavy is added. The durable channel already exists (write → user's space); the
optional convenience link reuses existing presigning and is short-lived by construction.

### 7.4 Generic ReAct (V2) agents — the same primitives via MCP

Authored tools use `ctx`. A **generic ReAct agent** has no Python tool of its own; it uses the
**`mcp-fs`** toolset, where each `/fs` route is an MCP tool (operation_id = tool name):
`ls`, `read_file`, `read_file_page`, `write_file`, `upload_file`, `download_file`,
`stat_file_or_directory`, `glob`, `grep`, `mkdir`, `edit_file`, `delete_file`. Same router,
same single ReBAC enforcement point — agents and humans share one code path (§6).

Per §7.3 the baseline already holds: a generic agent writes the deliverable into the user's
`outputs/` with `write_file`/`upload_file`, and the user can retrieve it from the Files UI.
V1 also ships the parity tool that mirrors `ctx.link_for`: an `mcp-fs`
tool **`share_file`** (operation_id) that, given an existing path, returns
`{ download_url, file_name, size, mime }` where `download_url` is a **signed, short-TTL
presigned URL** (the same `get_presigned_url` mechanism), falling back to the session-authed
stream off-MinIO. `download_file` (raw bytes) stays for agent-to-agent byte access; it is not a
chat link. Naming/shape is §15-Q2.

> Design rule held: the two surfaces (authored `ctx`, generic `mcp-fs`) expose the **same**
> primitives over the **same** router. Neither gets a capability the other lacks, and neither
> bypasses §4/§6.

### 7.5 Canonical scenarios — the V1-defining user↔agent file loop

These two scenarios are the point of the whole RFC: a user and a generic agent cooperate over
the shared filesystem, with the team as the perimeter. Setup: **Alice**, working in team
**fredlab**, drops `report.xlsx` through the Files UI — into her personal space
(`uploads/report.xlsx` → `/teams/fredlab/users/alice/uploads/report.xlsx`) or the team space
(`shared/uploads/report.xlsx`). She opens a chat with a **generic ReAct V2 agent** in fredlab.

**Scenario 1 — “give it back to me as a downloadable link.”**
The file already exists; nothing is generated. The agent locates it and hands back its link.

- Authored tool:
  ```python
  return await ctx.link_for("uploads/report.xlsx", text="Here is your file.")
  ```
- Generic ReAct (MCP): `glob`/`ls` to find it → `share_file("uploads/report.xlsx")` →
  signed `download_url` → chat link.
- Guarantees: the path resolves under Alice's session (§7.1); the link is a **signed,
  short-TTL** URL (§7.3) and access is re-checked at the enforcement point (§6); **no copy**,
  key unchanged. A file in `users/alice/...` is reachable only in Alice's session — an agent
  run for Bob could not mint this link. And since the file is already in Alice's space, the
  link is pure convenience: she can also just open it from the Files UI (the "nothing extra"
  path of §7.3).

**Scenario 2 — “make me a copy and put it in my space.”**
Read source → (optionally transform) → write into the user's `outputs/` → return the link.
This is the *write path → read path → write path* of §1/§5.

- Authored tool:
  ```python
  data = await ctx.read_bytes("uploads/report.xlsx")
  # … optionally transform the bytes …
  artifact = await ctx.write("outputs/report-copy.xlsx", data)   # bare path → Alice's space
  return ctx.link(artifact, text="Copied into your space.")
  ```
- Generic ReAct (MCP): `read_file`/`download_file` → `write_file`/`upload_file`
  (returns `download_url`) into `outputs/`.
- Guarantees: the copy lands under `users/alice/outputs/` (bare path = private); writing to
  `shared/outputs/` instead would require `CAN_UPDATE_RESOURCES` (§6). The corpus view is never
  a write target.

**The broader story — templates & skills in, generated deck out.**
The same loop powers the headline use case. Alice or a fredlab admin drops reusable **inputs**
under the reserved `templates/` convention (§5) — PowerPoint/Word templates *and* skill /
instruction files the agent reads:

```
/teams/fredlab/shared/templates/brand.pptx        # team-wide deck template
/teams/fredlab/shared/templates/deck-style.md     # a "skill": how this team wants decks built
/teams/fredlab/users/alice/templates/brand.pptx   # Alice's personal override (wins, §5)
```

A slide-builder tool then composes these into a deliverable:

```python
template = await ctx.resolve_template("brand.pptx")        # §5: attached → mine → team → code default
skill    = await ctx.read("shared/templates/deck-style.md")
deck     = build_deck(template, skill, data)                # agent logic
artifact = await ctx.write("outputs/q3-review.pptx", deck)  # → Alice's space
return ctx.link(artifact, text="Your deck is ready.")
```

“Skills” and “templates” introduce **no new concept**: they are just files the agent *reads*
under the `templates/` convention, resolved most-specific-first (§5). A generic ReAct agent
does the same with `resolve`/`read_file` + `write_file`. The whole feature touches **only**
`/fs` (§14) — no deck-specific endpoint exists.

### 7.6 What an agent may assume — the reserved layout, restated for builders

For tool/agent authors, the contract reduces to four reserved folders inside their writable
area (§5), all team-relative (§7.1):

- `templates/` — inputs I **read** to generate (documents *and* skills/instructions).
- `uploads/` — raw user-dropped inputs, not yet classified.
- `outputs/` — deliverables I **write**, returned to chat as links.
- everything else — free-form working files.

Read with `read`/`read_bytes`/`resolve_template`; produce with `write` then `link`, or hand
back an existing file with `link_for`. That is the entire surface.

---

## 8. Code cleanup — no backward compatibility

This is a required part of the RFC, not a follow-up. The unified view makes the following
redundant; they are **deleted**. (Exact lines confirmed at implementation; this is the
target end-state.)

| Delete / collapse | Where | Replaced by |
| ----------------- | ----- | ----------- |
| `ArtifactScope`, `ResourceScope` enums; `target_user_id`/`target_team_id` scope params | `fred-sdk/contracts/context.py` | path addressing (§7) |
| `ArtifactPublishRequest` / `ResourceFetchRequest` scope dispatch | `fred-sdk/contracts/context.py` | `read(path)` / `write(path)` |
| `FredArtifactPublisher` + `FredResourceReader` per-scope branching | `fred-runtime/.../v2_runtime/adapters.py` | one path-routed client |
| `KfWorkspaceClient.upload_user_blob` / `upload_agent_config_blob` / `upload_agent_user_blob` | runtime client | one `upload_blob(path, bytes)` |
| `WorkspaceStorageService` per-scope helper sextets (`put_user_file`, `put_agent_config_file`, `put_agent_user_file`, …) | knowledge-flow | one `put/get/list/delete(path)` that parses the virtual path |
| `WorkspaceLayoutConfig` patterns (`user_pattern`, `agent_config_pattern`, `agent_user_pattern`) | knowledge-flow + `configuration_*.yaml` | the single `/teams/{team}/…` grammar (physical mapping internal) |
| `/storage/user/*`, `/storage/agent-config/*`, `/storage/agent-user/*` route families | knowledge-flow controllers | the existing path-addressed `/fs/*` surface |
| The **`agent-config` storage scope** entirely | all layers | code-bundled agent default (§5 step 4) |
| Legacy generated-artifact / resource-key code & any Kea-era file abstraction | wherever it survives | nothing — not migrated (`FILES-01`) |

Net direction: from four scope families + two ports + three route families **down to one
path-addressed router**. Fewer types, fewer endpoints, fewer branches.

> **Implementation status (2026-06-21).** Most of this table is already done (grep-confirmed):
> the scope-based SDK is removed — `ArtifactScope`/`ResourceScope`,
> `ArtifactPublishRequest`/`ResourceFetchRequest`, `publish_bytes`/`publish_text`/`read_resource`,
> and the `FredArtifactPublisher`/`FredResourceReader` ports are gone, replaced by the
> path-addressed `ctx` surface (§7.2) over `WorkspaceFsPort`; the `/storage/*` route families
> and `WorkspaceStorageService`/`WorkspaceLayoutConfig` are deleted; the unused `/user-assets`
> and `/agent-assets` knowledge-flow endpoints are removed. The builtin tool *name*
> `artifacts.publish_text` is retained but now resolves to `workspace_fs` `WORKSPACE_WRITE`
> (no scope dispatch). The **only net-new** work this revision asks for is the small
> download-link primitive of §7.3–§7.4 (`ctx.link_for` + the `mcp-fs` `share_file` twin).

---

## 9. Configuration is a *logical* view — it does not move

`/etc` and `/teams/{team}/etc` are an **ownership and addressing model**, not a relocation
of config into object storage. The bytes stay in Postgres/YAML.

- `/etc/models` — the **catalogue** (what exists), owned by the technical admin.
- `/teams/{team}/etc/models` — the **selection** (what this team uses, per agent), owned by
  the business admin.
- The catalogue→selection invariant ("a team cannot enable a model absent from the
  catalogue") is a **referential constraint** — it stays in the relational layer, where it
  can actually be enforced. Putting config in blob storage would *break* this invariant, so
  we explicitly do not.

The two `etc` levels share the word but carry different ownership and non-overlapping
content, mirroring the technical-vs-business admin split. They are exposed as views (§10),
never as writable blob folders.

---

## 10. UX — storage truth ≠ user-facing tree

The layout is backend truth. The "everything is a file" elegance must **not** leak into the
UI as raw path browsing.

- **Data spaces** (`users/`, `resources/`, `shared/`, `agents/.../users/`) → the unified,
  VSCode-style resource tree, scoped to the current team (the team selector sets the box).
  Users see *"Mon espace / Resources / Espace d'équipe / Agents"* — never `/teams/.../users/...`.
  Switching teams reloads the whole tree on the other box; no transverse space appears.
- **Config spaces** (`/etc`, `/teams/{team}/etc`) → the admin consoles already designed,
  not folders: `/etc` → *Console technique* (platform admin); `/teams/{team}/etc` →
  *Paramètres d'équipe* (business admin).

One backend namespace; purpose-built views over it. Per-folder permission states
(invisible / read-only / full) apply within the current team's box.

---

## 11. Kea → Swift migration enablement

Migration is a **control-plane application**, not a filesystem area (ties into the `MIGR`
track). A technical admin uploads a **Kea export zip**; the migration app **ingests,
transforms, and maps** it (notably agent mapping) into the target Swift instance, writing
the result through the normal stores and the unified view. Its job state lives in the
control plane (Postgres + a transient blob for the uploaded zip), **not** under `/etc` —
which is why `/etc/migration` is dropped from the layout.

The unified view is what makes that app cheap:

- Swift imports only **durable config** (agents, prompts, users, teams) per `FILES-01`;
  generated content is **not** migrated.
- Because the filesystem is a *view*, Kea-origin corpus and config are **exposed** under
  `/teams/{team}/...` without physically re-laying-out S3 or rewriting object keys — the
  app maps existing keys into the team subtree rather than copying data, wherever the
  physical layout is already team-bound.
- The single namespace means the Swift UI presents Kea-imported and Swift-native data
  identically, removing per-origin special-casing in the frontend.

---

## 12. Migration of existing Swift state (the real, smaller move)

Only the **legacy workspace blobs** actually move — the ones written under the old *flat*
`WorkspaceLayoutConfig` patterns (`users/{uid}/...`, `agents/{id}/users/{uid}/...`), which
have **no team in their key**. Everything else is a view or is already team-keyed.

- `users/{uid}/...` → `teams/{personal-{uid} | origin_team}/users/{uid}/...`
  (default **personal team**; a real team only with positive origin evidence — §15-Q1).
- `agents/{agent_id}/users/{uid}/...` → `teams/{origin_team}/agents/{agent_id}/users/{uid}/...`
- `agents/{agent_id}/config/...` → **dropped** (no backward compat; defaults move to code).
- Corpus (S3 uuid layout) and Postgres config → **unchanged**; only the view is new.

> "Legacy / no team in their key" is the precise meaning of what earlier drafts loosely
> called *unrooted*: blobs from the pre-team-partition layout that are not yet under any
> `/teams/{team}/` prefix. Going forward **no such blob can exist** — every write is
> team-relative (§7.1), so a file is always under a team (personal or real). This is a
> one-time, migration-only concern.

One-shot, gated behind a flag, run offline — same playbook as `CTRLP-10` §4.4. Dev/test:
purge legacy blobs with no reliable owner; prod: correlate ownership before the cutover.

---

## 13. Alternatives considered

1. **Physically move config/corpus into one blob store.** Rejected — loses transactions,
   joins, and the catalogue→selection constraint (§9); huge migration for no gain. The view
   gives the unification for free.
2. **Keep scope enums and add `team`.** Rejected — keeps the duplicate abstraction the whole
   exercise removes; more code, not less.
3. **Per-resource `user_id` filtering instead of team-rooting.** Rejected — already rejected
   and replaced by team isolation in `CTRLP-10` (fragile whack-a-mole).
4. **Backward-compatible dual surface.** Rejected — the developer's explicit goal is a
   cleaned codebase with the least code; `FILES-01` authorises the break.

---

## 14. Acceptance criteria

- Every stored/addressable key is either `/etc/...` or rooted at `/teams/{team_id}/...`; no
  other root exists in the view.
- Corpus bytes remain in their existing uuid-keyed S3 layout; only the `/teams/{team}/resources`
  view is added (no corpus re-keying).
- Configuration remains in Postgres/YAML; no config is written to object storage.
- The same agent in two teams shares no files (cross-team isolation test).
- The personal team uses byte-identical layout logic to a real team (no special-case path).
- A team's `etc/models` cannot enable a model absent from `/etc/models` (catalogue→selection).
- `team_id` is sourced only from session context; a disagreeing explicit team is a hard error
  (audited — no code path builds a key from an agent-supplied team).
- Scope enums, the two publisher/reader ports, and the per-scope `/storage/*` routes are
  **removed** from the codebase (grep-clean).
- "Drop a `.pptx` → get a deck" touches zero feature-specific endpoints — only `/fs`.
- **Scenario 1** (return an existing file as a link, §7.5) is a single call —
  `ctx.link_for` / `mcp-fs` `share_file` — with **no copy** and no key change.
- **Scenario 2** (copy into the user's space, §7.5) uses only `read` + `write` + `link`, and
  the copy lands under the user's `outputs/` (bare path), never in the corpus view.
- A **generic ReAct V2** agent performs both scenarios using only `mcp-fs` tools — no
  authored tool and no feature-specific endpoint.
- Every agent deliverable is retrievable from the user's own space via the Files UI **without
  any chat link** (the space is the deliverable channel, §7.3(1)).
- When an in-chat link is returned, it is a **signed, short-TTL** URL (presigned in prod;
  session-authed `/fs/download` fallback in dev) — never an unsigned URL handed outside the
  session — and access is re-checked at the enforcement point (§4/§6). `ctx.link_for` /
  `mcp-fs` `share_file` **refuse** (hard error) a path outside the session team or a
  non-readable user space.
- `make code-quality` and `make test` green in `fred-sdk`, `fred-runtime`, `knowledge-flow-backend`.

---

## 15. Open questions

1. **Legacy per-user blob ownership at migration** — the old flat `users/{uid}/` layout
   carries **no team dimension** (§12). The security-conservative default is to map each
   such blob to the user's **personal team** (`teams/personal-{uid}/users/{uid}/`), the
   smallest-blast-radius home, and to route it into a real team **only with positive
   evidence** of that origin. Confirm this default (and that Swift dev/test simply purges
   per `CTRLP-10` §4.4).
2. **Shape of the download-link primitive (§7.3–§7.4).** Three decisions to confirm:
   (a) **SDK ergonomics** — single `ctx.link_for(path, *, text="") -> ToolOutput` (one call,
   matches `ctx.error`/`ctx.text`), or the composable pair
   `ctx.workspace_link(path) -> PublishedArtifact` + existing `ctx.link(...)` (mirrors
   `write`+`link`, lets a tool tweak `title`/`mime` before rendering)? Recommendation:
   ship `link_for` as the ergonomic default, implemented on top of `workspace_link`.
   (b) **MCP tool name** — `share_file` vs `get_download_link` vs `link_file` for the
   `mcp-fs` twin. It must read clearly to an LLM choosing tools ("return this file to the
   user as a link"). Recommendation: `share_file`.
   (c) **Link durability — decided: signed.** In-chat links are **signed, short-TTL presigned
   URLs** (`ContentStore.get_presigned_url`, the markdown-media mechanism), with a
   session-authed `/fs/download` fallback off-MinIO (dev). No unsigned URL is handed outside
   the session in prod. (§7.3.)
   (d) **Do we ship in-chat links in V1? Decided: yes (signed).** V1 ships the signed,
   short-TTL in-chat link (§7.3(2)) alongside the durable copy in the user's space — the
   space remains the always-available fallback if a link expires. (Resolved 2026-06-21.)
3. **Should `ls`/`stat` carry the download href?** Today `FsEntry` is `{path, size, is_dir}`
   and a link costs a second `stat`. Optionally include the `/fs/download/{path}` href on file
   entries so the Files UI and agents avoid the extra call. Minor; defer unless the round-trip
   shows up. Keep `FsEntry` lean by default.
*(Resolved 2026-06-20: the ingestion pipeline is the **sole writer** to the corpus view —
now a hard rule in §6. Migration is a control-plane app, not an `/etc` view — `/etc/migration`
**dropped** from the layout, see §11.)*

# RFC: Unified Virtual Filesystem — one layout over every backend

**Status:** draft — awaiting developer confirmation
**Author:** Dimitri Tombroff (drafted with Claude Code)
**Date:** 2026-06-20
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
- `make code-quality` and `make test` green in `fred-sdk`, `fred-runtime`, `knowledge-flow-backend`.

---

## 15. Open questions

1. **Legacy per-user blob ownership at migration** — the old flat `users/{uid}/` layout
   carries **no team dimension** (§12). The security-conservative default is to map each
   such blob to the user's **personal team** (`teams/personal-{uid}/users/{uid}/`), the
   smallest-blast-radius home, and to route it into a real team **only with positive
   evidence** of that origin. Confirm this default (and that Swift dev/test simply purges
   per `CTRLP-10` §4.4).
*(Resolved 2026-06-20: the ingestion pipeline is the **sole writer** to the corpus view —
now a hard rule in §6. Migration is a control-plane app, not an `/etc` view — `/etc/migration`
**dropped** from the layout, see §11.)*

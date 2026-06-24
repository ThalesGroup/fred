# RFC: Agent Filesystem — user-first unified file exchange

**Status:** target contract — implementation gates defined; consolidated FILES-01 + FILES-04, awaiting developer confirmation to implement. §§1–11 are the target product contract, **not** approved current behaviour; §12 is the source of truth for what is shipped versus gated.
**Author:** Dimitri Tombroff
**Date:** 2026-05-30
**Last updated:** 2026-06-24
**ID:** AGENT-FILESYSTEM
**Tracked items:** `FILES-01`, `FILES-04`
**Backlog:** `docs/swift/backlog/CHAT-UI-BACKLOG.md §4.5`, `§4.6`
**Supersedes:** `AGENT-FILESYSTEM-UNIFIED-LAYOUT-RFC.md`
**Contract impact:** breaking SDK/runtime simplification allowed; `FsEntry` gains provenance
(product-contract change); no legacy generated-content migration

> **Reading note.** §§1–11 describe the **target** product contract. §12 states
> precisely what is **already shipped** versus **still to build**, and the order in
> which the four-root UI becomes truthful. Do not read §§1–11 as current behaviour;
> read §12 for status.

---

## At a glance — build the UI from this

Four read-as-simple spaces inside the current team:

| Space | What it holds | Who writes |
| --- | --- | --- |
| **Resources** | team corpus (read-only view) | ingestion only |
| **Mon espace** | my private files in this team | me |
| **Espace d'equipe** | files shared with the team | humans with rights |
| **Agents** | one folder per agent, my files from it | the agent, for me |

Four rules, nothing more:

1. Team templates live in **Espace d'equipe**; my overrides in **Mon espace**; agent outputs
   in **Agents**.
2. Agents write only to their own **Agents** folder — never to Resources or Espace d'equipe.
3. Sharing to the team is an explicit **human** action (`Copy to Espace d'equipe`), never
   automatic.
4. Each file shows where it came from: **deposé** (human), **généré** (agent), **partagé**
   (shared copy).

The UI shows the agent's **name**, never an id. Everything below is the enforcement and
status detail to implement these four rules safely; §12 says what is shippable now.

---

## 1. Decision

Fred has one filesystem product contract: a simple team-scoped file workspace where humans
and agents exchange files through Knowledge Flow.

The user-facing layout comes first. If Alice is working in team `fredlab`, the UI shows
exactly four data roots:

```text
fredlab
├── Resources
├── Mon espace
├── Espace d'equipe
└── Agents
```

The raw backend paths, buckets, object keys, and storage providers are implementation
details. Users, agents, and SDK authors should not need to understand them.

The four visible spaces mean:

| UI space | Meaning | Default write owner |
| --- | --- | --- |
| `Resources` | Team knowledge/corpus content exposed as a read-only view | ingestion pipeline only |
| `Mon espace` | Alice's private files inside the current team | Alice |
| `Espace d'equipe` | Files deliberately shared with the team | authorized humans |
| `Agents` | Files produced or used by agents for Alice, grouped by agent | the running agent for Alice |

`Resources` is read-only **from the filesystem contract**. A human "adding a resource" in
the UI is an *ingestion request* (corpus pipeline), not an `/fs` write. The ingestion
pipeline is the only writer; the four-root tree exposes the result as a read-only view. No
`/fs`, MCP, or SDK call ever writes to `Resources`.

The core rule is:

```text
Team templates go in Espace d'equipe.
Personal overrides go in Mon espace.
Agent outputs go in Agents.
Sharing is an explicit human copy.
```

This is the canonical filesystem RFC. The previous split between `FILES-01` and
`FILES-04` is folded here so there is one source of truth.

---

## 2. User Stories

### 2.1 Alice uploads a team template

Alice is a fredlab business admin. She wants every slide-generating agent in fredlab to use
the official deck template.

She opens:

```text
Espace d'equipe / templates
```

and uploads:

```text
fredlab-corporate-template.pptx
```

Expected behavior:

- the template is readable by authorized fredlab users and agents;
- it is not copied into every user's private space;
- it is not hidden inside one specific agent;
- updating the shared template updates the team default for future agent runs.

### 2.2 Alice asks the slide agent to generate a deck

Alice chats with her agent **Slide Builder** (its logical name; the underlying agent
folder is keyed by the agent's instance id — see §3.1).

> Generate a Q3 review deck using the fredlab corporate template.

The agent resolves the template in the standard order:

1. files explicitly attached to this run;
2. `Mon espace / templates / fredlab-corporate-template.pptx`;
3. `Espace d'equipe / templates / fredlab-corporate-template.pptx`;
4. the agent's bundled fallback template, if any.

Resolution rules (so `resolve_template` is deterministic, not best-effort):

- **First match wins, by source precedence**, in the exact order above. A user override
  (step 2) always beats a team template (step 3) of the same name, even if the team copy is
  newer.
- **Within one source**, name match is exact (case-sensitive, including extension). MIME is
  not part of matching: a `.pptx` name that resolves to non-PPTX bytes is returned as-is and
  is the agent's problem to validate — the resolver does not silently fall through to the
  next source on a MIME mismatch.
- **Attached duplicates** (two run attachments with the same name) are a hard error from
  `resolve_template`; the caller must disambiguate. Attachments never silently shadow each
  other.
- **Attached files are ephemeral run inputs**, not durable workspace files. They live only
  for the run unless the agent explicitly writes them into its own space. Resolving an
  attachment does not create a file under `Agents / {agent} / ...`.
- **Bundled fallback** (step 4) is addressed by logical name only; it is never written into
  any team/user space and never appears in the Files UI.

The generated file lands in:

```text
Agents / Slide Builder / outputs / q3-review.pptx
```

Alice receives a chat download chip, but the durable place is the Files UI under the
agent's space. The chat link is convenience; the file location is the product truth.

### 2.3 Alice overrides the team template for herself

Alice uploads:

```text
Mon espace / templates / fredlab-corporate-template.pptx
```

For Alice's runs, Slide Builder now uses Alice's private override before the shared team
default. Bob, in the same team, still gets the team default unless he creates his own
override.

### 2.4 Alice shares an agent output with the team

The agent produced:

```text
Agents / Slide Builder / outputs / q3-review.pptx
```

By default this file is private to Alice. The agent does not silently publish it to the
team.

If Alice decides the deck should become a team asset, she clicks a human UI action such as
`Copy to Espace d'equipe`. The server copies the file to a shared location:

```text
Espace d'equipe / files / q3-review.pptx
```

The original remains in:

```text
Agents / Slide Builder / outputs / q3-review.pptx
```

The copy preserves origin provenance and adds `shared_by` / `shared_at`.

### 2.5 Bob uses the same agent

Bob also works in fredlab. He can read:

```text
Espace d'equipe / templates / fredlab-corporate-template.pptx
```

and his generated files land in **his own** partition of the agent space:

```text
Agents / Slide Builder / outputs / q3-review.pptx
```

Alice and Bob each see only their own files under `Agents / Slide Builder`. The filenames
may be identical — isolation is by the `users/{uid}` segment in the path (§3), never by
filename. They share only what a human explicitly copies into `Espace d'equipe`.

---

## 3. Canonical Virtual Layout

The visible UI roots map to a single team-rooted virtual namespace:

```text
/teams/{team}/resources/...                              # UI: Resources
/teams/{team}/users/{uid}/...                            # UI: Mon espace
/teams/{team}/shared/...                                 # UI: Espace d'equipe
/teams/{team}/agents/{agent_instance_id}/users/{uid}/... # UI: Agents / {agent display name}
```

### 3.1 Agent identity in paths

The agents subtree is keyed by `agent_instance_id`, the immutable per-team identity
of an enrolled agent. This is deliberate; the other two identifiers are wrong as path
keys:

| Identifier | Why not the path key |
| --- | --- |
| template id (`source_runtime_id:source_agent_id`) | Shared by every instance enrolled from the same template, so two agents in one team would collide in one folder. |
| `display_name` (the logical name) | Mutable (rename would orphan or force-move files) and not guaranteed unique per team. |
| **`agent_instance_id`** | **Immutable, unique per team, and already the identifier the runtime selects on (`ExecutionGrant` / `RuntimeExecuteRequest`).** |

The UI never shows `agent_instance_id` or the template id. It shows the agent's
**logical name** (`display_name`), resolved by joining the `agents/` listing to the
team's agent registry. The path stays stable across renames; the label follows the
current name. An `agents/{agent_instance_id}/...` folder whose instance has been
deleted is shown with a fallback label such as "Removed agent".

`agent_instance_id` keys the *same* per-user space across every run of that instance:
there is no per-run segment. The agent's outputs for a user accumulate durably in one
place; "that run" in the permission table (§6) refers to write *capability* during an
active run, not to a per-run folder.

> **Label disambiguation (not a filesystem requirement).** Folders are keyed by the
> immutable `agent_instance_id`, so duplicate *labels* never cause path collisions or
> isolation bugs — isolation is path-level, always correct. The only open question is
> cosmetic: two agent folders rendering the identical label. `display_name` is currently
> mutable and not unique per team (no DB constraint). Two acceptable resolutions:
>
> 1. **Render-time disambiguation (default, lighter).** Allow duplicate names and render a
>    deterministic suffix — `Slide Builder`, `Slide Builder · Finance`, or a short id tail —
>    so labels are always distinct in the UI without constraining what users may name agents.
> 2. **Per-team unique-name constraint (product-policy hardening).** Add a DB constraint +
>    creation-time validation. This is a deliberate *product* choice (tidy names), **not** a
>    filesystem necessity, and it constrains the user; adopt it only if the product owner
>    wants enforced-unique agent names.
>
> The acceptance criteria require only that **no two agent folders render the same label**;
> either approach satisfies it. See §12 G6.

### 3.2 Configuration views (not in the Files tree)

Platform and team configuration remain separate admin views:

```text
/etc/...                         # platform technical configuration view
/teams/{team}/etc/...            # team business configuration view
```

These config paths are logical views over Postgres/YAML. They are not ordinary user file
folders and must not appear in the main Files tree.

### 3.3 Physical storage is unchanged

- `resources/` is a read-only view over corpus/document storage;
- `users/`, `shared/`, and `agents/.../users/...` are workspace object-storage areas;
- config stays in relational/config stores;
- object-store buckets, keys, GCS/S3 details, and signed URL mechanics are not the product
  contract.

---

## 4. UI Design Rules

The Files UI must optimize for comprehension, not raw path accuracy.

- Show the current team as the enclosing workspace.
- Show exactly four data roots: `Resources`, `Mon espace`, `Espace d'equipe`, `Agents`.
- Do not show `/teams/{team}`, `/users/{uid}`, object keys, bucket names, or provider names.
- Under `Agents`, show one folder per agent instance that has files for the current user.
  Each folder is keyed internally by `agent_instance_id` but labelled with the agent's
  logical name (`display_name`); never render the uuid or the template id.
- Inside each agent folder, use the same simple conventions: `templates/`, `uploads/`,
  `outputs/`, `work/`.
- Mark provenance in the list/detail view:
  - `depose` / uploaded by a human;
  - `genere` / generated by an agent;
  - `partage` / copied into team space by a human.
- Render permission states clearly: invisible, read-only, or editable.
- Team switching reloads the whole tree into the other team box. There is no cross-team
  blended view.

Recommended empty-state language:

| Space | Empty-state intent |
| --- | --- |
| `Resources` | "No indexed team resources are available yet." |
| `Mon espace` | "Drop private files for this team here." |
| `Espace d'equipe` | "Share templates and reusable team files here." |
| `Agents` | "Agent outputs will appear here after a run." |

The `Agents` empty state is honest: until an agent run produces files for the user, the
root is legitimately empty. It must not be lit up as "ready" while agent outputs are still
landing elsewhere (see §12 sequencing).

---

## 5. Principal And Enforcement Model

This section is the backbone that makes the rest of the contract enforceable. Every
filesystem decision is authorized at **one** point against a **verified principal**, not
against a path plus an ambient user token alone.

### 5.1 The principal descriptor

Every `/fs` and MCP filesystem call carries a server-verified principal:

| Field | Meaning |
| --- | --- |
| `actor_type` | `human` (interactive HTTP) or `agent` (a runtime agent run) |
| `team_id` | the active team (the confidentiality perimeter) |
| `uid` | the acting user |
| `agent_instance_id` | present only when `actor_type = agent`: the calling agent instance |

Rules:

- The principal is derived from the verified session (human) or the execution grant
  (agent). It is **never** taken from caller-supplied request fields.
- For agent runs, `agent_instance_id` is bound into the workspace access token / call
  context by the runtime and validated at the Knowledge Flow boundary. The agent process
  cannot mint or alter it.
- A single enforcement point authorizes **both** human HTTP and agent MCP operations on
  `(virtual_path, actor_type, team_id, uid, agent_instance_id)`. Same gate, but the gate
  knows *who* is acting, not just *as which user*.

### 5.2 Why the principal is required

Three otherwise-invisible holes close only when the gate knows the acting principal:

1. **Agent outputs land in the right root.** A bare agent write must resolve into
   `/teams/{team}/agents/{agent_instance_id}/users/{uid}/...`, which is impossible unless
   `agent_instance_id` reaches the resolver.
2. **No cross-agent leakage.** For any agents-subtree path, the gate must verify the
   `{agent_instance_id}` segment equals the calling run's `agent_instance_id`. Without the
   principal, a run could address a sibling agent's folder for the same user.
3. **Agents cannot escalate into team space.** Writes to `shared/...` must be denied when
   `actor_type = agent`, independent of whatever team permissions the underlying user
   holds. A pure `(path, user-permission)` gate cannot express this.

### 5.3 How Knowledge Flow trusts the principal (the trust contract)

The principal fields above are only safe if Knowledge Flow can prove they were minted by
the runtime, not forged by the agent process or a client. This is the explicit contract;
implementers MUST NOT pass principal fields as plain, caller-settable headers.

**Two distinct callers, two distinct trust paths:**

| Caller | `actor_type` | How the principal is established | May the caller set actor fields? |
| --- | --- | --- | --- |
| Interactive human (`/fs` over HTTP) | `human` | Derived from the verified user session at the KF boundary; `agent_instance_id` is **absent**. | **No.** A human request carrying `actor_type`, `agent_instance_id`, or a foreign `uid` is rejected, not honoured. Human `/fs` calls can never assert agent identity. |
| Agent run (MCP filesystem tools) | `agent` | Carried by a signed **runtime→KF workspace token**, minted per run by the runtime from the `ExecutionGrant`. | **No.** The agent process receives the token opaque; it cannot read, mint, or alter the claims. |

**Runtime→KF workspace token.** The runtime already mints a workspace access token per run
(`_workspace_access_token`); v1 **extends that existing token** with the principal claims
below rather than building a parallel mechanism. Minted by the runtime (the trusted issuer)
at run start and attached to every MCP filesystem call for that run:

- **Type:** short-lived signed token (JWT or equivalent), signed with a runtime key that KF
  verifies against a published/shared verification key. KF rejects any unsigned or
  wrong-issuer token.
- **`iss`:** the runtime service identity.
- **`aud`:** the Knowledge Flow filesystem service. KF rejects tokens with any other
  audience (no token replay across services).
- **`exp` / `iat`:** short expiry bounded by run lifetime (minutes, not hours). Expired
  tokens are rejected; the runtime re-mints as needed.
- **Claims (the principal):** `actor_type=agent`, `team_id`, `uid`, `agent_instance_id`,
  and the run/grant id for audit. These claims **are** the principal; KF reads the principal
  from verified claims only, never from request body or non-signed headers.
- **Binding:** `agent_instance_id` and `team_id` in the token MUST match the `ExecutionGrant`
  the runtime selected on. The runtime injects them from the grant, not from agent input.

**Rejection behavior (fail closed):** a filesystem call is rejected with an authorization
error — never silently downgraded, redirected, or treated as a human call — when the token
is missing, unsigned, wrong `iss`/`aud`, expired, or when its claims disagree with the
addressed path (e.g. a token for instance A used on instance B's subtree). Rejections are
audit-logged with the run/grant id.

> **Invariant.** Principal fields are server-verified claims, never caller-supplied inputs.
> Any code path that reads `actor_type`, `team_id`, `uid`, or `agent_instance_id` from a
> request body or an unauthenticated header is a security bug, not a convenience.

---

## 6. Permissions And Isolation

Permission is derived from `(virtual path, principal)` (§5). There is no separate scope
parameter that an agent or client can supply.

| Virtual area | Read | Write/delete |
| --- | --- | --- |
| `/teams/{team}/resources/...` | team members with resource access | ingestion pipeline only |
| `/teams/{team}/users/{uid}/...` | owning user | owning user |
| `/teams/{team}/shared/...` | team members with `CAN_READ` | **humans** with `CAN_UPDATE_RESOURCES` (never agents) |
| `/teams/{team}/agents/{agent_instance_id}/users/{uid}/...` | owning user; the named agent during its own run | owning user; the named agent during its own run |
| `/etc/...` | platform admin | platform admin through admin console |
| `/teams/{team}/etc/...` | team members/admin views as appropriate | business admin through admin console |

Hard rules:

- `team_id`, `uid`, and `agent_instance_id` come from the verified principal (§5.1).
- An agent cannot supply or override `team_id`, `uid`, or `agent_instance_id`.
- An agent cannot write to `Resources`.
- **An agent run cannot write to `shared/` (Espace d'equipe), regardless of the acting
  user's `CAN_UPDATE_RESOURCES`.** Sharing is a human-only action (§8).
- A human must explicitly copy into `Espace d'equipe`, and that requires
  `CAN_UPDATE_RESOURCES`.
- **Cross-team, cross-user, and cross-agent paths are hard errors, never redirects.** For
  an agents-subtree path, the gate rejects any `{agent_instance_id}` segment that is not
  the calling run's own instance (cross-agent), any `{uid}` that is not the principal's
  (cross-user), and any team that is not the session team (cross-team).
- Path traversal is rejected before authorization.
- All human HTTP and agent MCP operations use the same router/enforcement point, evaluated
  against the full principal.

The owning user controls their agent space: a human may read, download, delete, rename,
copy, and share-copy any file under `Agents / {their agent}`, even after the run ends.

**In-place editing of agent outputs is out of scope for the first target.** A human does not
overwrite agent-generated bytes in place; to change a deck, the user downloads it and uploads
the edited copy into `Mon espace` as their own file (normal human provenance), or keeps the
original. This is a deliberate, simplifying limit: creation provenance stays immutable and
trivially truthful, and v1 needs no edit-tracking or concurrency machinery. In-place editing
can be added later if a real need appears (§15.7).

---

## 7. Agent SDK Contract

The SDK must be simple enough that an agent author rarely writes a raw platform path.

### 7.1 Authored agents

The common path is:

```python
template = await ctx.fs.resolve_template("fredlab-corporate-template.pptx")
deck = build_deck(template)
artifact = await ctx.fs.write("outputs/q3-review.pptx", deck, content_type=PPTX_MIME)
return ctx.fs.link(artifact, text="Your deck is ready.")
```

Rules:

- Bare SDK paths are relative to the running agent's private space for the current user:
  `/teams/{team}/agents/{agent_instance_id}/users/{uid}/...`. The SDK never asks the
  author for `agent_instance_id`; the runtime injects it from the execution grant.
- Bare reads and writes are symmetric. If the agent writes `outputs/x.pptx`, it can later
  read `outputs/x.pptx`.
- The SDK must not require, encourage, or document raw `/teams/...` paths for normal agent
  authoring.
- The SDK must reject absolute paths that name another team, another user, or another agent
  instance.
- The SDK exposes small helpers for common intent rather than many scope enums.

Authored-agent surface. **Two separate axes** — do not conflate them:

- **API** — does the method exist by name in `ctx.fs` today? (`present` / `target`)
- **Target routing** — does it route/resolve per the target contract above? (`done` =
  matches target; `G#` = method exists but its target semantics are gated by that gap).

The trap this table closes: `read`/`write`/`ls`/`link` exist as methods, but their *target
routing* is not yet implemented — today a bare `write` still lands in `Mon espace`, not the
agents subtree (§12 G1). "API present" is not "behaves as specified".

| Call | Purpose | API | Target routing |
| --- | --- | --- | --- |
| `ctx.fs.read(path)` / `ctx.fs.read_bytes(path)` | read from the agent's space by default | present | **G1** — symmetric with bare write; correct only once writes route to the agents subtree |
| `ctx.fs.write(path, content, *, content_type=None, title=None)` | write into the agent's space by default | present | **G1** — today routes to `Mon espace`; target is the agents subtree |
| `ctx.fs.ls(path="")` | list the agent's space by default | present | **G1** — lists the agents subtree only once writes land there |
| `ctx.fs.link(path_or_artifact, *, text="")` | return an existing agent-space file as a chat link | present (currently `link_for`; rename/alias to `link`) | done (name alias is G7) |
| `ctx.fs.resolve_template(name)` | attached → user → team → bundled default | present | **G7** — today user → team only; attached + bundled steps to build |
| `ctx.fs.read_user(path)` | explicit read from `Mon espace` (§7.3) | present | done (v1 reads the run user's whole Mon espace; selection-scoping deferred) |
| `ctx.fs.read_team(path)` | explicit read from `Espace d'equipe` (§7.3) | present | done |
| `ctx.fs.read_resource(path)` | explicit read from `Resources` | present | deferred — raises in v1; read corpus via the search/RAG tools |

The explicit `read_user`, `read_team`, and `read_resource` helpers are read-oriented. Team
sharing stays a human server-side copy, not an SDK write capability. Bare writes never reach
`Mon espace`, `Espace d'equipe`, or `Resources`.

Removed from the target authoring model:

- `ArtifactScope`, `ResourceScope` (already absent in code — keep them out);
- `target_user_id`, `target_team_id` in author-facing file calls;
- per-scope publish/fetch calls;
- agent-authored writes into team shared space.

### 7.2 Generic ReAct and MCP agents

Generic agents are enrolled instances too, so they carry an `agent_instance_id` and use the
identical layout and principal model. They receive the same capabilities through MCP
filesystem tools, whose names express user intent and hide backend layout.

Required tool categories:

- list/stat/read/write/delete inside the agent's own space;
- read user-selected or user-space files when the run grants them;
- read team shared files;
- read resources;
- return a chat link for an existing file in the agent's space.

The MCP surface must not give a generic agent a capability that the SDK would deny — in
particular, no MCP tool may write to `shared/` or another agent's subtree.

### 7.3 Cross-space read access is scoped by default (not ambient)

An agent's *default* reach is its own private space only. The `read_user` / `read_team` /
`read_resource` helpers are the **only** way out of that space, and each is deliberately
narrow so an agent cannot quietly crawl a user's or team's files.

**`read_user` — the run user's own Mon espace.** `read_user` reads files from the acting
user's private space (same user the agent runs for; KF enforces own-uid ownership, so there
is no cross-user reach). **v1 reads the whole Mon espace** for that user — consistent with
the first-party/trusted-agent posture (cf. G1a/G1b). **Selection-scoping is deferred
hardening** (the §target below): once it lands, a `read_user` call is bounded to a per-run
grant — specific files or a folder the user picked — and a read outside the selection is a
hard authorization error. Until then, treat broad Mon espace reads by an agent as a trust
assumption, not an enforced boundary.

**`read_team` inherits the user's team-read access — no extra grant.** `Espace d'equipe` is
already readable by any team member with `CAN_READ`, so an agent acting for that member reads
it under the same right. The one deliberate v1 limit is precise and enforceable: agents get
**scoped** reads — a named file or a single-level listing — not a recursive enumeration of the
whole shared tree, so a run cannot silently crawl and exfiltrate everything. (This is a
read-shape cap, not a permission gate, and it is the only cap; there is no ambiguous
"broad reads need a grant" rule.) `resolve_template`'s team step (§2.2) is exactly such a
scoped read.

**`read_resource`** reads the read-only corpus view and is governed by the team's existing
resource-access permission; it grants no write and no cross-team reach.

In all three, the principal (§5) still bounds everything to the session `team_id` and `uid`;
these helpers widen *which space* may be read, never *which team or user*.

---

## 8. Provenance Metadata

Every filesystem object returned by `/fs`, MCP, and SDK metadata must carry server-stamped
provenance. Clients may display it, but may not forge it. Adding these fields to `FsEntry`
is a product-contract change recorded in `CONTROL-PLANE-PRODUCT-CONTRACT.md`.

**Immutable creation fields** (stamped once, never rewritten — not even by an overwrite):

| Field | Meaning |
| --- | --- |
| `origin` | `uploaded`, `agent_generated`, `shared_copy`, `ingested`, or `system` |
| `created_by` | user id responsible for the creation action, when applicable |
| `producer` | `human`, `agent:{agent_instance_id}`, `ingestion`, or `system` |
| `created_at` | server timestamp |

**Standard file metadata** (ordinary, not provenance — present for any file):

| Field | Meaning |
| --- | --- |
| `content_type` | server-resolved MIME of the bytes |
| `modified_at` | server timestamp of the last write |
| `modified_by` | user id of the last writer |

`version` / `etag` (optimistic-concurrency change tokens) are intentionally **out of the
first target**: there is no in-place overwrite of agent files in v1 (§6), so the conflict
case they solve does not yet arise. Add them only when in-place editing lands.

**Share-copy fields:**

| Field | Meaning | Visibility |
| --- | --- | --- |
| `source_path` | original virtual path of the copied file | **Server/audit metadata.** Not part of the reader-facing `FsEntry` for arbitrary team members — it can leak the originator's private folder structure or agent usage. Exposed only to the sharer, team admins, and audit. |
| `shared_by` | user id that initiated the copy | reader-visible |
| `shared_at` | server timestamp of the copy | reader-visible |

Rules:

- Provenance fields are stamped by the server. Client-supplied provenance is ignored or
  rejected.
- Copying to `Espace d'equipe` preserves the original creation provenance and adds the
  share-copy fields.
- **Creation provenance is immutable.** `origin`, `created_by`, and `producer` are stamped
  once and never rewritten. Re-uploading a file in `Mon espace` is a normal user write; agent
  outputs are not overwritten in place in v1 (§6).
- **`source_path` is audit metadata, not a reader-facing field.** A shared copy must not
  expose the originator's private path to every team reader; surface it only to the sharer,
  admins, and audit logs.
- `FsEntry` exposes enough provenance for the UI to show `depose`, `genere`, and `partage`
  badges without an extra lookup for common list views.

---

## 9. Share-By-Copy

Sharing is an explicit human action:

```text
private file -> server-side copy -> Espace d'equipe
```

The original remains untouched. This is a new server operation (see §12); `/fs/share`
today returns a signed download link, which is a different thing and not a copy.

Rules:

- The caller's `actor_type` must be `human`. Agents cannot invoke this operation.
- The user must have read access to the source file.
- The user must have `CAN_UPDATE_RESOURCES` on the target team space.
- The target path is under `/teams/{team}/shared/...` (default subfolder `files/`).
- Name collisions are resolved by deterministic suffixing, for example
  `q3-review (2).pptx`.
- **No clobber on collision.** Suffix resolution and destination creation are one atomic step
  (reserve-then-write), so two concurrent copies of the same name cannot both resolve to
  `q3-review (2).pptx` and overwrite each other; the loser takes the next free suffix. This is
  the one concurrency guarantee v1 needs.
- Cross-request idempotency keys are **not** required in v1: a double-click producing a
  `q3-review (2).pptx` duplicate is acceptable and user-correctable. Add an idempotency key
  only if duplicate copies become a real complaint.
- Provenance is preserved and `shared_by` / `shared_at` are stamped.
- Sharing to `Resources` is impossible; corpus ingestion remains the only writer there.

---

## 10. URL And Download Policy

Do not mix object-storage URL policy into the filesystem layout contract.

For this RFC:

- chat links and Files UI downloads are Fred/Knowledge Flow links;
- current `/fs` and LinkPart URL patterns remain the product-facing contract;
- authorization is checked through Knowledge Flow before bytes are served;
- raw GCS/S3/MinIO URLs are not exposed by this RFC;
- large-file transfer and any future presigned/direct-download optimization belong to
  `FILES-05`, not to the core layout.

Backend-internal signed URLs, such as DuckDB reading Parquet from object storage
(`FILES-06`), are outside this RFC's user-facing filesystem contract.

---

## 11. Compatibility And Migration

The target is breaking for SDK/runtime abstractions, but should be compatible with the
existing Knowledge Flow `/fs` route family wherever possible.

Compatibility rules:

- Keep the `/fs` endpoint family as the stable product API.
- Map UI root aliases to canonical virtual paths server-side.
- Do not expose storage-provider paths in SDK, frontend, runtime, or chat messages.
- Existing physical backends stay where they are.
- Legacy generated content and old conversations are not migrated for a fresh Swift install.
- Legacy workspace blobs without team in their key are a one-time migration concern:
  default to the user's personal team unless a real origin team is known.

The older routes and types that existed only to model artifact/resource scopes should be
deleted or hidden once the path-addressed filesystem is complete.

---

## 12. Implementation Status And Sequencing

The product contract above is the target. This section is the source of truth for what is
**already true** versus **to build**, and the order in which the four-root UI becomes
honest. Verified against code on 2026-06-24.

### 12.1 Already shipped (safe to rely on)

| Capability | Evidence |
| --- | --- |
| Team-rooted path grammar `/teams/{team}/{resources,users,shared,agents}` with a single Knowledge Flow enforcement point | `scoped_area_filesystem.py`, `virtual_fs_contract.py` |
| No scope enums; scope is implicit in the path | `ArtifactScope`/`ResourceScope` absent |
| `team_id`/`uid` derived from session; cross-team and cross-user rejected | runtime `_resolve` + KF `_ensure_own_uid` |
| Agents subtree path grammar exists and validates structure | `scoped_area_filesystem.py` agents branch |
| `agent_instance_id` is immutable, per-team, and carried by the execution grant | `agent_instance_models.py`, `execution.py` |
| Three working roots: `Resources`, `Mon espace`, `Espace d'equipe` | `TeamResourcesPage.tsx` |
| `ctx.fs` with `read`/`read_bytes`/`write`/`ls`/`link_for`/`resolve_template` | `fred-sdk` authoring API |

### 12.2 To build (gates the four-root UI and the isolation guarantees)

| Gap | Required work | Unblocks |
| --- | --- | --- |
| **G1 — Bare agent writes land in `Mon espace`, not `Agents`** | Propagate `agent_instance_id` (and `actor_type`) into the runtime fs adapter and route bare writes to the agents subtree (§5) | The `Agents` root being non-empty and `Mon espace` staying clean |
| **G2 — Cross-agent same-user access** | Gate must verify the path's `{agent_instance_id}` equals the calling run's (§6) | Cross-agent isolation AC |
| **G3 — Agents can write `shared/`** | Deny `shared/` writes when `actor_type = agent` at the enforcement point (§5.2, §6) | "agents cannot share" AC |
| **G4 — No provenance on `FsEntry`** | Stamp + return creation provenance (`origin`/`created_by`/`producer`/`created_at`), standard `content_type`/`modified_at`/`modified_by`, and share fields with `source_path` audit-only (§8) | Provenance badges (§4, §8) |
| **G5 — No share-by-copy operation** | New human-only server copy with **atomic** no-clobber collision suffixing and sharing metadata (§9) | `Copy to Espace d'equipe` UI action |
| **G6 — Agent folder labels can collide** | Either render-time disambiguation (default) **or** a per-team unique-name constraint + creation validation (product-policy choice) (§3.1) | Unambiguous `Agents` folder labels |
| **G7 — SDK surface gaps** | `resolve_template` attached/bundled steps; add `read_user`/`read_team`/`read_resource`; alias `link` | §7 surface parity |

G1–G3 share one root cause — the filesystem boundary does not know the acting principal —
and are delivered together by the **principal-propagation** work (§5). That is the single
gating item.

### 12.3 Rollout order

1. **Principal propagation (G1–G3).** Thread `(actor_type, agent_instance_id)` to the
   Knowledge Flow enforcement point; route bare agent writes to the agents subtree; enforce
   cross-agent and agent-no-shared rules. This is prerequisite for a truthful `Agents` root.
2. **Provenance (G4)** and **label disambiguation (G6).** Enable badges and clean labels.
3. **Share-by-copy (G5).** Enable the `Copy to Espace d'equipe` action.
4. **SDK parity (G7)** can land in parallel; it does not gate the UI.

**UI gating — two distinct milestones, do not collapse them:**

- **`Agents` root may appear (minimum) once G1–G3 ship** — i.e. routing (G1),
  cross-agent isolation (G2), and the agent-no-shared-write rule (G3). Below this bar the
  root is not just empty, it is *unsafe* (outputs in the wrong place, possible cross-agent
  visibility, agents able to write team space). **Never light `Agents` while G1 is
  unshipped.**
- **The four-root UI may be called "final"/product-complete only once G1–G5 ship** —
  routing + isolation + no-agent-shared-writes + provenance (G4) + share-by-copy (G5). A
  tree that routes correctly but shows no provenance badges and offers no
  `Copy to Espace d'equipe` is structurally correct but not product-complete; it must not be
  presented as the final Files experience. G6 (label disambiguation) is required for legible
  labels but is satisfiable by render-time suffixing, so it does not block the milestone the
  way G1–G5 do.

Until G1–G3 ship, the honest interim UI is the three working roots (`Resources`,
`Mon espace`, `Espace d'equipe`), which are fully backed today.

---

## 13. Implementation Instructions

### 13.1 Knowledge Flow

- Keep the one virtual router for all `/fs` and MCP filesystem operations.
- Verify the principal from trusted sources only (§5.3): the user session for `human`
  calls, and a signed runtime→KF workspace token (verify `iss`/`aud`/`exp`/signature) for
  `agent` calls. Read `actor_type`/`team_id`/`uid`/`agent_instance_id` from verified
  claims; reject — fail closed, audit-log — any request that supplies them as plain
  body/header fields, and any agent token whose claims disagree with the addressed path.
- Authorize on `(path, actor_type, team_id, uid, agent_instance_id)`.
- For agents-subtree paths, reject any `{agent_instance_id}` segment that is not the
  calling run's instance (G2).
- Reject `shared/` writes when `actor_type = agent` (G3).
- Stamp and return provenance through the workspace filesystem boundary (G4): immutable
  creation fields plus standard `content_type`/`modified_at`/`modified_by` metadata; expose
  `source_path` to audit/admin only, not in the reader-facing `FsEntry`.
- Return `FsEntry` with stable path, name, type, size, timestamps, content type, and
  provenance summary.
- Keep `Resources` read-only from the filesystem view; treat human "add resource" as an
  ingestion request, never an `/fs` write.
- Add the server-side share-copy operation for humans only (G5), with atomic no-clobber
  destination reservation (§9).

### 13.2 fred-sdk

- Present a small `ctx.fs` API centered on read/write/link/resolve-template.
- Make bare paths resolve to the current agent's space.
- Provide explicit read helpers for user/team/resource reads (G7); make `read_user`
  selection-scoped and `read_team` scope-limited by default (§7.3), not ambient crawls.
- Implement the full `resolve_template` order (attached → user → team → bundled).
- Do not expose raw team/user/agent path construction as the normal authoring model.
- Keep old scope enums and per-scope artifact/resource abstractions out of the public path.

### 13.3 fred-runtime

- Mint the signed runtime→KF workspace token per run from the `ExecutionGrant` (§5.3):
  `actor_type=agent`, `team_id`, `uid`, `agent_instance_id` from the grant — **not** the
  template/definition `agent_id` (G1) — plus `aud` = KF filesystem service and a short
  run-bounded `exp`. Attach it to every MCP filesystem call; the agent process never sees
  the claims in mutable form.
- Route bare SDK and generic ReAct writes into
  `/teams/{team}/agents/{agent_instance_id}/users/{uid}/...`.
- Refuse to construct absolute paths that name another team, user, or agent instance.
- Route SDK and generic ReAct filesystem operations through Knowledge Flow MCP.
- Persist and replay `LinkPart` values in chat history.

### 13.4 control-plane

- Continue to issue the execution grant carrying `agent_instance_id`.
- Agent-folder label disambiguation is handled render-time in the frontend by default
  (§3.1); a per-team unique-`display_name` constraint is an optional later product choice,
  not a v1 requirement.

### 13.5 Frontend

- Render the four-root Files UI exactly as the user model states, gated per §12.3.
- Resolve `agent_instance_id` → `display_name` by joining the `agents/` listing to the team
  agent registry; show "Removed agent" for orphaned folders.
- Keep raw canonical paths and ids out of ordinary UI copy.
- Render provenance badges (`depose` / `genere` / `partage`) and the human-only share-copy
  action. Do not surface `source_path` to ordinary team readers.
- Use authenticated Knowledge Flow download behavior for file chips and Files UI.
- Do not add direct object-store URL handling as part of this RFC.

---

## 14. Acceptance Criteria

Layout and identity:

- Alice in fredlab sees exactly `Resources`, `Mon espace`, `Espace d'equipe`, and `Agents`.
- `Resources` is read-only from `/fs` and agent tools.
- A team admin can upload a template to `Espace d'equipe/templates`.
- A user can upload a private template to `Mon espace/templates`.
- Agent-generated files are visible under `Agents / {agent display name} / ...` for the
  owning user; the UI resolves `agent_instance_id` to the logical name and never shows the
  uuid or template id.
- Two agent instances enrolled from the same template write to separate folders (keyed by
  `agent_instance_id`), never a shared template-id folder.
- No two agent folders in a team render the same label (via unique `display_name` **or**
  deterministic render-time suffixing — §3.1).

Principal and trust (§5):

- A human `/fs` request that supplies `actor_type`, `agent_instance_id`, or a foreign `uid`
  is rejected, not honoured.
- An agent MCP call with a missing, unsigned, wrong-audience, expired, or
  claim/path-mismatched workspace token is rejected and audit-logged — never downgraded to a
  human call or silently redirected.
- The agent process cannot read, mint, or alter its own principal claims.

Routing and isolation:

- A bare agent write lands under `/teams/{team}/agents/{agent_instance_id}/users/{uid}/...`,
  not under `Mon espace`.
- Bare agent read/write is symmetric.
- Cross-team, cross-user, and **cross-agent** writes are rejected, including via absolute
  paths.
- An agent run cannot write or copy into `Espace d'equipe`, even when the acting user holds
  `CAN_UPDATE_RESOURCES`.

SDK:

- `ctx.fs.resolve_template(name)` resolves attached → user → team → bundled default, with
  first-match-wins precedence and a hard error on duplicate attachments (§2.2).
- `read_user` / `read_team` / `read_resource` exist and are read-only; bare writes never
  reach those spaces.
- `read_user` is selection-scoped by default: a read outside the run's granted selection is
  an authorization error, not an empty result (§7.3).
- `read_team` reads shared files the user can already read; agents get scoped reads (named
  file or single-level listing), not a recursive dump of the whole shared tree (§7.3).

Provenance and sharing:

- `FsEntry` carries creation provenance (`origin`, `created_by`, `producer`, `created_at`),
  standard metadata (`content_type`, `modified_at`, `modified_by`), and share fields
  (`shared_by`, `shared_at`). `version`/`etag` are out of v1 (§8).
- Agent outputs are not overwritten in place in v1; creation provenance is immutable (§6).
- `source_path` is audit/admin-only and is not exposed in the reader-facing `FsEntry` for
  arbitrary team members (§8).
- Client-supplied provenance cannot forge those fields.
- Human share-by-copy preserves the original, stamps `shared_by` / `shared_at`, and resolves
  name collisions atomically (no clobber); cross-request idempotency is not required in v1 (§9).

Cross-cutting:

- Chat download chips and Files UI downloads use Knowledge Flow product URLs, not raw
  object-store URLs.
- Scope enums and old artifact/resource ports remain absent / unexported.
- `make code-quality` and `make test` pass in touched projects when implementation begins.

---

## 15. Alternatives Considered

### 15.1 Let bare agent writes go to `Mon espace`

Rejected. It makes generated files indistinguishable from human-owned private files and
pollutes the user's personal area. Agent outputs belong in `Agents / {agent display name}`
by default. (Note: this rejected behaviour is what ships *today* — see §12 G1.)

### 15.2 Let agents publish directly to team shared space

Rejected for the hardened platform posture. Agents generate privately. Humans decide what
becomes shared. This is enforced by an `actor_type` rule, not by the user's permissions
(§5.2, §6).

### 15.3 Key the agents subtree by template id or display name

Rejected. The template id is shared across instances (collisions); the display name is
mutable and not unique. Only `agent_instance_id` is immutable, per-team-unique, and already
the runtime's selection key (§3.1).

### 15.4 Separate enforcement points for human HTTP and agent MCP

Rejected. Two gates drift. One gate that receives the full principal (§5) gives both
consistency and the actor-type distinctions the product rules need.

### 15.5 Expose raw `/teams/...` paths in the UI and SDK

Rejected. Raw paths are useful for implementation and tests, but they are not the product
experience. The UI and SDK should guide users and agent authors through stable intent.

### 15.6 Make object-store signed URLs part of the core filesystem contract

Rejected for this RFC. Download transport is a separate performance/security choice. The
layout works with proxy downloads, streaming proxy downloads, or future signed URL
optimizations without changing the user model.

### 15.7 In-place editing of agent outputs

Deferred for the first target. Three models exist: (a) overwrite in place with edit-tracking
fields, (b) forbid overwrite entirely, (c) an edit forks a new human-owned derivative linked
to the agent origin. Each adds fields and UI the core flows do not need yet. v1 takes the
simplest fully-working stance: agent outputs are not edited in place; a user who wants to
change one downloads it and re-uploads into `Mon espace` as their own file (§6). Revisit with
a concrete model — (a), (b), or (c) — only when a real editing need appears.

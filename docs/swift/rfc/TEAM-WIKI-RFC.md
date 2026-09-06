# RFC — Team Wiki: a shared knowledge base written by agents and governed by humans

**Status:** Draft for developer review — nothing implemented
**Author:** Maxime Daragon
**Date:** 2026-09-06
**Area:** `control-plane-backend` (owner: tables, API, authorization), a new
capability package (agent tools only), `frontend` (Wiki page, HITL diff modal)
**Tracking:** none yet — an issue should be cut from §14 once this RFC is approved
**Related:** `writable_document` capability
(`libs/fred-capability-writable-document/`) as the reference vertical for a
capability package; `platform_postgres` / `document_access` as the reference for
a capability reaching an external service through a typed port;
`capabilities/AUTHORING.md`; `platform/REBAC.md` (team roles);
`design/FILESYSTEM.md` and `AGENT-FILESYSTEM-HARDENING-RFC.md` §9 (why the team
file space is **not** the storage — §5.2)

---

## 1. Why this exists — the philosophy, and why it constrains the design

### 1.1 The idea

The "LLM wiki", as popularised by Andrej Karpathy, is a simple inversion of how
we usually give models context. Retrieval-augmented generation hands the model
**raw material** — document chunks, retrieved fresh on every question, digested
from scratch every time, then thrown away. A wiki holds **conclusions**: text
that was already understood once, written down, and improved since.

The difference is not storage, it is *compounding*. With retrieval alone, the
tenth person to ask "how do we deploy to the client's cluster?" pays the same
cost as the first, and the reasoning of the first nine is lost. With a wiki, the
first answer becomes a page, the second corrects it, the third adds the edge
case — and the team's collective understanding is an artifact rather than a
series of transcripts nobody reads again.

Two properties make it more than a document folder:

- **It is written for two audiences at once.** The same page is read by a human
  opening the Wiki tab and by an agent composing an answer. Not two formats, not
  a human doc plus a machine index: one text, curated by both.
- **The model is a contributor, not the author.** It drafts, restructures and
  keeps things current at a pace no team sustains by hand. Humans decide what
  is true and what stays. A wiki the model owns outright degrades into a
  plausible-sounding artifact nobody trusts — which is worse than no wiki,
  because people act on it.

### 1.2 Why Fred needs it specifically

Fred already has a corpus: uploaded documents, ingested, chunked and searchable.
That covers *reference* knowledge — the contract, the specification, the report.
It covers nothing of what a team actually knows: the decisions taken and why,
the client's real constraints, the gotcha that cost two days last month, the
shape an answer should take here. That knowledge exists only in conversations
today, and dies with them.

The corpus also cannot be *corrected*. A document is a snapshot of what someone
wrote once; you replace it or you live with it. A wiki page is meant to be
wrong at first and improved after.

### 1.3 What this means for v1 — go slowly, on purpose

The failure mode of this feature is not a bug. It is **silent quality decay**: a
wiki that fills with confident, agent-written, unreviewed pages that nobody
trusts and everybody stops reading. That is not fixable by a patch, because by
the time it is visible the trust is gone.

So v1 optimises for trust rather than for capability:

- Every agent write is **approved by a human**, in the chat, with the diff shown.
- Every version is **kept**; every page says **who wrote it** and whether a human
  or an agent produced the last change.
- Everything an agent does is **reversible by an editor**, in one click.
- The agent can **create and modify**. It can never delete, never rename, and
  never touch the rules page.

And v1 deliberately withholds several obvious features (§13) — not because they
are hard, but because each one is easier to add once we know how the wiki is
actually used than to remove once people depend on it.

---

## 2. Goals

1. A per-team wiki: a tree of Markdown pages, readable by every team member in
   the product and by every agent granted the capability.
2. Editors manage the wiki directly: create, edit, move, delete, revert.
3. An agent with the capability can **read** the wiki, and — when the capability
   is configured for it — **propose** page creations and edits, each gated behind
   a human approval in the chat showing the exact diff.
4. A **rules page** whose content is injected into the system prompt of every
   agent holding the capability, and which no agent can ever modify.
5. Full revision history, with restore.
6. No new authorization concept: the existing team roles decide everything.

## 3. Non-goals for v1

- Not a corpus replacement, and **not indexed into the vector store** (§13.1).
- No cross-team wiki, no page-level permissions, no private pages.
- No asynchronous review queue (§12.2) — approval is synchronous, in the chat.
- No comments, no page-level discussion, no @mentions.
- No attachments or images beyond what Markdown links can already reference.
- No import from, or export to, the corpus.

---

## 4. Reuse audit (2026-09-06)

Run before writing this document, per `CLAUDE.md`.

| Looked for | Found | Verdict |
| --- | --- | --- |
| An existing wiki / knowledge-base issue or RFC | none | new ground |
| A shared long-term agent memory | `MULTI_AGENT_MEMORY.md` is **conversational** memory (turn carry-forward, checkpoints); long-term semantic memory is an explicit non-goal there | no overlap |
| A collaborative Markdown surface | `writable_document` — session-scoped, single-user-owned, no hierarchy, no history | wrong scope, right **pattern** (§5.3) |
| A team-shared file space | `/teams/{t}/shared` in `FILESYSTEM.md` | disqualified — see §5.2 |
| A wiki-shaped UI to copy | `HelpCenterPage` (tree left, Markdown article right, search) | reuse the layout |
| A Markdown editor | `MDXEditor`, already used by `writable_document` | reuse |
| An approval gate | `HitlSpec(require=True)` on a capability tool | reuse as-is |
| A prompt-injection hook | capability middleware (`abefore_model`, `awrap_model_call`) | reuse as-is |
| A per-team feature gate | `TeamScopePolicy.ADMIN_GATED` + per-team enablement | reuse as-is |

Nothing here is invented. The only genuinely new pieces are two tables, one REST
surface, one typed port, one capability package and one frontend page.

---

## 5. The structural decisions

Each decision below states what was chosen, why, and — as this RFC is a proposal
— **how to reverse it** if a reviewer disagrees.

### 5.1 The wiki is owned by control-plane, not by the capability

**Decision.** The tables, the REST API and the authorization live in
`control-plane-backend`. The capability installed in the agent pod owns **no
table, no migration and no router**; it reaches the wiki through a new typed
`TeamWikiPort` on `RuntimeServices`, exactly as `platform_postgres` reaches the
platform database through `PlatformSqlPort` and `document_access` reaches
knowledge-flow through `DocumentSearchPort`.

**Why.** Four facts, checked in the code, each sufficient on its own:

1. **The databases are separate.** The agent pod has its own store
   (`storage.postgres` in `apps/fred-agents/config/configuration.yaml`);
   control-plane has another. A capability-owned table lives in the *pod's*
   database.
2. **There is more than one agent pod, and there will be more.** The deployment
   declares three runtime catalog sources today (`fred-agents`,
   `fred-samples-agents`, `rags-agents`). A capability installed in two of them
   would give one team **two different wikis**, one per pod, with nothing in the
   product signalling the split. That alone disqualifies pod ownership for
   team-shared knowledge.
3. **A capability's API address is only published during a chat.** Control-plane
   computes `capability_base_urls` from the *agent instance's* selected
   capabilities and ships them on `ExecutionPreparation`
   (`product/service.py`, consumed at `useChatSse.ts:377`). The Wiki page lives
   in the team navigation: no chat, no instance, therefore no way to discover
   the API. The wiki exists independently of any agent; its API must too.
4. **Pod availability.** `PLATFORM_RUNTIME_MAP.md` states that when a runtime pod
   is down its templates disappear from discovery. Acceptable for an agent
   template; not for a team's written memory.

To which one design argument is added: the wiki is a **team governance surface**,
and every other team-navigation page (Resources, Agents, Prompts, Usage,
Settings) is served by control-plane, where team roles and ReBAC already live.

**Reversing this.** If a reviewer wants the wiki inside the capability package
(the `writable_document` shape), the four facts above have to be answered, not
argued around: pin the capability to exactly one pod and enforce it at boot
(fact 2), publish the capability base URL on a chat-independent endpoint
(fact 3), and accept that the wiki is unavailable whenever that pod is
(fact 4). The data model in §6 is unaffected — it would move verbatim into a
capability-owned Alembic tree. The port in §7.1 would collapse into a direct
store call, which is a simplification, and the frontend would call the pod
instead of control-plane. Estimated as a smaller package but a strictly weaker
product; recorded here so the trade is explicit rather than rediscovered.

### 5.2 The team file space is not the storage

**Decision.** The wiki does not use `/teams/{t}/shared` or the `/fs` routes.
Nothing in this feature touches the team file space.

**Why.** `FILESYSTEM.md` states outright that agents should not write there, and
explains why: the Knowledge Flow `/fs` boundary only ever sees the authenticated
*user*, never "which agent instance is calling", so it cannot tell Alice's
browser from Alice's agent. That is issue #2113 — an agent listing `teams/`
today sees **every team the human can read platform-wide**, not the one team the
conversation belongs to. The fix is the scoped `WorkspaceService` (#2498), whose
*contract* was merged as PR #2501 but whose implementation does not exist (there
is no `workspace/` feature directory in knowledge-flow), and which is itself
gated behind #2113.

Building the wiki on that boundary would mean inheriting an open critical
isolation gap, and blocking on a chantier we do not control. Beyond timing, the
file space also offers no revisions, no hierarchy metadata and no page identity.

**Reversing this.** Wait for #2113 and #2498 to ship, then the question can be
reopened honestly. Even then the revision model of §6 has no equivalent in a
file store, so this would be a rewrite rather than a substitution.

### 5.3 One table for all teams, never one table per team

**Decision.** Two tables, shared by every team, with `team_id` as an indexed
column. Never a table (or schema) created per team.

**Why.** A table per team means DDL executed when a team is created — schema
changes outside Alembic, invisible to the migration history. `CLAUDE.md`
devotes a section to keeping that history linear with exactly one head per
backend; tables born outside it are precisely what that discipline exists to
prevent.

Isolation is therefore per row, and its safety rests on one rule, stated here
because it is the whole of the tenant boundary:

> `team_id` is always derived server-side from the authenticated request
> context. It is never read from a caller-supplied parameter, and it is never
> assembled by a client.

This is the same lesson `AGENT-FILESYSTEM-HARDENING-RFC.md` §9 draws for the
Workspace namespace, applied one layer up.

**Reversing this.** There is no reasonable path to per-team tables. If row-level
isolation is ever judged insufficient, the escalation is Postgres row-level
security on `team_id`, which is additive and changes no application code.

### 5.4 The capability *is* the grant

**Decision.** Enabling the wiki capability in write mode on a team agent grants
wiki contribution to **every member who uses that agent**, not only to editors.
No new ReBAC relation is introduced.

**Why.** This is already how every capability in Fred works: an editor enables
`platform_postgres` on a team agent, and every member chatting with that agent
queries the platform database. The capability is the grant; the audience is
whoever may use the agent (`can_use_team_agents`, a `team_member` permission).

It is also the only reading consistent with §1: a wiki only members may *read*
and only editors may *feed* is not a wiki, and it forfeits most of the material
— members hold the volume of conversations, and that is where the undocumented
knowledge is.

A supporting technical fact: `CapabilityIdentity` carries `user_id`,
`session_id`, `team_id` and `agent_instance_id` — **no role**. A capability
literally cannot check a team role today. The check therefore belongs in the
control-plane API, which is also where it is safest.

Editors keep exclusive control of the *governance* surface (§9): the rules page,
deletion, renaming/moving, direct UI editing, and restore.

**Reversing this.** If contribution must be restricted to editors, change one
predicate in the write endpoint (`CAN_UPDATE_RESOURCES` instead of team
membership) and nothing else. The reverse move — from editors-only to members —
is equally cheap. This is deliberately a one-line policy decision, not a
structural one. Note that restricting it makes §12.2's review queue *more*
attractive, not less, because members would then need a way to contribute at all.

### 5.5 Safety comes from reversibility, not prevention

**Decision.** The wiki is protected by human approval on every agent write, full
revision history, per-revision attribution, and one-click restore — not by
narrowing who may contribute.

**Why.** This is the wiki social model, and it is the one that has actually
worked at scale. The worst realistic outcome is noise, and noise is cleaned by
an editor in a click. Prevention, by contrast, costs the feature its reason to
exist (§1.2) while providing weaker guarantees than it appears to: a member who
wants to write nonsense into the wiki can already do so by asking an editor.

**Reversing this.** §12.2 (proposals queued for editor review) is the stricter
model, and the data model in §6 already supports it — a `proposed` revision that
is neither approved nor rejected *is* a queued proposal. Only the surfaces are
missing.

---

## 6. Data model

Two tables, following `writable_document`'s conventions: plain columns, **no
foreign keys into core tables** (so install/uninstall ordering stays free), one
owned Alembic revision.

### `team_wiki_pages` — identity, hierarchy, current state

| Column | Type | Notes |
| --- | --- | --- |
| `page_id` | `str(64)` PK | opaque id |
| `team_id` | `str(128)`, indexed | the tenant boundary (§5.3) |
| `parent_page_id` | `str(64)`, nullable | `NULL` at the root; plain column, not an FK |
| `slug` | `str(160)` | unique per `(team_id, slug)`; the URL and the agents' address |
| `title` | `str(300)` | display name |
| `kind` | `str(16)` | `page` or `rules`; at most one `rules` row per team |
| `current_revision_id` | `str(64)`, nullable | the published content; `NULL` only mid-creation |
| `needs_review` | `bool` | set when an agent's edit is published, cleared by an editor (§8.8) |
| `position` | `int` | sibling ordering |
| `created_at` / `updated_at` | `timestamptz` | |
| `created_by` / `updated_by` | `str(128)` | user ids |

### `team_wiki_revisions` — content, append-only

| Column | Type | Notes |
| --- | --- | --- |
| `revision_id` | `str(64)` PK | |
| `page_id` | `str(64)`, indexed | |
| `team_id` | `str(128)`, indexed | denormalised so every query filters on it without a join |
| `content_md` | `text` | the Markdown |
| `base_revision_id` | `str(64)`, nullable | what the author started from — the conflict check (§8.4) |
| `status` | `str(16)` | `proposed`, `published`, `rejected`, `superseded` |
| `author_user_id` | `str(128)` | always a real user — the human who wrote or approved |
| `author_kind` | `str(16)` | `human` or `agent` |
| `agent_instance_id` | `str(128)`, nullable | which agent proposed it; `NULL` for a human edit |
| `session_id` | `str(128)`, nullable | the conversation an agent edit came from — the audit trail back to its context |
| `created_at` | `timestamptz` | |

**Content is never modified in place.** An edit appends a revision and moves the
page's `current_revision_id`. Three of §8's behaviours fall straight out of that
shape: history and restore are free, an agent's proposal is simply a revision
not yet published, and conflict detection is a comparison of two ids.

**The rules page is a page.** `kind = "rules"` rather than a separate table, so
it inherits history, attribution and restore at no cost, and the agent write
tools exclude it with a single filter in a single place (§8.6).

---

## 7. Architecture

### 7.1 `TeamWikiPort` — the capability's only way in

A new port on `RuntimeServices`, implemented in `fred-runtime` as an HTTP client
against control-plane, following `PlatformSqlAdapter`'s shape: all policy in the
adapter, none in the SDK contract and none in capability code.

```
list_pages(team_id)                                  -> tree (id, slug, title, parent, needs_review)
read_page(team_id, slug)                             -> title, content_md, revision_id, author_kind
propose_page(team_id, parent_slug, title, content)   -> proposal_id, diff summary
propose_edit(team_id, slug, content, base_revision)  -> proposal_id, diff summary
publish_proposal(team_id, proposal_id)               -> published revision, or a conflict error
reject_proposal(team_id, proposal_id)                -> ()
```

`team_id` is passed by the adapter from the verified runtime context, never by
capability code and never by the model.

**Authentication.** The adapter calls control-plane with the **end user's**
bearer, exactly as the pod already does to resolve an agent instance
(`{control_plane_url}/teams/{team_id}/agent-instances/{id}/runtime`). This is
the right identity here, and a pleasant simplification: the write is authorised
*as the user*, which is precisely the enforcement model §5.4 requires. It avoids
the machine-identity machinery `WorkspaceService` needs, because that contract
must distinguish an agent from a human at a shared file boundary, whereas here
we deliberately want the user to be the authority and the HITL gate to be what
makes the act deliberate.

### 7.2 The capability package

One package, one capability id (`team_wiki`), `TeamScopePolicy.ADMIN_GATED` so a
platform admin grants it per team. Its `ConfigModel` carries a single field:

| Field | Type | Meaning |
| --- | --- | --- |
| `mode` | `read` \| `read_write` | default `read` |

Tools, built per turn in `tools()`:

- always: `wiki_list_pages`, `wiki_read_page`
- when `mode = read_write`: `wiki_propose_page`, `wiki_propose_edit`, both
  declared with `HitlSpec(require=True)`

No delete tool and no rename tool exist. That is the enforcement of §5.4's
invariant — not a check that could be bypassed, but an absence.

### 7.3 Prompt injection

Through the capability's middleware, once per turn:

- the **rules page** verbatim, capped at 4 000 characters;
- a **compact index** of the wiki: `slug — title`, one per line, capped at
  4 000 characters. Past the cap the index is replaced by a line telling the
  model to call `wiki_list_pages`.

Both caps matter: the baseline system prompt already sits near 16 700 tokens
(#2412), and this rides on every turn of every agent holding the capability.

---

## 8. Behaviour — the eight decisions

### 8.1 Structure

A tree by parent page, not by folders: a page *is* the node. `slug` is unique
per team and is what both the URL and the agents use. Maximum depth 3; maximum
page size 100 KB.

*Evolution.* Depth and size are constants, trivially raised. Folders were
rejected because they add a second kind of object that carries no content and
that agents would have to reason about.

### 8.2 One change, one approval

An agent's proposal is approved or rejected as a whole. The approver cannot
amend it in the modal.

*Evolution.* Amending requires an editor inside the HITL modal and a decision
about who is then recorded as the author. Both are real work, and neither is
needed to learn whether the feature is useful. §12.1.

### 8.3 Reads

Every team member reads the wiki in the product. Every agent holding the
capability reads every page of its team's wiki. No private pages in v1.

*Evolution.* Page-level visibility is the kind of thing that is easy to add and
almost impossible to remove; it needs a real use case first.

### 8.4 Conflicts

A proposal records the `base_revision_id` it started from. At approval time, if
the page's `current_revision_id` no longer matches, the publication is
**refused** and the agent is told, with the current content, so it can redo its
edit. Without this, the last writer silently wins and someone's work vanishes.

*Evolution.* A three-way merge is the obvious improvement and needs no schema
change — the base, the current and the proposal are all present.

### 8.5 History and restore — in v1

The revision list is visible on every page, and an editor can restore any
earlier revision (which appends a new revision pointing at the old content,
rather than deleting history).

This is **not optional**: it is the safety net that makes §5.4's open
contribution defensible. Shipping open contribution without restore would be
shipping the risk without the mitigation.

### 8.6 The rules page

One per team, at a fixed slug, `kind = "rules"`. Editable only by editors, and
only in the UI. Excluded from `wiki_propose_edit` by its `kind`, so no agent can
modify it under any configuration. Capped at 4 000 characters.

**What it is honestly worth.** A rules page in the prompt *orients strongly*; it
does not *guarantee*. The guarantee comes from the approval gate and from the
absence of dangerous tools. This is worth stating plainly because the feature is
easy to over-trust: if the rules page were the only protection, a well-crafted
page elsewhere in the wiki could talk an agent out of it. It is a quality
instrument, not a security boundary.

### 8.7 Personal spaces

Personal spaces get a wiki too. A personal team is a real team in the
authorization model, and its owner holds `team_editor` on it — so everything
above applies unchanged, with an audience of one. It is also the natural place
to try the feature before enabling it on a collaborative team.

### 8.8 The review mark

Publishing an agent-authored revision sets `needs_review` on the page. The Wiki
UI shows the mark, offers a filter, and any editor clears it.

This is what gives editors a review queue without building one — and it is the
counterpart of §5.4: contribution is open, but everything an agent produced is
visibly pending a human's eye until someone says otherwise.

---

## 9. Permissions

| Action | Who |
| --- | --- |
| Read the wiki (UI and agents) | any team member |
| Create / edit a page in the UI | `team_editor` |
| Propose a page or an edit through an agent | any team member, through an agent whose capability is in `read_write` mode |
| Approve one's own agent's proposal | the member driving that conversation |
| Delete, rename, move a page | `team_editor` — no tool exists for agents |
| Edit the rules page | `team_editor`, UI only |
| Restore a revision | `team_editor` |
| Clear the review mark | `team_editor` |

Enforcement is server-side in control-plane, on every call, from the
authenticated identity. The frontend hides what a user cannot do; it never
decides it. The precedent worth remembering is `ui.visible_when` in
`AUTHORING.md`, documented as display-only with the stored value kept — this
codebase has already learned that a hidden field is not a disabled field.

---

## 10. Security model

| Threat | What stops it |
| --- | --- |
| Cross-team read or write | `team_id` derived server-side from the request context, never from a parameter (§5.3) |
| An agent silently rewriting the wiki | every write is a proposal; a human approves it with the diff in front of them |
| An agent deleting or renaming | no such tool exists |
| An agent editing its own rules | the `kind = "rules"` filter, unconditional |
| A poisoned page steering an agent | pages are attributed and reviewable; the review mark surfaces agent-written content; an editor can restore. Not eliminated — see the residual below |
| Prompt-size abuse | rules and index both capped (§7.3); page size capped (§8.1) |
| A member exceeding their rights | control-plane checks the role on every call, whatever the frontend showed |

**Residual risks, stated rather than hidden.**

1. **Indirect prompt injection through wiki content.** An agent reads pages
   written by other agents and by members. A page crafted to manipulate a reader
   is possible, and the wiki is a durable, high-trust surface — which is exactly
   what makes it attractive. v1 mitigates by attribution, the review mark and
   reversibility; it does not eliminate. Anyone raising the bar should look at
   marking wiki content as untrusted data in the prompt, which is a broader
   platform question than this feature.
2. **`author_kind` is declared, not proven.** The capability tells control-plane
   that a write came from an agent. Someone holding a user's token could claim
   `human` for an agent write. Severity is low — with that token they could use
   the UI directly — and the gain is limited to muddying the audit trail. The
   hardening path, if it ever matters, is the machine-identity model of
   `AGENT-FILESYSTEM-HARDENING-RFC.md` §9.1.
3. **A page can hold anything a member can type.** There is no secret detection
   and no classification. The wiki is exactly as sensitive as the team it
   belongs to.

---

## 11. Frontend

**The Wiki page** (`/teams/{id}/wiki`), in the team navigation panel: page tree
on the left, rendered Markdown on the right — the `HelpCenterPage` layout, which
already solves this exact shape. Editors get an **Edit** button opening
`MDXEditor`, the same component `writable_document` uses. A page displays its
last author, its `human`/`agent` origin, the review mark when set, and its
revision list.

**The HITL diff modal.** This is the one genuinely new frontend mechanism. The
approval prompt carries an identifier for the proposed revision; a **See the
changes** button in the HITL widget opens a modal rendering the diff between the
current content and the proposal.

Today the approval request carries only `PendingToolCall.args_preview`,
truncated to 1 200 characters, and the widget does not display it at all. So the
capability needs a way to contribute a renderer to the HITL widget, keyed by
tool name — the same registry pattern the codebase already uses for capability
side panels (`sidePanelRegistry`) and capability config widgets
(`configWidgetRegistry`). It is a third instance of an established pattern, not
a new mechanism.

Because control-plane owns the API (§5.1), touching its controllers means
regenerating the frontend client in the same change (`make update-control-plane-api`),
per `CLAUDE.md`'s generated-client rule.

---

## 12. Deferred, with the direction recorded

Direction only. None of this is specified, and per the repository's practice a
ticket must not be cut for any of it until it is.

### 12.1 Amending a proposal before approving

The approver edits the agent's draft in the modal, then publishes. Needs an
editor in the modal and a decision on authorship — most likely a `human`
revision whose `agent_instance_id` records what it came from.

### 12.2 Proposals queued for editor review

The stricter model of §5.5: a member's agent proposal is not published on
approval but queued; an editor publishes it later. The data model already
supports it — a `proposed` revision that is never resolved *is* a queue entry.
What is missing is a review inbox in the UI and an honest answer to what the
agent is told in the meantime, since it cannot wait for an asynchronous review.
Worth building only if noise becomes a real problem rather than an imagined one.

### 12.3 Retrieval

Two distinct steps, in order. First, full-text search over pages, for humans and
as a `wiki_search` tool — cheap, and the compact index of §7.3 stops scaling
somewhere around a hundred pages. Second, indexing wiki pages into the vector
store so wiki knowledge participates in ordinary retrieval. The second changes
what the wiki *is* — it stops being a curated surface and becomes part of the
corpus — so it deserves its own decision, not a follow-up commit.

### 12.4 Page summaries

A `summary` column, written by whoever edits the page, shown in the tree and
used in the compact index instead of bare titles. Additive, cheap, and probably
the first thing worth adding once there are enough pages for the index to
matter.

### 12.5 A "write what you learned" prompt

The wiki only compounds if pages actually get written. Nothing in v1 nudges an
agent to contribute at the end of a useful conversation. Whether that should be
a prompt fragment, an explicit user action, or nothing at all is a product
question v1 is deliberately not answering — but it is the difference between a
wiki that fills and one that stays empty, and it should be revisited as soon as
the mechanism works.

---

## 13. Known limitations that stay open in v1

1. **Not in retrieval.** An agent finds wiki content through the injected index
   and the read tools, never through ordinary document search. A team with both
   a large corpus and a large wiki will notice the seam. §12.3.
2. **No search.** Navigation is by tree and title.
3. **No concurrent editing.** Two humans editing one page is last-writer-wins
   between humans; only agent proposals carry the `base_revision_id` check. This
   is worth knowing before someone reports it as a bug.
4. **The compact index does not scale.** Past its cap the agent must call
   `wiki_list_pages`, costing a tool round-trip before it knows what exists.
5. **The rules page is guidance, not a guarantee.** §8.6.
6. **A member can approve their own agent's proposal.** By design (§5.4), and the
   review mark is what compensates.

---

## 14. Delivery

Four slices, in order. Each is a reviewable PR; none is a big-bang.

| # | Slice | Content |
| --- | --- | --- |
| 1 | Control-plane foundation | the two tables and their migration, the REST API, role enforcement, the generated client |
| 2 | The Wiki page | tree, rendered page, editor for editors, revision list and restore, the rules page, the review mark |
| 3 | The capability, read-only ✅ shipped 2026-09-07, issue #2573 | package, `TeamWikiPort` and its adapter, `wiki_list_pages` / `wiki_read_page`, rules and index injection |
| 4 | Agent writes | the two propose tools, the HITL gate, the pending-revision flow, the diff modal and its HITL renderer registry |

Slices 1 and 2 deliver a usable human wiki with no agent involvement at all —
which is the right order: it lets the team judge whether the wiki is worth
having before any agent writes into it.

`fred-performance-reviewer` is required on slice 3, which touches per-turn prompt
composition.

**Two decisions taken while building slice 3**, both outside what this RFC had
settled; the durable form of each lives in `CONTROL-PLANE-PRODUCT-CONTRACT.md`
§49, and they are recorded here only because they change what §5 said.

*The capability is ReAct-only.* The rules page reaches the model as a
system-prompt fragment, and prompt fragments are a ReAct-loop hook the Graph
runtime never runs. §3 calls the rules non-negotiable, so a Graph agent
selecting this capability must fail loudly at assembly rather than answer
without them. The cost is real: the wiki is unavailable to Graph agents
entirely, read included. Reversing this means finding a prompt seam both
runtimes share — the closest is `McpCapability.prompt_group()`, which the
assembler currently keys off `isinstance(capability, McpCapability)` and would
have to generalise.

*Enabling the capability is what gives a team a wiki at all.* Not only its
agents: the control-plane refuses every wiki route for a team without it. §5.4
said "the capability is the grant" about agent access; this extends the same
sentence to people. The reasoning is that a wiki no agent can read is a
document store, and the team space already is one. Reversing this means
splitting the two — a separate deployment flag or ReBAC relation for human
access — and accepting that a team can then maintain a wiki nothing reads.

---

## 15. Alternatives considered and rejected

- **Files in the team space.** §5.2.
- **A capability-owned table in the agent pod**, the `writable_document` shape.
  §5.1 — right pattern for session-scoped data, wrong for team-scoped data.
- **A new ReBAC relation for wiki contribution.** Rejected: the capability
  already is the grant (§5.4), and a new relation would be a second, parallel
  way to express the same thing.
- **A dedicated wiki agent.** Rejected: it would make the wiki someone's job
  instead of a by-product of ordinary work, which is the opposite of §1.
- **Storing pages in the corpus as ingested documents.** Rejected: documents are
  snapshots, not editable pages; ingestion is asynchronous; and it would collapse
  the very distinction of §1.2 between reference material and digested
  knowledge.

---

## 16. Open questions

None blocking. The design decisions of §5 and the behaviours of §8 were settled
with the developer on 2026-09-06. What remains open is deliberately deferred to
§12, and must be specified before any ticket is cut for it.

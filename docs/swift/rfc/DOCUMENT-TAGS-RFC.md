# RFC: Knowledge Flow — Arbitrary Document Business Tags (Labels)

**Status:** v1 implemented (metadata-field design, §5); definitions-table is a
documented future enhancement
**Author:** Dimitri Tombroff
**Date:** 2026-06-18
**ID:** DOC-TAGS
**Scope:** swift `apps/knowledge-flow-backend` (data model + API) and the workspace UI
**Related:** `KNOWLEDGE-FLOW-SIMILARITY-SEARCH-RFC.md` (KF-SIMILARITY-SEARCH — the
consumer), `KNOWLEDGE-WORKSPACE-REWORK-RFC.md` (FRONT-09 — the UI surface)
**Contract impact:** additive — a **separate descriptive label field** on the
document; the permission **tag** system is untouched. **Business tags are NOT a kind
of tag** (see §4).

> ⚠️ **Read §4 first.** "Tag" and "business tag" share a word and nothing else. They
> are different systems with different purposes; this RFC exists partly to keep them
> from being confused or merged.

---

## 1. Decision (in one paragraph)

Let users attach **arbitrary, flat, user-defined labels** to documents — e.g. "CV",
"DVA", "DAT", "confidential" — independent of where the document lives in the folder
hierarchy. These **business tags** become a targeting dimension for the targeted
similarity search (KF-SIMILARITY-SEARCH): "compare within the documents labelled
*DVA*", not just "within this folder". **Storage recommendation:** keep the existing
Postgres `tag` table as the **single source of truth** for labels, and target search
by **resolving a label to its document set in Postgres, then using the search's
document-targeting** — so we avoid denormalising business labels into the vector
index (and the stale-metadata problem that would create).

---

## 2. Problem (functional)

Documents today are organised by **folders / libraries** — a hierarchy where a
document lives in one place. That is too rigid for assessment-style work:

- A single document is often **several things at once** ("this is a *DVA* **and**
  *confidential*").
- Useful groupings are **cross-cutting**, not hierarchical ("all *CV* documents
  across every project").
- The targeted similarity search (KF-SIMILARITY-SEARCH) currently targets
  **documents and folders**; the rags team wants to target a **meaningful subset of
  documents the user has identified** — "compare within the *DVA* set" — which a
  folder cannot express.

So we need **flat, many-to-many, user-defined labels on documents**, usable as a
search target and surfaced in the UI.

---

## 3. What already exists (so we extend, not duplicate)

Knowledge Flow already has most of the machinery — but with a critical caveat:
**today's tags are an access/scope construct, not descriptive metadata.**

- A **Postgres `tag` table** (`core/stores/tags/`) — tags already live in a
  relational store.
- Tags currently have one type, `TagType.DOCUMENT`, used as **hierarchical
  libraries/folders** (they carry a `path`). **They carry scope and permissions** —
  a document's library determines *who can see it*; assigning/removing such a tag is
  a **security-relevant** act, governed by ReBAC and team/personal isolation.
- Documents are **many-to-many with tags** already (`add_tag_id_to_item` /
  `remove_tag_id_from_item`) — assignment after ingestion is supported at the
  metadata level.
- The **vector store already carries `tag_ids` in chunk metadata** and **already
  filters search by them** (`_matches_tag_ids`) — but those `tag_ids` are written
  **at ingestion** and are **not updated** when a tag is added/removed afterwards.

Two gaps follow: (a) there is no **flat, label-style** tag kind (today's tags are
hierarchical containers), and (b) the denormalised vector `tag_ids` **go stale** for
anything tagged after ingestion.

---

## 4. Core principle: a "tag" and a "business tag" are NOT the same thing

**This is the most important point in the RFC. Fred "tags" and "business tags"
(labels) are not similar, not related, and must never be merged, reused for each
other, or treated as variants of one concept. They only share an unfortunate word.**

They are **two different systems** with opposite purposes:

| | Fred **tag** (existing) | **Business tag / label** (new) |
| --- | --- | --- |
| What it is | an **access-control / scope** construct | **descriptive content metadata** |
| Answers | **who may see** the document | **what** the document is |
| Backed by | the **permission tag system** (ReBAC, team isolation, libraries) | a plain **label field on the document** |
| Changing it | a **security event** — alters visibility | a **harmless edit** — zero access impact |
| Hierarchy | hierarchical (folders/libraries, `path`) | flat, many-to-many, cross-cutting |
| Governance | curated, permissioned | free-form, any user who can edit the doc |
| Lifecycle | stable, governed | casual, high-churn |
| Example | "library: Project-Alpha" | "CV", "DVA" |

**Why this matters (the danger of confusing them):**
- A user adding the label "DVA" must **never** be able to change who can see a
  document. If labels lived in the tag system, a descriptive edit could silently
  widen or narrow access — a security bug.
- The permission machinery must **never** gate or complicate free-form labelling, or
  the feature dies under friction.

So a label is a metadata write with **zero access-control consequence — by
construction, not by convention.** Concretely: **labels are NOT** a `TagType`, **NOT**
a `kind` flag on the permission `tag` table, and **NOT** routed through any
tag/ReBAC code path. They are a separate descriptive field that the access layer
never reads. The existing scope tags are untouched by this RFC.

> If you remember one thing: **never let a "business tag" flow into the tag /
> permission system, and never let a scope "tag" be exposed as a descriptive label.**

---

## 5. Storage decision — *the subtle question*

> *"Where do we store these — in the embedding metadata, in a new Postgres table,
> or both?"*

**Shipped in v1 — the metadata-field design:** labels are a plain
`DocumentMetadata.labels: list[str]` field, stored wherever document metadata is
already stored (the metadata store). This is the **single source of truth**; nothing
is denormalised into the vector index. "Target the *DVA* set" is **resolve-then-
target**: `GET /documents/by-label/{label}` resolves the label to the readable
documents carrying it, which KF-SIMILARITY-SEARCH then targets as documents.

This was chosen over a dedicated `document_label` *definitions* table for v1 because
it **maximises reuse** (no new store/table/feature/wiring — it rides the existing
metadata service and controller) and still **fully honours §4** (labels are a
distinct descriptive field, never touched by the tag/permission system). What it does
**not** yet provide: first-class label *definitions* (rename "CV"→"Resume" globally,
descriptions, a managed team vocabulary) — that is the **future enhancement** below.

> **Future enhancement (only when needed):** a dedicated Postgres `document_label`
> table for managed label *definitions* (rename/describe/team-scoped vocabulary),
> with assignments still as ids on the document. It stays **separate from the
> permission `tag` table** (§4). Add it when the rags team needs managed vocabularies,
> not before.

The denormalisation question still stands the same way (do not denormalise into the
vector index); the three options below are why:

| Option | How search targets by label | Cost |
| --- | --- | --- |
| **A. Postgres only — resolve then target** *(recommended)* | resolve `label → document ids` in Postgres, then use KF-SIMILARITY-SEARCH **document-targeting** | no vector sync ever; large labels → large id lists |
| B. Denormalise into vector metadata | vector store filters on the label `tag_ids` directly | **must keep vector metadata in sync** on every (re)tag — the stale-metadata problem (§3) |
| C. Both (B + A as fallback) | direct vector filter, Postgres as truth | best at scale, **but pays the sync cost** |

Why **A** wins for v1:

- It **reuses what we are already building.** KF-SIMILARITY-SEARCH already targets
  *documents*. "Target the *DVA* set" = Postgres resolves the label to its document
  ids → the search targets those documents. Nothing new in the vector layer.
- It **side-steps the consistency trap.** Because labels are mutable user data
  (added/removed any time, long after ingestion), denormalising them into vector
  chunks would require updating every chunk's metadata on every tag change — exactly
  the gap that exists today (§3). Option A never has that problem: Postgres is the
  only place a label lives.
- **Postgres is the right home for mutable business data anyway** — CRUD, rename,
  listing, UI all want a relational source of truth, not a vector index.
- A **separate table keeps the security guarantee structural** (§4): labels live
  outside the access/scope tag system, so a label can never be mistaken for a scope.

When to revisit (and only then): if a label routinely matches **thousands** of
documents, passing that many ids as a search target becomes unwieldy. *Then* add
denormalisation (Option B/C) as a **scale optimisation**, with an explicit
**propagation job** that updates vector `tag_ids` when labels change — and Postgres
still the source of truth. We should not pay that cost pre-emptively.

> Note: the existing ingestion-time `tag_ids` denormalisation for **library/folder**
> tags stays as-is. This RFC does not change it; it only declines to *add* business
> labels to it in v1.

---

## 6. Search integration

Amend **KF-SIMILARITY-SEARCH §targeting**: a search `target` may be expressed as one
or more **labels** in addition to documents/folders. Knowledge Flow resolves
`labels → document set` (Postgres) and runs the targeted search over those
documents. To the caller it is just "target the *DVA* set". No change to the search's
ranking or output contract.

---

## 7. API + UI surface

- **API (knowledge-flow):** create / rename / delete a label; list labels; assign /
  unassign a label to/from a document; list documents for a label (already partly
  present via the tag-item service). MCP exposure follows the search consumer's
  needs.
- **UI (workspace, FRONT-09):** in the resource browser, let users see a document's
  labels, add/remove labels, and filter the document list by label. This is the
  human entry point for "tag this as a DVA".

---

## 8. Edit rights (not access control)

Labels grant and restrict **nothing** — they never change who can see a document
(§4). The only questions are about **who may edit the metadata**:

- Who can **create / rename / delete** labels — any user, or curators? Are the label
  *definitions* **team-scoped** or **personal**?
- A user may only **assign** a label to a document they can already access (assignment
  follows existing document access; it does not alter it).

---

## 9. Decisions to settle with the rags team

1. **Separation (headline):** confirm labels are a **separate descriptive concept**,
   structurally outside the access/scope tag system — a label never affects
   visibility (§4)? — *strongly recommended.*
2. **Storage:** v1 ships as the **metadata-field** design (§5) — a `labels` field on
   the document, resolve-then-target for search, no vector denormalisation. Confirm
   that's the right v1, with the `document_label` *definitions* table as a later
   enhancement when managed vocabularies are needed.
3. **Predefined vs free-form:** do rags want a **controlled vocabulary** (a fixed set
   like DAT/MEX/DVA/CV) or fully **free-form** labels — or both (suggested set +
   free-form)?
4. **Relationship to the IS document *roles*** (DAT/MEX/CMDB already exist inside the
   rags information-system record): are business labels the **general-platform**
   mechanism that the rags roles become a **special case** of, or do they stay
   separate? (Worth deciding so we don't end up with two parallel tagging systems.)
5. **Scope/permissions** (§8).

---

## 10. Acceptance criteria

- A user can create a flat label and assign it to any document they can access,
  **after ingestion**, with no re-ingestion.
- The targeted similarity search can target **"the documents labelled X"** and only
  searches within them (via resolve-then-target).
- Labels are managed in the workspace UI (view / add / remove / filter).
- Existing library/folder tags and ingestion behaviour are unchanged.
- No stale-metadata risk: because labels are resolved at query time, label-targeted
  search is always consistent with the latest assignments.

---

## 10b. Implementation (v1 — shipped)

Backend, in `apps/knowledge-flow-backend`, reusing the existing metadata machinery
(no new store/table/feature/wiring; rides the already-registered `MetadataController`):

- `DocumentMetadata.labels: list[str]` — a descriptive field, **separate from the
  permission `tags` field**, never read by the access layer (§4).
- Pure helpers `normalize_labels` / `with_label_added` / `with_label_removed`
  (`features/metadata/metadata_utils.py`) — unit-tested.
- Service (`features/metadata/service.py`): `add_label_to_document`,
  `remove_label_from_document` (mirror `add/remove_tag_id_to_document` **but with no
  ReBAC on the label** — only the document's UPDATE access is checked),
  `get_documents_with_label` (resolve-then-target), `list_document_labels`.
- REST (`features/metadata/controller.py`): `POST`/`DELETE
  /documents/{uid}/labels/{label}`, `GET /documents/labels`,
  `GET /documents/by-label/{label}`.

Not in v1 (future): label *definitions* table (rename/describe/team vocabulary),
workspace UI, MCP exposure.

---

## 11. Out of scope

- Re-embedding or changing how documents are vectorised.
- Denormalising labels into the vector index (explicit **future** scale
  optimisation, §5 — not v1).
- Agent business logic (how rags decides what to compare).
- The rags pod / rags-services (consumers only).

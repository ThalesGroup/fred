# RFC: Knowledge Flow — Rename a Document

**Status:** Implemented (2026-07-30) — see §7 for how each open decision was resolved and §6 for the as-built route (differs from the originally-proposed path).
**Author:** Dimitri Tombroff
**Date:** 2026-06-29
**ID:** DOC-RENAME
**Scope:** swift `apps/knowledge-flow-backend` (metadata API) and the workspace UI (FRONT-09)
**Related:**
- `DOCUMENT-TAGS-RFC.md` (DOC-TAGS — sibling "edit document metadata after ingestion" feature)
- `OBJECT-STORAGE-NAMING-RFC.md` (storage keys are uid-based, not name-based)
- `docs/swift/design/FILESYSTEM.md` (file exchange keyed by `document_uid`)
- `docs/swift/backlog/FRONTEND-BACKLOG.md` (FRONT-09 — rename is the deferred note this RFC unblocks)
**Contract impact:** additive — one new metadata endpoint; mutates the **display name only**.

---

## 1. Decision (in one paragraph)

Let a user **rename a document** after ingestion — change its human-visible name
(e.g. `report.docx` → `DVA-Acme-2026.docx`) **without re-ingesting, re-embedding,
or moving anything in object storage**. A rename is a pure metadata edit of
`Identity.document_name`: the document's stable `document_uid` — which every
vector chunk, storage key, and file-exchange reference is keyed by — **does not
change**. So renaming is cheap, reversible, and has zero blast radius on search or
content.

---

## 2. Problem (functional)

Documents are named at ingestion from the uploaded file name
(`Identity.document_name`). Today there is **no way to change that name
afterwards**:

- Files arrive with unhelpful names (`scan_0007.pdf`, `Untitled (1).docx`) that
  the user wants to correct in place.
- The frontend already wants this — FRONTEND-BACKLOG.md (FRONT-09) carries a
  deferred *"document rename (no backend endpoint)"* note. The UI is blocked on a
  backend endpoint that does not exist.
- No RFC covers rename; this is the design decision that unblocks it.

---

## 3. What already exists (so we extend, not duplicate)

- **`Identity` already models everything rename needs**
  (`libs/fred-core/.../document_structures.py`):
  - `document_uid: str` — *"Stable unique id across the system"* (**never
    changes** on rename — this is the whole reason rename is safe).
  - `document_name: str` — *"Original file name incl. extension (display name)"* —
    **the only field a rename writes.**
  - `canonical_name`, `version` — existing machinery for the *"name (1)"* version
    suffix within a folder/tag.
  - `title`, `modified`, `last_modified_by` — already present for an edit's audit
    trail.
- **The metadata service already mutates `Identity`** — ingestion sets
  `metadata.identity.document_name = display_name` (`ingestion_service.py:110`),
  so writing this field through the service is an established path.
- **Storage and vectors are uid-keyed, not name-keyed** (OBJECT-STORAGE-NAMING-RFC,
  FILESYSTEM.md). Renaming the display name touches **neither** the object-storage
  layout **nor** the vector index.
- **DOC-TAGS (§10b) is the template** — it added "edit a document's descriptive
  metadata after ingestion, gated by the document's UPDATE access, no ReBAC on the
  field." Rename is the same shape on a different field.

So this RFC adds **one endpoint and one service method**, reusing the metadata
controller/service that DOC-TAGS already extended.

---

## 4. Core principle: rename is a display-name edit, not an identity change

**A rename must never change `document_uid`.** The uid is the join key for vector
chunks, object-storage keys, file-exchange links (LinkPart), citations, and audit
records. If rename changed the uid (or the storage key), every one of those would
dangle. Therefore:

- Rename writes **`Identity.document_name`** (and updates `modified` /
  `last_modified_by`). It does **not** touch `document_uid`, storage keys, chunks,
  or embeddings.
- The extension is part of the display name. Whether a rename may change the
  extension (`.docx` → `.pdf`) is a **decision** (§7) — default **no**, because the
  extension reflects the ingested content type, and changing it would mislead
  downstream readers without re-processing.

---

## 5. Naming, collisions, and versions

Documents within the same folder/tag use `canonical_name` + `version` to render
the *"name (1)"* suffix. A rename must stay consistent with that machinery:

- The new name is normalised the same way an ingested name is, and re-derives
  `canonical_name` from the new base name.
- **Collision policy (decision, §7):** if the target name already exists in the
  same folder/tag, do we (a) reject with a 409, or (b) auto-suffix
  `name (1)` via the existing version logic? Default recommendation: **reject (409)
  with a clear message** for a user-driven rename, so the user stays in control of
  the final name — auto-suffixing is right for bulk upload, not for an intentional
  rename.

---

## 6. API surface (as built — 2026-07-30)

One additive endpoint on the existing `MetadataController` (`features/metadata/`),
next to the sibling `retrievable`/`title` routes it was modeled on:

- **`PUT /document/metadata/{document_uid}/name`** — body `{ "name": "<new display name>" }`
  - `operation_id: rename_document`, tag `["Documents"]`.
  - Returns the updated `DocumentMetadata`.
  - Service method `rename_document(user, document_uid, new_name, modified_by)` —
    checks the document's **UPDATE access** (same gate as label edits), applies
    the extension guard (§4) and collision policy (§5), writes `document_name`,
    clears `title`, and stamps `modified` + `last_modified_by`.
- **Generated client:** regenerated in the same change (`make update-knowledge-flow-api`,
  CLAUDE.md "Backend ↔ frontend contract" rule) — no hand-written UI type.

> **Deviation from the original proposal:** this RFC originally proposed
> `PATCH /documents/{document_uid}/name` (partial update of one field). The
> as-built route is `PUT /document/metadata/{document_uid}/name` instead —
> singular `/document/metadata/...` with `PUT` is this controller's actual,
> already-established convention for every sibling single-field identity edit
> (`retrievable`, `title`), so the implementation followed that convention
> over the RFC's original text rather than introducing a second naming
> pattern into the same controller.

---

## 7. Decisions (resolved 2026-07-30, as implemented)

1. **Field scope — resolved: `document_name`, and rename clears `title`.**
   Not two independently-editable fields: the frontend's `documentDisplayName()`
   (`DocumentWorkspace.tsx`) renders `title || document_name` — if a rename left
   a stale cosmetic `title` in place, it would keep masking the new
   `document_name` forever, defeating the point of a *real* rename. So
   `rename_document` writes `document_name` and unconditionally sets
   `title = None`. The older cosmetic-only `update_document_title` endpoint
   (RFC §13.8 in KNOWLEDGE-WORKSPACE-REWORK-RFC.md, decision 9) is **not**
   removed — `title` remains a legitimate independent field for any future
   surface that only wants a display override — but the Corpus "Renommer"
   action now calls `rename_document`, not `update_document_title`.
2. **Extension — resolved: no**, as originally defaulted (§4). A rename whose
   new name has a different extension than the current one is rejected with
   400 (`InvalidMetadataRequest`).
3. **Collision policy — resolved: 409 reject**, as originally defaulted (§5).
   Checked against every sibling document sharing any of the renamed
   document's tags (`get_document_metadata_in_tag`), by exact `document_name`
   match.
4. **Access — resolved: `DocumentPermission.UPDATE`**, as originally defaulted
   — same gate as `update_document_retrievable`/label edits, no new ReBAC.
5. **Agent/MCP exposure — resolved: human-only in v1**, as originally
   defaulted. No new agent tool was added.
6. **`canonical_name`/`version` staleness — new decision, not in the original
   proposal, resolved: left untouched in v1.** These fields drive a real,
   UI-facing "draft version" system (`ingestion_service.py`'s
   `_apply_versioning`, surfaced by `DocumentVersionChip.tsx`) — at ingestion,
   `document_name == canonical_name` always holds for `version == 0`. A rename
   changes `document_name` but not `canonical_name`, so a later upload whose
   name matches the renamed document's *old* name will still collide against
   its now-stale `canonical_name` and get auto-versioned unexpectedly. Scoped
   out of v1 as a narrow, recoverable, non-corrupting edge case — fixing it
   would mean deciding whether a rename detaches the document from its
   version family entirely, which is a separate product question from "make
   the file name actually change everywhere." Revisit if this surfaces in
   practice.

---

## 8. UI surface (FRONT-09, as built)

Unblocks the deferred FRONTEND-BACKLOG.md note: in `DocumentWorkspace.tsx`'s
row "more" menu, **Renommer** opens `RenameModal` (generic, also used for
folder rename), calls `useDocumentCommands.renameDocument` →
`rename_document`, and the hook's own `refresh()` reloads the active
folder/page (the same refresh path already used after upload/delete/reprocess)
— no bespoke local-state patch was needed, unlike the `retrievable` toggle.

### 8.1 Vector-index and content-store propagation (beyond the original proposal)

The original decision (§1) says storage/vectors are uid-keyed so renaming
"touches neither the object-storage layout nor the vector index" — true for
the **embedding and chunk text**, which never change. It understated one
thing: each chunk also carries `document_name` as a flat **metadata** field
(`vectorization_utils.py`), independent of the embedding itself, and that
field does go stale on a rename unless explicitly patched. As built:

- `BaseVectorStore.set_document_name(*, document_uid, document_name)` — a new
  optional-capability method (same shape as the pre-existing
  `set_document_retrievable`), implemented for all 5 configured backends
  (OpenSearch, Chroma, InMemory, pgvector, ClickHouse). Called best-effort
  from `rename_document` (never fails the request — the Postgres write is
  authoritative) only when the document has reached `ProcessingStage.VECTORIZED`.
- **Content-store filename fix**, unrelated to vectors but in the same "old
  name shouldn't survive a rename" spirit: `ContentService.get_file_metadata`
  used to resolve the file name from the stored blob's own name on disk/MinIO
  (never updated by a rename) instead of the DB record — this backs the
  in-app preview/stream endpoint's `Content-Disposition` header. Fixed to read
  the DB's `identity.document_name`, matching what the download endpoint
  already did correctly.

---

## 9. Acceptance criteria

- A user can rename a document they can edit; the new name shows everywhere the
  document is listed, **with no re-ingestion and no re-embedding**.
- `document_uid`, object-storage keys, embeddings, and existing
  citations/links are **unchanged** after a rename (verified by test) —
  vector chunk **metadata**'s `document_name` field is the one exception,
  updated best-effort per §8.1.
- Renaming respects the collision policy (§5) and updates the audit fields
  (`modified`, `last_modified_by`).
- The generated frontend API client is regenerated in the same change; no
  hand-written rename type.

---

## 10. Out of scope

- **Moving** a document between folders/tags (a scope/permission act — separate
  work; see FRONT-09 *"move deferred"*).
- Changing a document's content type / re-processing (extension change, §4).
- Bulk rename / find-and-replace across many documents.
- Renaming **labels** (that is DOC-TAGS' future *definitions* table, not this RFC).

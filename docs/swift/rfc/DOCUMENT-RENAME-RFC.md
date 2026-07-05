# RFC: Knowledge Flow — Rename a Document

**Status:** Proposed
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

## 6. API surface

One additive endpoint on the existing `MetadataController` (`features/metadata/`),
mirroring the DOC-TAGS routes:

- **`PATCH /documents/{document_uid}/name`** — body `{ "name": "<new display name>" }`
  - `operation_id: rename_document`, tag `["Documents"]`.
  - Returns the updated `DocumentMetadata` (or at least the new `Identity`).
  - Service method `rename_document(user, document_uid, new_name, modified_by)` —
    checks the document's **UPDATE access** (same gate as label edits), normalises
    the name, applies the collision policy (§5), writes `document_name` +
    `modified` + `last_modified_by`.
- **Generated client:** regenerate the control-plane / knowledge-flow API client
  in the same change (CLAUDE.md "Backend ↔ frontend contract" rule) — no
  hand-written UI type.

> Method choice: `PATCH` (partial update of one field) over `PUT` (full
> replacement). Open to `PUT /documents/{uid}/identity` if the team prefers a
> single identity-edit endpoint that also covers `title` — see §7.

---

## 7. Decisions to settle

1. **Field scope** — rename writes `document_name` only, or also `title`
   (human-friendly UI title)? Should we instead expose one *"edit identity"*
   endpoint covering `document_name` + `title` together?
2. **Extension** — may a rename change the file extension? (Default **no**, §4.)
3. **Collision policy** — 409 reject vs auto-suffix `name (1)` (§5). Default
   **409 reject**.
4. **Access** — confirm rename is gated by the document's existing **UPDATE
   access**, with **no** ReBAC/permission-tag involvement (mirrors DOC-TAGS).
5. **Agent/MCP exposure** — is rename also an agent tool, or human-only? Default
   **human-only** in v1 (rename is a deliberate, low-frequency act; an agent
   renaming documents at scale is hard to undo). Revisit per the DOC-TAGS §12
   pattern if a use case appears.

---

## 8. UI surface (FRONT-09)

Unblocks the deferred FRONTEND-BACKLOG.md note: in the Knowledge Workspace
resource browser / detail drawer, a **Rename** action on a document opens an
inline edit, calls `PATCH /documents/{uid}/name`, and refreshes the active
folder/page (the same refresh path already used after upload/delete/reprocess).

---

## 9. Acceptance criteria

- A user can rename a document they can edit; the new name shows everywhere the
  document is listed, **with no re-ingestion and no re-embedding**.
- `document_uid`, object-storage keys, vector chunks, and existing
  citations/links are **unchanged** after a rename (verified by test).
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

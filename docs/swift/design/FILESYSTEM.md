# Fred file storage paths

## Current scope

The Resources page shows the searchable team corpus. Corpus documents and conversation attachments use their existing document APIs; the `/corpus` virtual view is read-only. The earlier team-shared Files UI and agent-files browser are retired.

Knowledge Flow still serves technical agent paths needed for capability assets and generated outputs:

| Path | Current use |
| --- | --- |
| `/teams/{team}/agents/{agent_instance_id}/config/...` | Capability configuration assets, including the PPT Filler template |
| `/teams/{team}/agents/{agent_instance_id}/users/{uid}/outputs/...` | Generated PPT Filler files available through chat download links |
| `/corpus/...` | Read-only virtual view of indexed documents |

The runtime builds the agent output path from the verified team, agent instance and user context. `RuntimeServices.workspace_fs.write` uploads the output and returns the download URL; `RuntimeServices.agent_assets` loads and saves configured templates. Knowledge Flow retains `/fs/upload`, `/fs/download` and `/fs/delete` for these technical paths. The retired `/teams/{team}/shared/...` area is rejected before storage access.

Deep's conversation filesystem, writable documents, Wiki, corpus documents and conversation attachments have separate storage contracts; this document does not redefine them.

### Business labels vs. scope tags

A document can carry two structurally unrelated kinds of "tag" — never merged:

| | Fred **tag** (scope) | **Business label** (descriptive) |
| --- | --- | --- |
| Answers | who may see the document | what the document is |
| Backed by | the permission tag system (ReBAC, libraries) | `DocumentMetadata.labels: list[str]` |
| Changing it | a security event | a harmless metadata edit |
| Hierarchy | hierarchical (folders/libraries) | flat, many-to-many |

**Persistence (2026-08-11).** `MetadataService` is the sole functional owner
of label reads and mutations. The persisted source of truth is a relational
assignment table, `document_labels` (`document_uid` FK → `metadata`,
`ON DELETE CASCADE`; `label` text; composite primary key
`(document_uid, label)` — the primary key is what makes an add idempotent by
constraint, not by a precomputed Python check). `DocumentMetadata.labels:
list[str]` is the public Pydantic/API projection: hydrated from
`document_labels` on every read path (batched, no N+1), never stored
verbatim — `PostgresDocumentMetadataStore._to_dict` excludes `labels` from
every `doc` JSONB write, so a generic metadata save (rename, retrievable
toggle, ingestion, or a stale in-memory snapshot held by a long-running
task) can never add, remove, or otherwise touch a label —
`mutate_document_labels` is the only method that writes to `document_labels`,
full stop. There is exactly one persisted source of truth; the physical
(table) and API (`list[str]`) shapes are allowed to differ. Nothing is
denormalized into the vector index — a label is resolved to its document set
at query time, then that set is used wherever a document-scoped operation
needs a target (e.g. the similarity search's document targeting,
`DESIGN.md §4`), never by baking the label into indexed chunk metadata,
which would go stale between reindexes.

Why a table, not a `jsonb_set` merge-patch on the old `doc.labels` array: a
targeted JSONB merge (the idiom `bulk_mark_vector_done` already uses for
`processing.stages`) would fix the raw lost-update race, but a JSONB array
has no database-enforced uniqueness — idempotency would still be a
precomputed Python/SQL check that could itself race. A composite primary key
on `(document_uid, label)` makes a duplicate `INSERT` rejected by the
constraint itself, and turns "documents by label"/"distinct labels" into a
plain indexed-equality query instead of a full authorized-corpus scan
filtered in Python.

**Labels are an unordered set, represented alphabetically.** No order/rank
column exists or is planned — every read path (`get_labels_for_document`,
`get_labels_for_documents`, `get_distinct_labels`, a `mutate_document_labels`
response) returns labels sorted, not in add/first-seen order. Audited: no
backend, SDK, runtime, or frontend consumer depends on insertion order (the
frontend renders labels as an unordered chip set; the `document_label_search`
capability's `list_documents_by_label` tool, below, treats `labels` as a
plain membership set). This is a compatibility
change from the pre-table JSONB array, which happened to preserve
first-insertion order as an accidental property of appending to a Python
list — not a documented guarantee anything relied on.

**Audit trail.** A label add/remove still updates
`identity.modified`/`identity.last_modified_by`, in the same transaction as
the `document_labels` row insert/delete — a second small, explicitly-named
store method (`touch_label_mutation_audit_fields`) does a targeted
`identity`-only JSONB merge-patch, the same idiom as `bulk_mark_vector_done`,
never a read-modify-write of the whole `doc` blob. A genuinely empty PATCH
(nothing to add/remove after normalization) is a no-op that leaves the audit
trail untouched; a requested add/remove touches it even when the resulting
label-set change is itself a no-op (label already present/absent) — matching
the pre-relational-table behavior.

**Transport.** Canonical mutation: `PATCH /documents/{document_uid}/labels`
with a JSON body (`{"add": [...], "remove": [...]}`, `LabelMutationRequest`),
returning the full canonical stored set — any Unicode text, no character
restriction, since nothing rides in a URL path segment. The original
`POST`/`DELETE /documents/{uid}/labels/{label}` routes (label as a raw path
segment) are kept, marked `deprecated` in OpenAPI, for existing consumers
that already send labels they could transport; both are thin adapters onto
the same `MetadataService.mutate_document_labels`, not a second mutation
implementation. Removal condition: once no known consumer calls them
directly (the frontend already migrated to the PATCH route).

Canonical resolution: `GET /documents/by-label` (label as a query parameter,
`operation_id=resolve_documents_by_label`) — the read-side symmetric
counterpart to the PATCH body transport, since a URL path segment cannot
reliably carry `/`, `#`, `?`, a literal `%`, or arbitrary Unicode either.
`GET /documents/by-label/{label}` (path segment) is kept unchanged for
existing consumers; both resolve through the same
`MetadataService.get_documents_with_label`, not a second lookup
implementation. `GET /documents/labels` (distinct-label vocabulary) is
unchanged. Assigning/removing a label only checks the document's UPDATE
access; resolving/listing only ever surfaces the caller's readable
documents. Neither checks a ReBAC permission on the label itself — a label
carries no access semantics, and never becomes a ReBAC object.

**Agent exposure.** Label search reaches agents through one place only: the
`document_label_search` capability's `list_documents_by_label` tool
(`libs/capabilities/fred-capability-documents/`, `ADMIN_GATED`, paginated,
backed by `MetadataService.get_documents_with_label`). It is deliberately not
wired into `CorpusTreeService`/`list_document_tree` (`DEFAULT_ON`, no label
filtering — see `RUNTIME-EXECUTION-CONTRACT.md §8.47`) or into `/fs`: a team
opts an agent into label search explicitly, the same way as any other
`ADMIN_GATED` capability, instead of every `document_access` agent gaining a
new behavior for free.

Not built, and not planned here: a managed label-*definitions* table
(rename/describe a label globally, team-scoped vocabularies). Whether a label
is ultimately a bounded technical token (`DAT`) or free descriptive text is an
open product question this work does not settle — `document_labels` records
only the current assignment of an opaque text value to a document.

## Source map

| Concern | Source |
| --- | --- |
| Team-path authorization | `knowledge_flow_backend/features/filesystem/scoped_area_filesystem.py` |
| Binary upload/download | `knowledge_flow_backend/features/filesystem/mcp_fs_controller.py` |
| PPT output path mapping | `fred_runtime/integrations/v2_runtime/adapters.py` |
| PPT Filler behavior | `fred_capability_ppt_filler/fill.py` |
| Corpus UI | `apps/frontend/src/rework/components/pages/TeamResourcesPage/DocumentWorkspace/` |

# fred-capability-document-access

Fred agent capability giving an agent scoped access to the Knowledge Flow
document corpus: `search_documents` (semantic/RAG search)
and `list_document_tree` (folder and document listing with names, uids, MIME and arrival time).

It is the reference implementation a capability author copies: real tools wired
to platform services through typed SDK ports, static config-field scoping, and
one computed chat-turn narrowing control — with no HTTP stack, no access token
and no per-turn binding anywhere in the capability.

## Scoping

Three levels narrow each other, never widen:

    turn_option  ⊆  capability_config  ⊆  session_binding

The capability intersects configuration and turn selections with `DocumentScope`.
The runtime adapters intersect that result with the admitted turn context.
Model arguments carry only search or navigation parameters; scope and identity
remain outside the tool schema. Within each selection, folder contents and
explicit documents form a union; separate selections intersect.

## On Weaver

Version 0.4.0 exposes `list_document_tree(folder_id=None, max_chars=20000)`.
The runtime sends the admitted context to KF's corpus-only `GET /documents/tree`,
intersecting capability and turn selections, with attachments excluded.
The SDK port returns typed spaces, folders, documents and a truncation flag.
The capability renders space grouping lines and folder JSON records (`folder`,
`folder_id`), then document JSON leaves (`uid`, `name`, `mime`, `added_to_kb`).
Each document has at most one folder; root documents are included.

The character budget is clamped to 500..60000, including the truncation notice.
Deepest branches are pruned first. KF's 1000-record request limit can also make
the listing incomplete. An incomplete tree establishes nothing about omitted
items: narrow `folder_id` or use `search_documents`. IDs remain tool arguments,
never user-facing citations. `general_only` returns an empty corpus tree.

## Chat controls

`chat_controls(config)` emits up to four stock composer widgets behind their
config toggles: `attach_files`, `document_scope`, `search_policy`, `rag_scope`.
Their params are SDK models (`fred_sdk.contracts.models`) and carry the widget's
*default* only — the value the user picks travels on `RuntimeContext`.

## Tests

`make test` runs offline: the ports are faked, no service is contacted. The dev
group depends on `fred-runtime` for `CapabilityRegistry` (entry-point discovery)
and `build_capability_context`; the capability itself depends only on
`fred-core` and `fred-sdk`.

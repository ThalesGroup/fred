# fred-capability-document-access

Fred agent capability giving an agent scoped access to the Knowledge Flow
document corpus: `search_documents_using_vectorization` (semantic/RAG search)
and `list_document_tree` (folder and document listing, names and uids only).

It is the reference implementation a capability author copies: real tools wired
to platform services through typed SDK ports, static config-field scoping, and
one computed chat-turn narrowing control — with no HTTP stack, no access token
and no per-turn binding anywhere in the capability.

## Scoping

Three levels narrow each other, never widen:

    turn_option  ⊆  capability_config  ⊆  session_binding

The capability enforces the first (`narrow_scope_ids`, in `capability.py`); the
runtime's `DocumentSearchAdapter` enforces the second. The tool signature the
model sees carries only `question` / `top_k` — scope and identity travel in the
middleware closure and can never be widened by the model.

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

# fred-capability-document-access

Document Access supplies `search_documents_using_vectorization` through the
existing `RuntimeServices.document_search` port. Its tool signature, JSON hits,
`DocumentSearchResult`, tool artifacts and citable-source selection are unchanged.
`list_document_tree` is registered only when a tree port exists and team documents
are enabled. The Weaver pod does not supply that port in this increment.

## Weaver corpus path

The Control Plane resolves identity, space and admitted agent configuration once
per turn. `DocumentSearchAdapter` checks that its private context matches this
live authority and takes the space from `current_turn().binding.space.id`.
It never infers authority from tool arguments or infrastructure credentials and
performs no per-tool HTTP/OpenFGA authorization refresh.

The capability library's `CorpusSearch` owns the document operations:

1. `fred_core.documents.access.resolve_scope` reads the canonical space and its
   ancestors using the pod's existing PostgreSQL pool.
2. The connection is released before query embedding and OpenSearch search.
   `get_embeddings` uses the ingestion model configuration, independently of chat.
   `build_search` retains semantic, strict and hybrid policies; strict skips embedding.
3. `read_response` extracts candidates. A short SQL checkout runs
   `verify_candidates`: live document and space, correct placement, retrievable
   with no pending inclusion, and chunk in the published generation's manifest.
   Index metadata alone never grants access.
4. `repair_table_hits` retains table completion, ordering and header deduplication.
   Completion reads at most 40 chunks of one already-verified document directly
   from OpenSearch. Additional chunks pass the same SQL checks. A read reaching
   the cap leaves the original hits; the cap is checked before SQL filtering.
5. The existing tool selects citable sources from the verified, repaired hits.

Local turn-stop checks surround external operations and precede result exposure.
Technical failures, timeouts and partial OpenSearch responses fail the tool;
there is no Knowledge Flow fallback. Table-read errors propagate on this path.
The shared table helper retains its previous best-effort behavior for its other
runtime consumers, through the existing `fred_runtime.common.table_hits` import.

The capability still narrows configured/turn selections before calling the port.
This Weaver increment supports corpus only (`attachments: false`). Nonempty
library-tag or document selections, including private runtime selections, are
explicitly refused; they are never interpreted as unrestricted corpus. Empty
selections match nothing. General-only mode or a disabled corpus returns no hits
without accessing storage. No composer or user setting is added here.

## Deployment connection

No deployment is changed or provisioned by this increment. Supply these two
additional pod parameters, copying the active ingestion configuration exactly:

```yaml
ai:
  embedding_model:
    provider: openai
    name: mistral-embed
    settings:
      base_url: https://api.mistral.ai/v1
      check_embedding_ctx_length: false
  document_vector_store:
    type: opensearch
    index: document-vectors
```

These are the current k3d source values: the embedding alias in
`fred-deployment-factory/k3d-apps/fred/values.yaml` and the manager ingestion index
in `deploy/k3d/values.yaml.gotmpl`. The older Swift vector index in the factory
file is not the Weaver corpus. Neither model nor index is hardcoded in search.
`embedding_model` reuses `ModelConfiguration`; `document_vector_store` reuses
`OpenSearchIndexConfig`. They identify the vector space and its index, which the
chat model cannot supply. Both absent leaves the corpus port explicitly
unavailable; partial configuration fails startup.

Reuse `storage.opensearch` for endpoint, credentials and TLS configuration, and
`storage.postgres` for the existing Weaver database pool. The pod needs SELECT
on `space`, `document` and `document_processing`, OpenSearch search access to the
configured index and hybrid pipeline, and network/credential access to the
embedding provider. With the OpenAI-compatible configuration above, the existing
factory reads the provider credential from `OPENAI_API_KEY`. Ingestion must have
created the index and `hybrid-search-pipeline`; the reader creates neither.

The corpus clients are created once in `PodApplicationContext` and closed by
its lifespan shutdown. Embeddings reuse fred-core's shared HTTP clients; those
are also closed at pod shutdown. `ai.timeout.read` bounds each embedding and
OpenSearch call even when the shared model HTTP stack was initialized earlier.
There is no new retry, cache, SQL pool or connection held across remote work.

The runtime explicitly depends on this library; the library's production
dependencies remain fred-core and fred-sdk. Its runtime dependency used by tests
is development-only. Capability discovery and assembly continue to use the same
entry point and SDK port.

This is implemented wiring, not a validated Weaver user journey. Deployment,
functional validation and test execution remain outstanding. The frontend,
execution preparation, other document tools and their Knowledge Flow clients
are outside this increment.

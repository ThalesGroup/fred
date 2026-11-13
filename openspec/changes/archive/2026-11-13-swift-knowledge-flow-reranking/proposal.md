# Proposal

## Why

Swift's normal document search returns retrieved hits without reranking, although Knowledge Flow already has a local CrossEncoder for targeted similarity search. The Weaver RAG reranking behavior needs a Swift adaptation in which remote model configuration remains owned by Knowledge Flow, alongside `chat_model` and `vision_model`.

## What Changes

- Add an optional `reranker_model` to Knowledge Flow deployment configuration, using the existing model configuration shape. Without it, use the CrossEncoder supplied by the Knowledge Flow image.
- Rerank authorized candidates inside the normal RAG search when requested. Keep the retrieval scope and result count bounded and preserve document and attachment authorization.
- Add an advanced `document_access` reranking switch for agents, enabled by default for new and existing configurations that omit it.
- Use one Knowledge Flow reranking implementation for normal search, targeted similarity search and the existing direct rerank endpoint. Keep the direct endpoint available for existing callers; do not register a separate agent reranking tool.
- Update the typed search request path, deployment examples, generated schema and documentation. Add focused tests for configuration, remote/local selection, failures, scope and default behavior.

## Capabilities

### New Capabilities

- `document-search-reranking`: Operator model selection and bounded, authorized reranking of document search results, including the agent's default-on control.

### Modified Capabilities

None. Existing model routing covers agent pod chat profiles rather than Knowledge Flow deployment models. Existing document source and capability pack requirements retain their scope rules.

## Impact

- Knowledge Flow configuration, vector search service and request API.
- `document_access` capability, SDK document search port, runtime adapter and Knowledge Flow HTTP client.
- Agent settings translations and Knowledge Flow deployment documentation.
- Existing `/vector/rerank` and `/vector/similarity-search` callers remain supported.
- Swift backport tracking: [#3536](https://github.com/ThalesGroup/fred/issues/3536); source behavior: [Weaver PR #3535](https://github.com/ThalesGroup/fred/pull/3535).

## Why

Some remote rerankers expose positional scores through a model `:predict` endpoint rather than indexed results through `/rerank`. Fred currently supports only the latter, so the supplied Thales endpoint cannot be selected through deployment configuration.

## What Changes

- Support two explicit remote reranker providers: existing `rerank` for indexed results and new `predict` for positional scores. Keep the local CrossEncoder behavior.
- Make `predict` use the configured model name in `/models/<name>:predict`, send query and document strings, authenticate with the selected reranker key in the `apikey` header, and map positional `predictions` scores back to input documents.
- Reject malformed scores, failed requests, and missing credentials with the existing reranker error behavior.
- After a Fred release containing the adapter is available, configure both local, untracked PRISM int and prod values for model `bge-reranker-v2-m3` at `https://api.corp.thales/corp/genai/reranker/v1` using their existing `OPENAI_API_KEY`. Keep those values out of Git commits and pushes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `document-search-reranking`: Support a configurable model `:predict` request and positional score response as an additional remote reranker protocol.

## Impact

- Knowledge Flow reranker configuration, HTTP adapter, schema, focused tests, and operator configuration guidance in the Fred repository.
- Local `values-prism-int.yaml` and `values-prism-prod.yaml` in `kube-deployment-factory`, including the Knowledge Flow API and worker configuration. They remain untracked and are never pushed.
- Deployment requires a Fred image and chart version newer than v3.12.0 containing the adapter, plus a successful endpoint and credential check before enabling agent reranking.

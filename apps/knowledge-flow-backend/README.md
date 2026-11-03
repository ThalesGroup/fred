# Knowledge Flow API

Knowledge Flow API serves authorized search, published Markdown, tabular REST/MCP queries, summaries and exhaustive LLM extraction from published text. Control Plane owns access decisions and publication; indexes remain projections.

Ingestion runs in the separate [Knowledge Flow worker](../knowledge-flow-worker/README.md). Both applications use [fred-knowledge](../../libs/fred-knowledge/README.md) for artifact integrity, tabular contracts, index adapters and text primitives. Neither application depends on the other.

## Local development

From this directory:

```sh
make dev
cp config/.env.template config/.env
# Supply credentials through your local environment file.
make run
```

The API retains `/knowledge-flow/v2`, its JWT/delegation boundary, and tabular MCP under `/knowledge-flow/v2/mcp/tabular`. PostgreSQL publication/access reads use `cp_read`; the configured search projection is OpenSearch or pgvector.

`POST /knowledge-flow/v2/documents/search` also serves targeted document similarity.
Optional `rerank` retrieves `min(top_k * 5, 100)` candidates, applies publication
and scope checks, then uses the existing CrossEncoder to keep `top_k` hits.
Optional `min_score` filters the original retrieval scores after reranking; the
reranker does not replace those scores. With both options omitted, ordinary
search is unchanged. Similarity callers select corpus documents through the
trusted document-context header and exclude conversation attachments.

## Configuration

`CONFIG_FILE` and `ENV_FILE` retain their existing meaning. See [configuration](config/README.md).

- `published_artifacts`: S3 reader endpoint, bucket and environment-variable credential references.
- `storage`: PostgreSQL, optional OpenSearch, vector projection, logs and bounded tabular query settings.
- `embedding_model`: query embeddings, matching the worker's indexing model.
- `crossencoder_model`: the retained local reranker. Its default model is baked into the production image.
- `chat_model` and `text_splitter`: utility LLM and independent splitting parameters for summary/exhaustive extraction.
- `use_gpu`: explicit API device policy, derived from the former effective profile settings in each shipped configuration.

There is no scheduler, processing profile or processor registry in the API configuration. PyMuPDF, OCR, Office and audio extraction options belong to the worker.

## Build and validation

`make docker-build` builds `knowledge-flow-backend` with production dependencies only. The image installs no ingestion converters or ingestion-model caches. Torch and sentence-transformers remain necessary for reranking; no image-size or memory saving has been measured.

Developer validation targets: `make code-quality`, `make test`, `make generate-config-schema`, `make check-config-schema-drift`. Run `python ../../scripts/check_knowledge_api.py --development` in this application's environment to inspect its installed dependency boundary. Run the same script without `--development` inside the built image to check executables too.

The separation has not yet been validated through isolated installation, image builds or the end-to-end ingestion/search journey. The [k3d guide](../../deploy/k3d/README.md) describes the deployment prerequisites.

Apache 2.0 - Copyright Thales.

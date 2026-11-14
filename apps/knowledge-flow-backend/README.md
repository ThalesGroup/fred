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
and scope checks, then uses the organization's selected reranker or the local
CrossEncoder to keep `top_k` hits. A selected remote model is called through its
approved `/rerank` endpoint with an indexed-results response. If that model is
unavailable, search fails explicitly instead of silently switching models.
Optional `min_score` filters the original retrieval scores after reranking; the
reranker does not replace those scores. With both options omitted, ordinary
search is unchanged. Similarity callers select corpus documents through the
trusted document-context header and exclude conversation attachments.
The document-access agent capability leaves reranking off by default and lets its
advanced settings enable it. Knowledge Flow ranks only visible hits in the
same search request.

## Configuration

`CONFIG_FILE` and `ENV_FILE` retain their existing meaning. See [configuration](config/README.md).

- `published_artifacts`: S3 reader endpoint, bucket and environment-variable credential references.
- `storage`: PostgreSQL, optional OpenSearch, vector projection, logs and bounded tabular query settings.
- `inference_credentials`: the model destinations this workload attests and the variables holding their keys. The Control Plane decides the models: search embeds the question with the organization's locked corpus model, in its index `document-vectors-<organization id>`; summary and exhaustive extraction use its default chat model. Without them, search returns nothing and document tools answer `409`.
- `crossencoder_model`: the local fallback when the organization has no reranker choice. Its default model is baked into the production image.
- `text_splitter`: independent splitting parameters for summary and exhaustive extraction.
- `use_gpu`: explicit API device policy, derived from the former effective profile settings in each shipped configuration.

There is no scheduler, processing profile or processor registry in the API configuration. PyMuPDF, OCR, Office and audio extraction options belong to the worker.

## Build and validation

`make docker-build` builds `knowledge-flow-backend` with production dependencies only. The image installs no ingestion converters or ingestion-model caches. Torch and sentence-transformers remain necessary for reranking; no image-size or memory saving has been measured.

Developer validation targets: `make code-quality`, `make test`, `make generate-config-schema`, `make check-config-schema-drift`. Run `python ../../scripts/check_knowledge_api.py --development` in this application's environment to inspect its installed dependency boundary. Run the same script without `--development` inside the built image to check executables too.

The separation has not yet been validated through isolated installation, image builds or the end-to-end ingestion/search journey. The [k3d guide](../../deploy/k3d/README.md) describes the deployment prerequisites.

Apache 2.0 - Copyright Thales.

`GET /documents/tree` lists the bounded visible corpus using the same delegated context as search; attachments are excluded and truncation is explicit.
Tree SQL cases run with `make test-one TEST=tests/features/test_document_tree.py` and `KF_TREE_TEST_POSTGRES` pointing to an empty disposable database (async SQLAlchemy PostgreSQL URL); fixtures roll back all writes.

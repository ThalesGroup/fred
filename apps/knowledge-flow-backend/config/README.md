# API configuration

Set `CONFIG_FILE` to an API YAML and `ENV_FILE` to your local credentials file. Environment variables override `.env` values. Never copy worker configuration into the API.

The generated schema is `schema/configuration.schema.json`. Generate it with `make generate-config-schema`; validate drift with `make check-config-schema-drift` and shipped YAML with `make check-config-files`.

The API requires `app`, `security` and `storage`, and lists in `inference_credentials` the model destinations it attests; the Control Plane decides the models. Configure `control_plane_url` and workload delegation for scope authorization, and `published_artifacts` for verified S3 reads. Configure `use_gpu` and `text_splitter` explicitly; existing supported configurations preserve their previous effective CPU/GPU policy and splitting parameters.

Search uses `storage.vector_store`. The API's index base name and artifact bucket must match the worker's published output; each organization's corpus index and embedding model come from the Control Plane. Credentials and permissions remain separately configured. This split does not establish separate PostgreSQL API/worker roles.

For processing profiles, queues, output credentials and optional PyMuPDF, see the [worker configuration](../../knowledge-flow-worker/config/README.md).

## Tabular query results

`storage.tabular_store.query.default_max_rows` defaults to 500. A query may omit
`max_rows` to use that default, send JSON `null` to disable the row limit, or set
any positive row limit. `max_output_chars` (default 50,000) always bounds the JSON
rows array and keeps complete rows; metadata and explanation are additional.
The retired configuration key `query.max_rows` is rejected. SQL LIMIT, memory,
execution-time, concurrency and dataset guards remain effective. `truncated`
reports actual omitted rows; reaching the row limit alone does not imply truncation.

## Tabular HTTPS reads

For Parquet artifacts served by an internal HTTPS object store, mount a readable
CA bundle in the API container and set `storage.tabular_store.query.duckdb_ca_cert_file`
to its path, with `duckdb_enable_server_cert_verification: true` in the same block.
These options configure DuckDB `httpfs` only; they do not change URL signing or
the Python S3 client. Omitted or `null` values retain the installed DuckDB defaults.
See the [Helm example](../../../deploy/charts/fred/README.md) for the volume mount.

## Document models and reranking

Chat, vision and embeddings use the Control Plane's admitted model connection.
Each `inference_credentials` entry binds an approved destination to its own
`api_key_env`; use different entries and variables for endpoints with different
keys. `DocumentModels` passes each credential directly to the shared factory,
without changing the process environment. The worker uses the same mechanism
for admitted embedding and vision stages. The retired Swift `chat_model`,
`vision_model`, `embedding_model` and remote OCR configuration are not supported.

Reranking is an optional deployment-level service, applied only after Weaver has
verified the selected passages' publication and visibility. The document access
capability exposes an advanced `rerank` switch, off by default; similarity keeps
its existing default. Omit `reranker_model` (or set it to `null`) to keep the
bundled local CrossEncoder. To use the remote indexed-results protocol:

```yaml
reranker_model:
  provider: rerank
  name: your-reranker
  settings:
    base_url: https://models.example/v1
```

The API posts to `/rerank` under that base URL and requires results containing
`index` and `relevance_score`. Supply `KNOWLEDGE_FLOW_RERANKER_API_KEY` in the API
pod environment; a blank value falls back to `OPENAI_API_KEY`. The chart exposes
`applications.knowledge-flow-backend.configuration.reranker_model` and the
corresponding `dotenv` key. Neither the worker nor browser receives this key.
A missing credential prevents startup when a remote model is configured.
Timeouts or invalid responses produce `503 reranker_unavailable`, without a
silent fallback. Restart the API after changing its environment.

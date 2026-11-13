# API configuration

Set `CONFIG_FILE` to an API YAML and `ENV_FILE` to your local credentials file. Environment variables override `.env` values. Never copy worker configuration into the API.

The generated schema is `schema/configuration.schema.json`. Generate it with `make generate-config-schema`; validate drift with `make check-config-schema-drift` and shipped YAML with `make check-config-files`.

The API requires `app`, `security` and `storage`, and lists in `inference_credentials` the model destinations it attests; the Control Plane decides the models. Configure `control_plane_url` and workload delegation for scope authorization, and `published_artifacts` for verified S3 reads. Configure `use_gpu` and `text_splitter` explicitly; existing supported configurations preserve their previous effective CPU/GPU policy and splitting parameters.

Search uses `storage.vector_store`. The API's index base name and artifact bucket must match the worker's published output; each organization's corpus index and embedding model come from the Control Plane. Credentials and permissions remain separately configured. This split does not establish separate PostgreSQL API/worker roles.

For processing profiles, queues, output credentials and optional PyMuPDF, see the [worker configuration](../../knowledge-flow-worker/config/README.md).

## Tabular HTTPS reads

For Parquet artifacts served by an internal HTTPS object store, mount a readable
CA bundle in the API container and set `storage.tabular_store.query.duckdb_ca_cert_file`
to its path, with `duckdb_enable_server_cert_verification: true` in the same block.
These options configure DuckDB `httpfs` only; they do not change URL signing or
the Python S3 client. Omitted or `null` values retain the installed DuckDB defaults.
See the [Helm example](../../../deploy/charts/fred/README.md) for the volume mount.

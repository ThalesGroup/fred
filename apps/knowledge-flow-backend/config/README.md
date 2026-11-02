# API configuration

Set `CONFIG_FILE` to an API YAML and `ENV_FILE` to your local credentials file. Environment variables override `.env` values. Never copy worker configuration into the API.

The generated schema is `schema/configuration.schema.json`. Generate it with `make generate-config-schema`; validate drift with `make check-config-schema-drift` and shipped YAML with `make check-config-files`.

The API requires `app`, `security`, `chat_model`, `embedding_model` and `storage`. Configure `control_plane_url` and workload delegation for scope authorization, and `published_artifacts` for verified S3 reads. Configure `use_gpu` and `text_splitter` explicitly; existing supported configurations preserve their previous effective CPU/GPU policy and splitting parameters.

Search uses `storage.vector_store`. The API's index/collection, embedding model and artifact bucket must match the worker's published output. Credentials and permissions remain separately configured. This split does not establish separate PostgreSQL API/worker roles.

For processing profiles, queues, output credentials and optional PyMuPDF, see the [worker configuration](../../knowledge-flow-worker/config/README.md).

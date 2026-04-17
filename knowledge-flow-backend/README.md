# Knowledge Flow Backend

**Knowledge Flow** is a modular FastAPI backend that extracts and structures knowledge from documents or tabular data
for intelligent applications.

It is used by the open-source [Fred](https://github.com/ThalesGroup/fred) multi-agent assistant, exposing both REST and
MCP (Model Composition and Prompting) endpoints to serve structured knowledge to agents.

---

## What It Does

Knowledge Flow provides two primary services:

1. **Document Ingestion**  
   Converts unstructured files (PDF, DOCX, PPTX, etc.) into clean Markdown and metadata, splits the content into chunks,
   and vectorizes them using an embedding model. The results can be stored locally or in a vector store for semantic
   search (e.g., RAG pipelines).

2. **Structured Data Ingestion**  
   Processes CSV files into dataset-scoped Parquet artifacts stored in the shared `content_storage` object area.
   The primary ingestion path inspects delimiter and encoding once, converts CSV to Parquet directly with DuckDB,
   then derives row counts and column schema from the generated Parquet artifact instead of materializing a full
   pandas DataFrame. These datasets are then exposed through read-only REST and MCP endpoints and queried on demand
   with DuckDB, instead of being materialized into one global SQL database.

Knowledge Flow supports one tabular data runtime that can be queried with SQL:

| Runtime | Main config | Backing storage | Status |
|---------|-------------|-----------------|--------|
| Dataset-centric runtime | `content_storage` + `storage.tabular_store` | One Parquet artifact per document + DuckDB at query time | Recommended |

All processing pipelines are defined declaratively in `config/configuration.yaml`.

---

## Developer Docs

To learn how to:

- Add custom input or output processors
- Create new storage backends
- Extend the ingestion and search logic

→ See the [**Developer Guide**](docs/DEVELOPER_GUIDE.md)

For shared startup config and policy conventions across all Fred backends, read:

- [`docs/CONFIGURATION_AND_POLICY_CONVENTIONS.md`](../docs/CONFIGURATION_AND_POLICY_CONVENTIONS.md)

Key point: Knowledge Flow uses the same `ENV_FILE` + `CONFIG_FILE` contract as Agentic and Control Plane.

---

## Quick Start

The default configuration is developer-friendly and only uses local stores. See the
[configuration page](./config/README.md) when you want another setup.

### Storage credentials

- **Core storage (`storage.postgres`)**: used by tags, metadata, resources, pgvector, etc.  
  - User/host/db come from `storage.postgres` in `configuration*.yaml`.  
  - Password comes from `FRED_POSTGRES_PASSWORD` (or an explicit `password:` in the YAML).
- **Tabular artifacts (`storage.tabular_store` + `content_storage`)**: CSV ingestion writes Parquet artifacts into the shared content store object area.  
  - Runtime query limits come from `storage.tabular_store` in `configuration*.yaml`.  
  - The CSV-to-Parquet path is DuckDB-native and avoids loading the full dataset into a pandas DataFrame.  
  - Tabular runtime URLs now use `storage.tabular_store.query.internal_presigned_ttl_seconds` for backend-internal reads.  
  - Object-storage credentials come from `content_storage` when using MinIO/S3-compatible backends.  
  - This is the recommended mode for new deployments.
  - If `storage.tabular_store` is omitted, this runtime is enabled with the built-in defaults.

Tip: for S3-compatible deployments, keep `content_storage.endpoint` on the internal MinIO/S3 address used by backend
pods and workers, reserve `public_endpoint` for browser-facing links, and use `storage.tabular_store` only for
query/runtime bounds.

```bash
git clone https://github.com/ThalesGroup/knowledge-flow.git
cd knowledge-flow
make dev
cp config/.env.template config/.env
# Edit .env to add OPENAI_API_KEY
make run
```

Then visit:

- Swagger UI: http://localhost:8111/knowledge-flow/v1/docs
- ReDoc: http://localhost:8111/knowledge-flow/v1/redoc

Prefer a zero-install workflow? Open the project in VS Code’s Dev Container to get the app ready with all local-only
dependencies (no MinIO or OpenSearch). Follow the “Dev-Container mode” section in the root `README.md` for step-by-step
instructions.

---

## Features

- Ingests files: PDF, DOCX, PPTX → Markdown
- Ingests data: CSV → Parquet datasets queried with DuckDB
- Vectorizes content using OpenAI, Azure, or Ollama
- Stores content and metadata in pluggable backends
- Runs standalone with only an OpenAI key and local file system
- Exposes REST and MCP endpoints for agents to query

---

## Supported Embedding Providers

| Provider       | How to enable                                                           |
|----------------|-------------------------------------------------------------------------|
| OpenAI         | Set `OPENAI_API_KEY` in `.env`                                          |
| Azure OpenAI   | Set Azure variables and update `configuration.yaml`                     |
| Ollama (local) | Set `OLLAMA_BASE_URL` and configure model block in `configuration.yaml` |

See the `ai:` section in `config/configuration.yaml` for complete setup examples.

---

## Make Commands

| Command             | Description                 |
|---------------------|-----------------------------|
| `make dev`          | Set up virtualenv with `uv` |
| `make run`          | Launch FastAPI server       |
| `make build`        | Package the app             |
| `make docker-build` | Build Docker image          |
| `make test`         | Run all tests               |
| `make clean`        | Remove build artifacts      |

---

## Production Deployment

Use the [fred-deployment-factory](https://github.com/ThalesGroup/fred-deployment-factory) to run a full stack including:

- Keycloak (authentication)
- Storage options:
  - PostgreSQL + `pgvector` (no OpenSearch dependency), or
  - OpenSearch (vector + metadata index) if you prefer that stack
- MinIO (content storage) when you need object storage
- Fred + Knowledge Flow containers

Pick the storage flavour that matches your platform constraints; both are supported end-to-end.

---

## Documentation

- [Knowledge Backend Developer Guide](docs/DEVELOPER_GUIDE.md)

---

## License

Apache 2.0 — © Thales 2025

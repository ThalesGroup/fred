# Knowledge Flow Backend

**Knowledge Flow** is a modular FastAPI backend that extracts and structures knowledge from documents or tabular data
for intelligent applications.

It is used by the open-source [Fred](https://github.com/ThalesGroup/fred) multi-agent assistant, exposing both REST and
MCP (Model Composition and Prompting) endpoints to serve structured knowledge to agents.

---

> PDF/PPTX ingestion works with the standard dependency set. PyMuPDF is an
> explicit optional extra and image variant; see [optional processing](#optional-pymupdf-processing)
> for installation, configuration and the licenses of the complete dependency family.

---

For Temporal roles, queues and the document lifecycle, see the
[ingestion architecture](../../docs/swift/design/INGESTION.md).

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

| Runtime                 | Main config                                 | Backing storage                                          | Status      |
| ----------------------- | ------------------------------------------- | -------------------------------------------------------- | ----------- |
| Dataset-centric runtime | `content_storage` + `storage.tabular_store` | One Parquet artifact per document + DuckDB at query time | Recommended |

Tabular access denials return HTTP 403 and direct callers to `list_tabular_documents`
for valid `document_uid` values: filenames and SQL aliases are not document UIDs.
The same guidance applies to inaccessible and invalid identifiers without revealing
whether a denied document exists; permission checks remain unchanged.

All processing pipelines are defined declaratively in `config/configuration.yaml`.

---

## Developer Docs

To learn how to:

- Add custom input or output processors
- Create new storage backends
- Extend the ingestion and search logic

→ See the [**Developer Guide**](docs/DEVELOPER_GUIDE.md)

For shared startup config and policy conventions across all Fred backends, read:

- [`docs/CONFIGURATION_AND_POLICY_CONVENTIONS.md`](../../docs/swift/platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md)

Key point: Knowledge Flow uses the same `ENV_FILE` + `CONFIG_FILE` contract as Agentic and Control Plane.

---

## Quick Start

The default configuration is developer-friendly and only uses local stores. See the
[configuration page](./config/README.md) when you want another setup.

### Optional Chroma storage

Chroma remains available as an embedded vector store that persists data on the
local filesystem, with no separate database service. From
`apps/knowledge-flow-backend`, install it explicitly with:

```bash
uv sync --locked --extra chroma
```

The default development dependency group also includes Chroma so `uv sync`,
`make dev`, `make run` and `make test` keep supporting the local configuration.
Keep the existing `storage.vector_store.type: chroma`, `local_path` and
`collection_name`: existing data needs no migration or reindexing.

For an installation without Chroma or development tools, use
`uv sync --locked --no-default-groups` and configure another supported vector
backend (for example OpenSearch or pgvector). Start it with `uv run --no-sync`
or its installed executable; `make run` deliberately installs development
dependencies. Selecting Chroma without installing it fails with instructions
to enable the extra; there is no automatic fallback to another store.

Production API and worker images omit Chroma by default. To use the same image
with local Chroma storage, build an explicit variant from the repository root:

```bash
docker build -f apps/knowledge-flow-backend/dockerfiles/Dockerfile-prod \
  --build-arg INSTALL_CHROMA=true -t knowledge-flow-with-chroma .
```

Use this variant for both the API and any workers configured to use Chroma,
including local container runs that mount the default configuration. Preserve
the existing persistent storage mounts.

Chroma stays in `uv.lock` for reproducible optional installations. Lockfile and
local-environment scanners can therefore still report its vulnerabilities.
Only scans of the default final image should lose Chroma-specific findings;
the opt-in image retains them. Shared dependencies needed by other features
remain installed.

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

- Ingests files: PDF, DOCX, DOC, ODT, PPTX, PPT → Markdown (legacy DOC/PPT and OpenDocument ODT are upgraded to DOCX/PPTX via LibreOffice)
- Ingests data: CSV → Parquet datasets queried with DuckDB
- Vectorizes content using OpenAI, Azure, or Ollama
- Stores content and metadata in pluggable backends
- Runs standalone with only an OpenAI key and local file system
- Exposes REST and MCP endpoints for agents to query

---

## Supported Embedding Providers

| Provider       | How to enable                                                           |
| -------------- | ----------------------------------------------------------------------- |
| OpenAI         | Set `OPENAI_API_KEY` in `.env`                                          |
| Azure OpenAI   | Set Azure variables and update `configuration.yaml`                     |
| Ollama (local) | Set `OLLAMA_BASE_URL` and configure model block in `configuration.yaml` |

See the `ai:` section in `config/configuration.yaml` for complete setup examples.

---

## Make Commands

| Command             | Description                 |
| ------------------- | --------------------------- |
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

## Optional PyMuPDF processing

The standard installation uses pypdf for fast PDF extraction and attachments,
Docling for advanced PDF/OCR, and pypdfium2/PDFium for PPTX slide rendering.
No PyMuPDF family package is installed by ordinary `uv sync` or `make dev`.
Installing an extra never changes the configured processor automatically.

To enable PyMuPDF locally, from this directory:

```sh
uv sync --extra dev --extra pymupdf
```

To build the optional production image, from the repository root:

```sh
docker build -f apps/knowledge-flow-backend/dockerfiles/Dockerfile-prod \
  --build-arg INSTALL_PYMUPDF=true -t knowledge-flow-backend-pymupdf:local .
```

Release CI builds `knowledge-flow-backend` and `knowledge-flow-backend-pymupdf`
under `ghcr.io/thalesgroup/fred-agent/`, with the same release tag (or `swift-dev`).
`INSTALL_CHROMA=true` is independent and can be combined with `INSTALL_PYMUPDF=true`
when building a custom image. Both flags default to false. No source recompilation
or package installation inside a running container is needed when using a published
variant; deploy the chosen image and restart the pods.

Then select the optional processor explicitly in the deployment's configuration:

- Fast PDF: in `processing.profiles.fast.input_processors`, replace only the `.pdf`
  entry's class path with
  `knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite2_pdf_to_md_processor.LitePdfMarkdownProcessor`.
- Advanced PDF: retain `PdfMarkdownProcessor` and set
  `processing.profiles.medium.pdf.extractor: pymupdf` and/or the equivalent rich key.
- Standard fast PDF uses `lite_pdf_to_md_processor.LitePdfMarkdownProcessor`;
  advanced PDF defaults to `docling`. PPTX always uses PDFium.

With Helm, supply the selected repository/tag under
`applications.knowledge-flow-backend.image` and
`applications.knowledge-flow-worker.image`. The extraction deployments inherit
from the worker; update any explicit image overrides on those deployments too.
Set processing overrides under both applications' `configuration.processing`.
Helm replaces processor lists, so preserve the other suffix entries when
replacing `input_processors`. All selectable profiles are validated at startup,
even when they are not the current default. An optional selection without its
extra fails with the installation/build remedy before ingestion starts.

The extra includes `pymupdf`, `pymupdf4llm` and `pymupdf-layout`. Their terms differ;
see the [license inventory](../../docs/swift/COPYLEFT-DEPENDENCIES.md#license-01---optional-pymupdf-family).
See the [migration note](../../docs/swift/ops/migrations/3159-optional-pymupdf.md)
for draining workers, rollback and re-ingestion effects.

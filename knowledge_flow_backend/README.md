# Knowledge Flow Backend

**Knowledge Flow** is a modular FastAPI backend that extracts and structures knowledge from documents or tabular data for intelligent applications.

It is used by the open-source [Fred](https://github.com/ThalesGroup/fred) multi-agent assistant, exposing both REST and MCP (Model Composition and Prompting) endpoints to serve structured knowledge to agents.

---

## What It Does

Knowledge Flow provides two primary services:

1. **Document Ingestion**  
   Converts unstructured files (PDF, DOCX, PPTX, etc.) into clean Markdown and metadata, splits the content into chunks, and vectorizes them using an embedding model. The results can be stored locally or in a vector store for semantic search (e.g., RAG pipelines).

2. **Structured Data Ingestion**  
   Processes structured files (CSV, XLSX, etc.) into normalized data rows for downstream querying. These are stored in JSON, SQLite, or other formats and can be exposed via custom REST endpoints or MCP APIs.

All processing pipelines are defined declaratively in `config/configuration.yaml`.

---

## Developer Docs

To learn how to:

- Add custom input or output processors
- Create new storage backends
- Extend the ingestion and search logic

→ See the [**Developer Guide**](docs/DEVELOPER_GUIDE.md)

---

## Quick Start

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

Prefer a zero-install workflow? Open the project in VS Code’s Dev Container and get a full stack (Knowledge-Flow + SearchEngine + ObjectStorage) in one click. See **[docs/DEV_CONTAINER.md](docs/DEV_CONTAINER.md)** for step-by-step instructions.

---

## Features

- Ingests files: PDF, DOCX, PPTX → Markdown
- Ingests data: CSV, Excel → structured rows
- Vectorizes content using OpenAI, Azure, or Ollama
- Stores content and metadata in pluggable backends
- Runs standalone with only an OpenAI key and local file system
- Exposes REST and MCP endpoints for agents to query

---

## Supported Embedding Providers

| Provider       | How to enable |
|----------------|----------------|
| OpenAI         | Set `OPENAI_API_KEY` in `.env` |
| Azure OpenAI   | Set Azure variables and update `configuration.yaml` |
| Ollama (local) | Set `OLLAMA_BASE_URL` and configure model block in `configuration.yaml` |

See the `ai:` section in `config/configuration.yaml` for complete setup examples.

---

## Make Commands

| Command             | Description                     |
|---------------------|---------------------------------|
| `make dev`          | Set up virtualenv with `uv`     |
| `make run`          | Launch FastAPI server           |
| `make build`        | Package the app                 |
| `make docker-build` | Build Docker image              |
| `make test`         | Run all tests                   |
| `make clean`        | Remove build artifacts          |

---

## Production Deployment

Use the [fred-deployment-factory](https://github.com/ThalesGroup/fred-deployment-factory) to run a full stack including:

- Keycloak (authentication)
- SearchEngine (vector + metadata index)
- ObjectStorage (content storage)
- Fred + Knowledge Flow containers

This is the recommended way to test a production-grade Fred deployment.

---

## Documentation

- [Knowledge Backend Developer Guide](docs/DEVELOPER_GUIDE.md)

---

## License

Apache 2.0 — © Thales 2025

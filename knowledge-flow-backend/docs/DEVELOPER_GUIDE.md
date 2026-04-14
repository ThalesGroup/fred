# Developer Guide – Knowledge Flow Backend

This guide explains how to understand, extend, and contribute to the Knowledge Flow microservice.

---

## API Structure: REST and MCP

The `knowledge_flow_app` exposes two API namespaces for different purposes:

---

### 1. REST API

- **Base URL**: `/knowledge-flow/v1`
- **Used by**: React frontend, CLI tools, admin scripts
- **Includes**:
  - Ingestion endpoints
  - Metadata management
  - Vector search
  - Tabular schema/query
  - Raw content access

You can access the Swagger UI at:

```
http://localhost:8111/knowledge-flow/v1/docs
```

---

### 2. MCP API

- **Base URL**: mounted under `/knowledge-flow/v1` as one MCP server per capability
- **Used by**: Agents that follow the MCP runtime exposed by Fred
- **Examples**:
  - `/knowledge-flow/v1/mcp-text`
  - `/knowledge-flow/v1/mcp-tabular`
  - `/knowledge-flow/v1/mcp-statistic`
- **Tabular MCP tools** expose the dataset-centric operations tagged `Tabular`, notably:
  - `list_tabular_datasets`
  - `get_tabular_dataset_schema`
  - `read_query`

Mounted via `FastApiMCP` in `main.py`:

```python
mcp = FastApiMCP(
    app,
    name="Knowledge Flow MCP",
    description="MCP server for Knowledge Flow",
    include_tags=["Vector Search", "Tabular"],
    describe_all_responses=True,
    describe_full_response_schema=True,
)
mcp.mount()  # Mounts the /mcp namespace
```

### Design Rationale

We deliberately **separate REST and MCP namespaces**:

- ✅ Easier to distinguish agent-facing endpoints
- ✅ Enables differential access control, observability, or documentation
- ✅ Keeps the REST API clean and focused on user/UI/system integrations

As a result, REST controllers keep their normal `/knowledge-flow/v1/...` routes, while MCP mounts expose the selected
operations through dedicated MCP servers. For the recommended tabular runtime, the REST surface is dataset-centric:

```txt
GET  /knowledge-flow/v1/tabular/datasets
GET  /knowledge-flow/v1/tabular/datasets/{document_uid}/schema
POST /knowledge-flow/v1/tabular/query
```

Agents do not see presigned object-store URLs directly. They receive only authorized dataset metadata plus SQL aliases,
while Knowledge Flow resolves Parquet locations and mounts them in DuckDB internally. For MinIO/S3-compatible
deployments, these DuckDB reads use backend-internal presigned URLs rather than browser-facing links.

This approach is consistent and scalable across all agent-facing interfaces.

## Processor Architecture

### Input Processors

Input processors extract structured content and metadata from uploaded files.

| Type     | Location            | Output        |
| -------- | ------------------- | ------------- |
| Markdown | `input_processors/` | Markdown text |
| Tabular  | `input_processors/` | Table rows    |

Each input processor specializes in a file type (PDF, DOCX, CSV, etc.).

### Output Processors

Output processors transform parsed content into embeddings or structured records.

| Type          | Location                                     | Output                |
| ------------- | -------------------------------------------- | --------------------- |
| Vectorization | `output_processors/vectorization_processor/` | Embeddings + metadata |
| Tabular       | `output_processors/tabular_processor/`       | Dataset-scoped Parquet artifacts |

---

## Vectorization Pipeline

```txt
  [ FILE PATH + METADATA ]
          │
          ▼
  DocumentLoaderInterface
          │
          ▼
   TextSplitterInterface
          │
          ▼
  EmbeddingModelInterface
          │
          ▼
   VectorStoreInterface
          │
          ▼
   BaseMetadataStore
```

Each interface is pluggable. You can switch OpenSearch → Pinecone, or Azure → HuggingFace by updating config and
implementing the interface.

---

## Tabular Pipeline

Knowledge Flow supports one tabular storage runtime for SQL querying:

| Runtime | What is stored | Main config | Status |
|---------|----------------|-------------|--------|
| Dataset-centric runtime | One Parquet artifact per document | `content_storage` + `storage.tabular_store` | Recommended |

### Recommended pipeline: dataset-centric runtime

The recommended tabular runtime is document-scoped rather than database-scoped.

```txt
  [ CSV INPUT ]
        │
        ▼
  CsvTabularProcessor
  - delimiter/encoding inspection
        │
        ▼
  TabularProcessor
  - DuckDB read_csv_auto(...)
  - COPY ... TO PARQUET
        │
        ▼
  Parquet artifact in content_storage
  + schema/row_count from Parquet metadata
        │
        ▼
  metadata.extensions["tabular_v1"]
        │
        ▼
  /tabular/datasets + /tabular/query
        │
        ▼
  DuckDB session with authorized views only
```

Important runtime rules for the recommended mode:

- Each document produces its own Parquet artifact under `storage.tabular_store.artifacts_prefix`.
- The main CSV-to-Parquet path is DuckDB-native and avoids loading the full dataset into a pandas DataFrame.
- Column names are normalized before export so the mounted dataset exposes stable SQL-safe names.
- ReBAC is enforced at document level before a dataset is exposed or mounted.
- Team/personal/library scope is applied before query aliases are shown to the caller.
- Read-only query validation accepts only `SELECT`/`WITH` statements and only against authorized mounted datasets.
- Remote MinIO/S3-compatible reads use backend-internal presigned URLs plus DuckDB `httpfs`.

### Legacy pipeline: SQL-backed tabular stores

The historical SQL-backed runtime has been removed.

- Keep the legacy design note only as migration context.
- Prefer the dataset-centric runtime for any endpoint, agent flow, or deployment.

---

## Knowledge Flow – Project Layout (Modularized)

This project uses a modular architecture that separates domain features from core infrastructure. Below is the directory
structure with roles and guidelines for extension.

---

### 🔩 Root Layout

```
knowledge_flow_backend/
├── main.py                       # FastAPI + MCP entrypoint
├── application_context.py        # Shared runtime context (DI / singleton-style config)
├── config/                       # YAML and Python-based configuration modules
├── common/                       # Shared types, utilities, exceptions
├── features/                     # DOMAIN LOGIC — Controllers, Services, Structures
├── core/                         # INFRASTRUCTURE — Stores, Processors, Pipelines
└── services/ (optional)          # Cross-cutting service logic if needed
```

---

### `features/` – Domain-Centric Components

Each folder inside `features/` implements a full vertical slice:

```
features/
├── tabular/
│   ├── controller.py             # Dataset-centric tabular REST/MCP endpoints
│   ├── service.py                # ReBAC-aware dataset resolution + DuckDB query runtime
│   └── structures.py             # Pydantic models for dataset/query requests and responses
├── vector_search/
│   ├── controller.py
│   ├── service.py
│   └── structures.py
└── metadata/
    ├── controller.py
    ├── service.py
    └── structures.py
```

📌 **Where to add a new API?**

- Create a folder in `features/`
- Add controller, service, and structures as needed

---

### `core/` – Infrastructure + Processing

```
core/
├── stores/
│   ├── base_metadata_store.py
│   ├── base_content_store.py
│   ├── vector_store/
│   │   ├── opensearch_vector_store.py
│   │   └── in_memory_vector_store.py
│   └── metadata_store/
│       ├── local_metadata_store.py
│       └── opensearch_metadata_store.py
│
├── processors/
│   ├── input/
│   │   ├── csv/
│   │   │   └── csv_tabular_processor.py
│   │   ├── docx/
│   │   ├── pdf/
│   │   └── ...
│   └── output/
│       ├── vectorization/
│       │   └── vectorization_processor.py
│       ├── tabular_normalization/
│       └── ...
│
└── pipelines/
    ├── vectorization_pipeline.py
    ├── tabular_pipeline.py
    └── ...
```

📌 **Where to add new file support?**

- Add an `input/your_type/` folder inside `core/processors`

📌 **Where to add embedding or normalization logic?**

- Use `core/pipelines/` and optionally create helpers in `output/`

---

### `common/` – Shared Types and Helpers

```
common/
├── structures.py                 # Shared Pydantic models
└── utils.py                      # Generic helpers
```

---

### `config/` – Pluggable Settings

Contains config classes (e.g., OpenAI, Ollama, GCS, MinIO):

```
config/
├── embedding_openai_settings.py
├── opensearch_settings.py
└── ...
```

---

### Developer Guidance

| Task                       | Location                                   |
| -------------------------- | ------------------------------------------ |
| Add a new REST API         | `features/your_feature/`                   |
| Add support for a new file | `core/processors/input/your_type/`         |
| Add a new vector store     | `core/stores/vector_store/`                |
| Change embedding backend   | `core/pipelines/vectorization_pipeline.py` |
| Customize ingestion flow   | `services/ingestion_service.py`            |
| Add business exceptions    | into your feature                          |

---

## ✅ Dev loop

```bash
make dev         # Setup .venv
make run         # Start FastAPI server
make test        # Run pytest
```

---

## 🧪 Testing

Use standard `pytest`. Tests live in `tests/`.

Run all:

```bash
pytest
```

Run specific:

```bash
pytest tests/test_vector_search_service.py
```

---

## 📚 Docs and Swagger

Docs available at: [http://localhost:8111/knowledge-flow/v1/docs](http://localhost:8111/knowledge-flow/v1/docs)

---

## 🤝 Contributions

Please follow the coding guidelines in `CODING_GUIDELINES.md` and submit PRs or issues via GitHub.

## Testing

```bash
make test
```

Use standard `pytest`. Tests live in `tests/`, and you can run individual files with:

```bash
pytest tests/test_ingestion.py
```

---

## Custom Configuration

- See [`config/configuration.yaml`](../config/configuration.yaml)
- Set environment variables in `.env` (based on `.env.template`)
- Configure AI backend in the `ai:` block (OpenAI, Azure, Ollama)

---

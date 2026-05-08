# Parquet Object Store + DuckDB

This page describes the recommended tabular runtime used by Fred today.

In this mode, each tabular document produces a document-scoped Parquet artifact stored in `content_storage`, and
queries are executed on demand with DuckDB against only the datasets the current user is allowed to read.

## Why This Mode Exists

This mode was introduced to get all of the following at the same time:

- document-level ReBAC on tabular data
- team/personal/library scoping aligned with the rest of the corpus
- no permanent shared SQL database containing all datasets
- compatibility with MinIO and S3-compatible object storage
- direct Parquet querying through DuckDB

This is the mode to prefer for new features and deployments.

## Main Building Blocks

The core code lives in:

- `knowledge-flow-backend/knowledge_flow_backend/core/processors/output/tabular_processor/tabular_processor.py`
- `knowledge-flow-backend/knowledge_flow_backend/features/tabular/artifacts.py`
- `knowledge-flow-backend/knowledge_flow_backend/features/tabular/service.py`
- `knowledge-flow-backend/knowledge_flow_backend/features/tabular/utils.py`
- `knowledge-flow-backend/knowledge_flow_backend/features/tabular/controller.py`

## Configuration

This mode is enabled by `storage.tabular_store` together with `content_storage`.

Example:

```yaml
content_storage:
  type: minio
  endpoint: http://localhost:9000
  access_key: admin
  bucket_name: knowledge-flow-content
  secure: false

storage:
  tabular_store:
    artifacts_prefix: "tabular/datasets"
    format: "parquet"
    compression: "snappy"
    query:
      engine: "duckdb"
      access_mode: "presigned_url"
      presigned_ttl_seconds: 900
      default_max_rows: 200
      max_rows: 1000
```

If `storage.tabular_store` is omitted, Knowledge Flow applies the built-in defaults automatically.

## Ingestion Processor Flow

When a CSV/Excel-like document is ingested in the recommended mode, `TabularProcessor.process(...)` performs the
following steps:

1. load the extracted tabular content into a pandas `DataFrame`
2. sanitize column names
3. detect likely datetime columns and normalize them
4. set `metadata.file.row_count`
5. compute a deterministic source revision for this document version
6. build the canonical object key under `storage.tabular_store.artifacts_prefix`
7. write the `DataFrame` to a temporary Parquet file using DuckDB
8. upload that Parquet file to the configured `content_storage`
9. build a `TabularArtifactV1` descriptor
10. persist that descriptor into `DocumentMetadata.extensions["tabular_v1"]`
11. clean up older Parquet revisions for the same document
12. mark `ProcessingStage.SQL_INDEXED` as done

The important consequence is that the metadata record becomes the control plane for tabular access:

- the physical data lives in object storage
- the typed artifact descriptor lives in document metadata
- later reads and queries resolve everything from that metadata

## What Gets Stored In Metadata

The ingestion processor stores a typed `tabular_v1` payload containing at least:

- dataset UID
- object key
- source revision
- format
- row count
- schema
- generation timestamp
- file size

That payload is later rehydrated by `read_tabular_artifact(...)`.

## Query Flow From MCP Call To Final Response

This is the runtime path when a user asks a question and an agent decides to call a tabular MCP tool.

### 1. User question

The user asks a question in Agentic Backend that requires tabular analysis.

Example:

- "Compare the sales totals by city for my team datasets."

### 2. Agent decides tabular access is needed

The SQL-capable agent decides it needs tabular data rather than pure text retrieval.

Typical sequence:

1. call the dataset-listing MCP tool
2. inspect aliases, schema, and row counts
3. draft a read-only SQL query
4. call the read-query MCP tool

### 3. MCP call reaches Knowledge Flow

Knowledge Flow exposes dataset-centric tabular routes:

- `GET /tabular/datasets`
- `GET /tabular/datasets/{document_uid}/schema`
- `POST /tabular/query`

The controller delegates to `TabularService`.

### 4. Knowledge Flow resolves authorization and active scope

Before exposing any dataset, Knowledge Flow resolves:

- current authenticated user
- optional `owner_filter`
- optional `team_id`
- optional `document_library_tags_ids`

This keeps tabular visibility aligned with document-level permissions and active area scoping.

### 5. Knowledge Flow computes readable datasets

`TabularService._resolve_authorized_datasets(...)` does the main selection:

1. ask ReBAC which documents the user can read
2. read document metadata
3. apply team/personal/library scope if provided
4. keep only documents carrying a `tabular_v1` artifact
5. generate stable SQL aliases for the visible datasets

Important point:

- DuckDB is not the security boundary
- the security boundary is the selection of datasets before they are mounted

### 6. Knowledge Flow validates the SQL

Before execution, `validate_read_query(...)` ensures:

- exactly one statement
- only `SELECT` or `WITH`
- no writes or DDL
- no references outside the allowed dataset aliases for the request

### 7. Knowledge Flow opens one ephemeral DuckDB session

For each query request, Knowledge Flow creates a fresh in-memory DuckDB connection.

This session:

- is temporary
- is per request
- is closed after execution

There is no shared permanent DuckDB catalog containing every dataset.

### 8. Knowledge Flow resolves the Parquet location for each dataset

For each selected dataset:

- if `content_storage` is local, DuckDB reads the Parquet file from disk
- if `content_storage` is MinIO/S3-compatible, Knowledge Flow generates a short-lived presigned URL

The query path then uses DuckDB `httpfs` for remote object access.

### 9. Knowledge Flow mounts only authorized datasets

`TabularService._mount_datasets(...)` creates one temporary view per dataset alias.

This means:

- only authorized datasets are visible in the current query session
- unauthorized datasets are absent from the session entirely
- the views live only for the duration of the request

This is what "mounted on the fly" means in this runtime.

### 10. DuckDB runs the SQL directly against Parquet

DuckDB executes the validated SQL against those temporary views.

For MinIO/S3-compatible storage:

- the Parquet is read through the presigned URL
- `httpfs` handles the HTTP access
- the application does not first load all datasets into a pandas `DataFrame` just to run the SQL query

### 11. Knowledge Flow returns rows to the agent

The response contains:

- normalized SQL text
- result rows
- dataset UIDs involved
- query aliases involved

### 12. The agent writes the final answer

Agentic Backend receives those rows, may iterate once more if needed, then synthesizes the final natural-language
answer returned to the user.

## Why This Mode Is Better For Access Segregation

This mode is preferable because:

- access control is resolved at the document level before query execution
- only authorized datasets are mounted in the session
- team and library scope can be enforced before alias exposure
- there is no requirement to share one long-lived SQL database containing every dataset across teams

That is why this is the recommended tabular mode for Fred.

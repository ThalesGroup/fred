# Fred Knowledge

Shared primitives consumed by the Knowledge Flow API and ingestion worker. Neither application is a dependency.

| Module | API consumer | Worker consumer |
| --- | --- | --- |
| `artifacts` | Published Markdown and tabular reads with SHA-256 verification | Generation publication verifies uploaded/restored objects |
| `tabular` | Dataset metadata and query aliases | CSV/Excel artifact production |
| `vector` | Authorized corpus search | Generation-scoped indexing, cancellation and retry splitting |
| `text` | On-demand summary and exhaustive extraction | Chunking and ingestion summaries |
| `configuration` | Reader/index/query/splitter parameters | Artifact/index/tabular/splitter parameters |

Claims, publication, workflows and processor registration belong to the worker. HTTP authorization and publication visibility belong to the API. `DocumentMetadata` remains in fred-core with unchanged serialization.

From this directory: `make dev`, `make code-quality`, `make test`. The split has not yet been validated end to end.

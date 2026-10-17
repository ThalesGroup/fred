---
schema: 1
title: "Make Chroma an optional Knowledge Flow dependency"
impact: minor
configuration: none
configuration_reason: "Storage configuration keys and data formats are unchanged; deployments using Chroma must explicitly install its extra or build the opt-in image."
---
## Applicability

Knowledge Flow API and worker deployments. The standard production image no
longer includes Chroma or dependencies used exclusively by it.

## Prerequisites

Check `storage.vector_store.type` before upgrading. Deployments using OpenSearch,
pgvector or another non-Chroma backend can use the standard image as before.

## Configuration

No YAML keys, secrets or chart schemas change. For Chroma, retain the existing
`local_path`, `collection_name` and persistent volume mounts.

## Upgrade

Deploy normally for non-Chroma backends. Deployments using Chroma must install
the `chroma` extra or build the `INSTALL_CHROMA=true` image variant for their API
and workers, following the [installation instructions](../../../../apps/knowledge-flow-backend/README.md#optional-chroma-storage).
The default developer workflow continues to include Chroma. No reindexing or
data migration is required.

## Validation

Check the installed packages in the final image. The default image must not
contain `chromadb`; non-Chroma API and workers must start normally. In the
opt-in variant, search an existing local document, ingest a document, restart
and verify its chunks remain searchable, then delete it.

## Rollback

Restore the previous image and keep the existing configuration and volumes.
This can reintroduce Chroma-related vulnerabilities into the production image.

## Limitations

This removes an unused dependency from the default image, not vulnerabilities
from Chroma itself. Optional installations and lockfile scans can still report
them. Unrelated shared dependencies and OS vulnerabilities remain visible.

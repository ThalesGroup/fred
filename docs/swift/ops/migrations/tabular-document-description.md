---
schema: 1
title: "Combined tabular descriptions and richer column metadata"
impact: minor
configuration: local
configuration_reason: "Only tool usage instructions in apps/fred-agents/config/mcp_catalog.yaml change; no configuration keys, environment variables or production Helm values change."
---

## Applicability

Deployments using Excel or CSV documents through the tabular tools.

## Prerequisites

Keep the original files available if re-ingestion is needed.

## Configuration

No configuration changes are required for the bundled Fred integration.

## Upgrade

Deploy Fred normally. Users must re-ingest existing Excel or CSV files
to benefit from richer column metadata and improved Excel boolean typing.
These improvements are applied during ingestion, without automatic backfill.

## Validation

After ingestion completes, describe and query a document through an agent.
Check that its tables and column types are returned correctly.

## Rollback

Redeploy the previous Fred release. This does not undo regenerated document
artifacts.

## Limitations

Custom integrations using get_tabular_documents_schemas or
get_tabular_document_markdown must switch to describe_tabular_documents.
The /tabular/documents/{document_uid}/markdown endpoint is removed.
Excel descriptions require a successfully generated preview.

---
schema: 1
title: "Constrain runtime execution URLs and tabular queries"
impact: minor
configuration: production
configuration_reason: "Runtime ingress prefixes are now validated as canonical root-relative paths; deployments with absolute or ambiguous prefixes must update their runtime_catalog_sources values. The bundled Helm value already uses the accepted form."
---

## Applicability

Fred deployments with configured runtime catalog sources or tabular query access.

## Prerequisites

Inspect every `platform.runtime_catalog_sources[].ingress_prefix` value in the
active deployment configuration before upgrading.

## Configuration

Each `ingress_prefix` must be a canonical path beginning with one `/`, such as
`/fred/agents/v2`. Replace absolute URLs, network-path references, encoded
characters, dot segments, and trailing slashes with the gateway's root-relative
runtime path. The bundled Helm value needs no edit. No new secrets or permissions
are required.

## Upgrade

Update invalid runtime prefixes in the deployment values before restarting the
control plane. Deploy the control plane, frontend, and Knowledge Flow backend
through the normal release procedure. No data migration or re-ingestion is
required.

## Validation

Start a managed-agent turn and confirm its stream opens through the configured
runtime ingress path. Run an authorized tabular query and confirm it returns
results; confirm an external file or metadata query is rejected.

## Rollback

Restore the previous Fred release and its previous values together. Previously
accepted noncanonical prefixes may resume working after rollback; they should
still be corrected before a later upgrade.

## Limitations

Pure built-in DuckDB analytical functions remain available in tabular queries. Queries that inspect runtime configuration, use side-effecting functions, or use external table sources are rejected. DuckDB settings are defense in depth and do not replace process or container isolation for untrusted SQL.

---
schema: 1
title: "Upgrade urllib3, PyJWT, virtualenv and DOMPurify to patched versions"
impact: none
configuration: none
configuration_reason: "Only knowledge-flow-backend and frontend lockfiles and the frontend dompurify override change; no configuration keys or defaults change."
no_action_reason: "These are patch-level dependency upgrades already used by the other backends; data, APIs and deployment order are unchanged."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Ingest a document in knowledge-flow and check that it completes; open a chat answer containing a mermaid diagram and check that it renders.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The `http-cache-semantics` alert in `libs/frontend` has no patched version yet; it is only used by `sigstore` when publishing frontend packages.

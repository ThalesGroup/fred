---
schema: 1
title: "Use a fresh Weaver schema for conversation attachments"
impact: major
configuration: production
configuration_reason: "Control Plane content.limits adds positive conversation_files and conversation_bytes quotas; the generated backend and chart schemas include these settings with defaults of 100 files and 1073741824 bytes."
---

## Applicability

The experimental Weaver 5.x attachment branch tracked in #3362. This is a
fresh-install release candidate, not an upgrade path for Swift or an earlier
Weaver database. The frontend-only notes in this PR do not cover this schema
replacement.

## Prerequisites

Use matching Control Plane, Knowledge Flow, agent pod and frontend versions.
The initial Control Plane schema now records conversation-owned documents and
upload reservations. An already initialized database from the earlier schema
cannot apply these changes by replaying the initial migration.

## Configuration

Control Plane `content.limits.conversation_files` defaults to 100 and
`content.limits.conversation_bytes` defaults to 1073741824 (1 GiB). Both must be
positive. Review these conversation attachment limits alongside existing
personal, team and organization quotas. The generated backend configuration
schema and Helm values schema include the new fields; omitted settings use
the backend defaults.

## Upgrade

Install against a fresh database and matching fresh storage. This branch does
not provide a data conversion or incremental SQL migration from the earlier
experimental schema. Do not treat a Helm upgrade over that database as supported.
If an experimental environment contains data to retain, preserve it separately
before deliberately replacing that environment. No reset is performed by the PR.

## Validation

Create a conversation, attach a document and wait for it to become ready. Ask
a question about that document and verify its use in the response. Check that
another user or conversation cannot access the attachment, that storage limits
apply, and that deletion removes the attachment through its normal lifecycle.
The owner completes functional and integration-platform acceptance; code-quality
checks alone do not establish these outcomes.

## Rollback

Use the previous matching application versions with their preserved environment
or a fresh database initialized by that version. Do not run the old Control Plane
against the replacement schema. No reverse data migration is supplied.

## Limitations

The fresh-install decision is intentional for the new release, which is not yet
deployed in production. Pending Swift features remain separate porting lots;
their development previews do not provide a working production backend.

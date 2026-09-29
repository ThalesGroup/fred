---
schema: 1
title: "Release v3.0.0 preparation and pre-policy contribution audit"
impact: none
configuration: none
configuration_reason: "Only release notes and migration documentation change; no configuration key, default, chart value or schema is involved."
no_action_reason: "The release documents themselves need no deployment action; the audited contributions below add no operator step beyond their own notes."
legacy_range:
  base: code/v2.2.3
  through: 3dbb8c717dc13f7aec1a6be2f36d64682abe1b9f
covers:
  - 57322f1e484ca12b961dbe3806d81cea183f97cb
---
## Applicability

Existing Fred deployments upgrading from v2.2.3 to v3.0.0.

The legacy range from `code/v2.2.3` through the policy activation commit
contains a single contribution: opt-in delegated execution and renewable
service credentials (#2808). It was reviewed against its own note,
`2808-delegated-execution`, which remains the accurate declaration: default-off
upgrade needs no new configuration, and optional activation is `minor`.

The session ownership fix on the OpenAI-compatible chat route (#2813) landed
without a note. With authentication enabled, a request whose
`X-Fred-Session-Id` targets another user's existing history session now returns
HTTP 403 and emits `session_owner_mismatch`. Request and response schemas,
configuration and stored data are unchanged; new sessions behave as before.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required for
these contributions. Follow the other notes in this guide for their own steps.

## Validation

With authentication enabled, call the OpenAI-compatible chat route with another
user's existing session identifier and check that it returns 403.

## Rollback

Use the normal rollback procedure; these contributions introduce no data migration.
Rolling back re-opens cross-user access to existing sessions on the
OpenAI-compatible route.

## Limitations

Conversations known only through checkpoints, without a history ownership
record, are not covered by the ownership gate on the OpenAI-compatible route.

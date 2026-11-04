---
schema: 1
title: "Explain tabular tool failures and successful empty results"
impact: none
configuration: none
configuration_reason: "No configuration keys or defaults change; the tabular MCP prompt is packaged with the existing capability."
no_action_reason: "No data migration, re-ingestion or administrator action is required. The SQL response only gains an optional explanation field."
---

## Applicability

Deployments using tabular MCP tools and the chat trace drawer.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the runtime, Knowledge Flow and frontend normally. New turns use the
updated packaged tabular prompt. SQL responses with zero rows include an
explicit success message; zero/null aggregate rows remain ordinary results.

## Validation

Run a valid SELECT matching no rows and inspect its trace detail. Confirm the
explicit success explanation. Open a failed tabular call: its business arguments
and safe error should be visible, with no recovery section. Unknown historical
errors show a fallback rather than arbitrary exception text.

## Rollback

Use the normal rollback procedure. No stored data or configuration is changed.

## Limitations

Prompt guidance does not guarantee that a model will avoid all redundant calls.
There is no new cache, duplicate-call suppression or execution limit. This
change does not modify token refresh behavior or repair authentication failures.

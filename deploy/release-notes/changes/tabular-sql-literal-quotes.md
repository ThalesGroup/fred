---
schema: 1
title: "Clarify DuckDB string literal quoting for tabular queries"
impact: none
configuration: none
configuration_reason: "Only the packaged tabular capability instructions change; no configuration keys or defaults change."
no_action_reason: "Existing data, APIs and query execution are unchanged; the updated instructions load with a normal agent pod deployment."
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

Ask a tabular agent to filter a categorical value containing an apostrophe and check that the generated DuckDB SQL doubles the embedded single quote.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

These instructions guide the model but do not guarantee every generated query is valid SQL.

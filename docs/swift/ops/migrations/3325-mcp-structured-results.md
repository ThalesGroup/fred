---
schema: 1
title: "Restore structured MCP tabular results in agent runtimes"
impact: none
configuration: none
configuration_reason: "Only the runtime conversion of MCP results changes; MCP catalogs, URLs, credentials and deployment values are unchanged."
no_action_reason: "Normal deployment of the agent runtime activates the fix for existing tabular documents without re-ingestion or data migration."
---

## Applicability

Fred agent pods using MCP tools that return structured JSON, including Knowledge
Flow tabular discovery, schema inspection, search and queries.

## Prerequisites

No prerequisites beyond the existing MCP v2 deployment.

## Configuration

No configuration or permission changes are required.

## Upgrade

Deploy the agent pods normally. Existing ingested documents remain usable.

## Validation

Ask an agent to inspect and count rows in an existing tabular document. Verify
that discovery, schema inspection and the SELECT query succeed without
`tool_ref` or `structured_content` validation errors.

## Rollback

Use the normal agent pod rollback procedure. No data migration is involved;
rolling back this fix restores the structured-result failure.

## Limitations

This fix restores tool-result compatibility. It does not guarantee that a model
chooses the correct business filter or follows the prescribed tool sequence.

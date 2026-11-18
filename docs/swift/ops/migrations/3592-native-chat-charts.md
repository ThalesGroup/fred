---
schema: 1
title: "Render tabular query results as native chat charts"
impact: none
configuration: none
configuration_reason: "The native tool and chart renderer use existing agent and frontend dependencies; no deployment setting changes."
no_action_reason: "Existing conversations and agent configurations remain valid; normal agent-pod and frontend deployment supplies the tool and renderer."
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the agent pods and frontend normally.

## Validation

Ask a SQL expert to chart a bounded aggregate query. Confirm that `chart.render`
appears, the chart renders in chat, and its original rows can be inspected.

## Rollback

Use the normal rollback procedure. Chart parts already stored in history remain
available when a compatible frontend is deployed again.

## Limitations

The tool accepts at most 50 rows and 50,000 serialized characters per chart.

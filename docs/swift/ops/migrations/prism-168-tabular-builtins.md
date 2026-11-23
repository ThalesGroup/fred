---
schema: 1
title: "Restore pure SQL built-ins and tabular trace panels"
impact: none
configuration: none
configuration_reason: "Only built-in SQL identity validation and frontend result rendering change; no configuration keys or defaults change."
no_action_reason: "Existing tabular artifacts, permissions and API payloads are reused; normal Knowledge Flow and frontend deployment enables the correction."
---

## Applicability

Deployments using Knowledge Flow tabular queries and the managed-chat tool panel.

## Prerequisites

No additional prerequisites beyond normal deployment.

## Configuration

No configuration or permission changes are required.

## Upgrade

Deploy Knowledge Flow and the frontend normally. Existing Excel and CSV resources do not need re-ingestion.

## Validation

Run a read query over an authorized dataset using `TRIM` and `SUBSTRING`; confirm cleaned values are returned. Inspection functions and unauthorized sources must still be rejected. Open a successful tabular discovery or description step in the chat trace and confirm the rich panel displays its files, catalog or columns.

## Rollback

Use the normal application rollback procedure. No data migration is involved; rolling back restores the SQL compatibility and trace-display defects.

## Limitations

This correction does not guarantee model interpretation of business rules or exhaustive processing of large spreadsheets within the model context budget. Existing query row, memory and execution limits remain in force.

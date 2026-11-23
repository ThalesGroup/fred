---
schema: 1
title: "Document extraction failures and reading guidance"
impact: none
configuration: none
configuration_reason: "Existing capability IDs, settings, API fields and confirmation defaults are unchanged."
no_action_reason: "Normal application deployment is sufficient; no data migration, reindexing or agent reconfiguration is required."
---
## Applicability

Swift deployments using document reading, summarization or extraction.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Knowledge Flow and the Agent Pod with the updated document capabilities,
plus the frontend for the revised labels and help. No additional operator action
is required. This change adds no database migration.

## Validation

On one maintenance contract, ask for a clause quotation, a two-sentence summary,
and a list of deadlines and responsible parties. Confirm the distinct results.
An extraction window that fails after existing retries now fails the request
through the existing error path instead of silently returning incomplete data.
An input-size warning remains visible even when extraction finds no matches.

## Rollback

Use the normal application rollback procedure. There is no stored-data or
configuration conversion to undo. Rollback restores the former silent omission
behavior on extraction failures.

## Limitations

Reading uses converted text, not the original file layout. Model extraction can
miss items and deduplicates identical matches. The existing 2,000,000-character
input cap, concurrency, retries and confirmation settings are unchanged.
Weaver integration and production validation are separate follow-up work.

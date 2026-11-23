---
schema: 1
title: "Bound tabular query output by characters and make row limits optional"
impact: minor
configuration: production
configuration_reason: "Knowledge Flow replaces storage.tabular_store.query.max_rows with max_output_chars=50000 and raises default_max_rows to 500 in backend configuration and Helm values."
---

## Applicability

Fred deployments exposing Knowledge Flow tabular tools, including API and worker
configuration sharing the tabular storage block.

## Prerequisites

Review deployment overlays and custom callers of read_query before upgrading.
No data migration or re-ingestion is required.

## Configuration

Remove `storage.tabular_store.query.max_rows` from backend configuration and chart
overlays. Replace it with `max_output_chars: 50000` to bound the compact JSON rows
array. Metadata and explanation text are additional. Set `default_max_rows: 500`
or another positive default. The character budget must be at least 2 characters.
The bundled chart values and GCP example contain the replacement settings.

## Upgrade

Update configuration and Knowledge Flow images together, then restart affected
pods using the normal deployment procedure. Keep settings consistent across API
replicas. Explicit `max_rows: null` now disables the tool-added row limit; callers
wanting the configured default must omit that argument. Positive integer requests
have no fixed row ceiling. SQL-authored LIMIT and execution guards still apply.

## Validation

Confirm startup accepts the new configuration. Query a dataset containing more
than 500 small rows: omission returns at most 500 with a possible-additional-rows
notice; explicit null can return more while respecting the character budget.
Query wide rows and check that only complete rows fit, with the tool-owned English
explanation after row data. An oversized first row must produce a truncation
explanation rather than a no-matches message. Check recorded chat details too.

## Rollback

Roll back images and configuration together. Restore the previous `max_rows`
ceiling and default if rolling back to an image requiring those settings. No
persisted tabular data changes need reversal.

## Limitations

The budget counts JSON characters, not tokens or bytes. Disabling the row limit
does not disable the character or engine execution budgets. Messages do not claim
a complete table count: without a row limit, reading stops on character overflow.
Existing recorded responses retain their historical contents.

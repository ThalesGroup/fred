---
schema: 1
title: "Derive document and resource access from readable folders"
impact: none
configuration: none
configuration_reason: "The existing OpenFGA model and Knowledge Flow settings are reused; no service, chart or authorization-model setting changes."
no_action_reason: "A normal image deployment applies the fix. If Knowledge Flow or the control plane log event=authorization_list_objects outcome=possibly_truncated, one user reaches OpenFGA's ListObjects limits: raise OPENFGA_LIST_OBJECTS_MAX_RESULTS or OPENFGA_LIST_OBJECTS_DEADLINE on the OpenFGA server."
---
## Applicability

Above 1,000 readable documents, OpenFGA's plain ListObjects response was silently
truncated. Tabular tools (list, describe, query, value search), document listing,
label lookups and resource listing used that truncated list, so agents lost
workbooks and returned 404 for documents the caller could read.

Knowledge Flow no longer enumerates readable documents or resources. Stored
folder membership selects candidates from readable folders or the request's
team, personal or library scope. Object READ checks still authorize ordinary
readers, including when a stale metadata/resource save has restored a removed
membership only in SQL. The remaining enumerations (one user's folders,
teams and file areas) keep the same ListObjects call and now log a warning when
a response may have been truncated.

## Prerequisites

Use the existing demo identities and teams and an idle local test deployment with
working ingestion for the validation campaign.

## Configuration

No application configuration change is required. The optional large test is
enabled only with `FRED_VALIDATION_LARGE_CORPUS=1` on the validation command.

## Upgrade

Deploy Knowledge Flow and the control plane normally. No schema, FGA model, chart
or frontend change is required.

## Validation

Follow the [folder validation instructions](../../../../validation/README.md#folder-inventory-and-deletion).
The opt-in large case uploads 3,000 background documents and checks that a team CSV
is listed, described and queryable. That scenario does not exercise label SQL.
The fred-core PostgreSQL integration suite separately exercises the three label
queries, including 32,768 folder IDs. Deterministic service tests cover completed
folder removal followed by stale saves and denial across the affected surfaces.

## Rollback

Reverting the images restores the truncation defect.

## Limitations

Documents orphaned by the earlier folder-deletion defect are not repaired.
A user who can read more than 1,000 folders in total (subfolders included) is
still truncated at OpenFGA's default limit; the warning above makes it visible.
Unscoped tabular listing reads metadata for all folder candidates; agent tools
always carry a team or personal scope. Discovered-candidate READ checks run at
most ten at a time per request: one Check per tabular workbook, matching label UID, listed
metadata candidate or resource. Label pages repeat checks for all matches before
counting; vocabulary checks the folder corpus. Existing tabular diagnostics for
R missing explicitly requested UIDs can add R concurrent Checks. Validate latency
at deployment scale before release; correctness tests do not establish concurrency
capacity.

This change does not repair historical memberships or resolve the pre-existing
lost-update behavior of full metadata/resource writes. Ingestion can also
reassert parents from its snapshot; that pre-existing write behavior is not
changed by the read-side confidentiality correction.

---
schema: 1
title: "Home agent suggestions without OpenSearch"
impact: minor
configuration: none
configuration_reason: "The existing SQL database and authorization configuration are reused; no chart or application setting changes."
---
## Applicability
Existing deployments, including those without OpenSearch KPI storage.

## Prerequisites
Normal control-plane database migration privileges.

## Configuration
No configuration changes are required.

## Upgrade
Use the normal deployment procedure and control-plane Alembic upgrade. Revision
`d7a2f591c034` adds nullable `session_metadata.last_activity_at` and its lookup
index. No new table or historical backfill is introduced.

## Validation
Open home without KPI storage: accessible default-team and personal agents
appear. Send a message to an accessible agent and return home: that instance
ranks first, with up to four other distinct agents. Rename alone must not
establish recent priority.

## Rollback
Roll back application code normally; old code ignores the additive column.
If explicitly downgrading the schema, stop the new application first, then
run the ordinary Alembic downgrade. Dedicated activity dates will be lost.

## Limitations
Older conversations have unknown activity until another activity PATCH.
Ranking uses the existing browser activity report, not proof of successful
runtime execution. Agents in non-default teams appear through known recent
activity; default-team and personal agents provide the alphabetical complement.

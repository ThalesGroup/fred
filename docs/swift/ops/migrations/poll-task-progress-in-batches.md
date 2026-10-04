---
schema: 1
title: "Follow task progress with batched reads instead of one stream per task"
impact: none
configuration: none
configuration_reason: "The change adds an optional query parameter and replaces the frontend's progress transport; no configuration keys or defaults change."
no_action_reason: "The API change is additive, no data or schema changes, and the frontend switches transport on a normal deployment."
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

Import more than six files into a team folder and keep the page open longer
than the realm's access token lifetime. Every file reaches its final state in the
import panel and the Resources table without a reload, and the rest of the page
stays responsive during the import. The browser's network panel shows periodic
`GET /tasks?scope=user&task_id=…` reads instead of one `…/events` stream per file.

Query arrays from the generated clients are now sent as repeated keys. On a page
listing documents or agents from several authors, each author's name now shows
instead of a bare identifier.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Progress appears up to five seconds late. A task whose workflow dies without the
backend noticing is corrected by the existing reconciliation sweep: it only
considers tasks idle for five minutes and runs every two, so allow about seven
minutes after the task's last update.

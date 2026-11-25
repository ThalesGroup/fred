---
schema: 1
title: "Improve Resources table and file browser usability"
impact: minor
configuration: none
configuration_reason: "The change adds one database preference column and UI behavior without configuration keys."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

The Control Plane database must be available for its Alembic migration.

## Configuration

No configuration changes are required.

## Upgrade

Apply the Control Plane migration adding `users_preferences.resources_tree_open`
before serving the updated frontend. Then deploy the updated backend and frontend.
Existing preference rows receive `false`, so the file browser starts closed.

## Validation

Open Resources with an existing account. The file browser starts closed, opens
from the table toolbar, and restores that choice after signing in on another
browser. Hover a long name and drag a labeled column boundary.
In the right-hand table, Shift-click a second row to select the visible range,
including any folders between the two rows.

## Rollback

Rollback the application normally. The older code ignores the added column;
retain it unless a full database rollback is required. A full rollback drops
the visibility choice.

## Limitations

Tree width and expanded folders remain browser-local and are not restored on
another device.

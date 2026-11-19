---
schema: 1
title: "Weaver organization-first navigation and shared space header"
impact: none
configuration: none
configuration_reason: "Frontend-only change: navigation, panel headers and settings pages reuse existing Control Plane endpoints; no environment variables, secrets or chart settings are added or changed."
no_action_reason: "No data, schema, API or configuration change; deploying the matching frontend is enough and the previous frontend can be redeployed as is."
---
## Applicability

Existing Weaver deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required. Users find
the profile, Help Center and admin console in a profile card at the bottom of the
navigation panel instead of the former left rail.

## Validation

Open the application: the organization panel lists the marketplace, the personal
space and the person's teams, and the profile card at the bottom of the panel opens
the profile menu.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No dedicated mobile layout yet: below 768px the profile card sits at the end of the
navigation strip.

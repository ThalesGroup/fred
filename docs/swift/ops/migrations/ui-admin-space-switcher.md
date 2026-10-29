---
schema: 1
title: "Switch between the platform and organization admin spaces"
impact: none
configuration: none
configuration_reason: "Frontend change only; no configuration keys or defaults change."
no_action_reason: "Navigation of the application shell only; permissions and data are unchanged."
---

## Applicability

Existing deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy normally; no additional operator or user action is required.

## Validation

Sign in as a platform owner who is also an organization admin. Home opens the personal home page, and the rail shows the same entries on every page. In the admin panel, a switcher at the top shows the current space and lists the platform and the organization; the platform menu lists Organizations and Provisioning only. The Home and Marketplace panels show the organization's name at the top. A platform owner with no organization membership still sees only the platform pages.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The switcher lists one organization, the one the person belongs to.

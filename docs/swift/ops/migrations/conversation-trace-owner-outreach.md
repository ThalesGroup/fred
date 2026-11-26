---
schema: 1
title: "Identify conversation traces and contact their owners"
impact: none
configuration: none
configuration_reason: "The inspector uses existing trace operator permissions, user metadata, and frontend branding settings."
no_action_reason: "Trace detail fields are additive and come from existing data. Normal deployment requires no database migration, backfill, or special deployment order."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. No additional operator or user action is required.

## Validation

As a trace operator, open a captured failure whose owner has never granted
consent. Check that the inspector masks the conversation title, displays
available identity details, and offers the owner chat link. Open Contact user
and check that the French and English drafts use the configured site name and
link to the same chat.

## Rollback

Use the normal rollback procedure. This change introduces no data migration.

## Limitations

The email draft action requires an email address in the existing user
metadata. Copying the message is available when the email is missing.

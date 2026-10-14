---
schema: 1
title: "Condensed Platform access administration screens"
impact: none
configuration: none
configuration_reason: "Frontend layout, styles and wording of one administration page only; no configuration keys or defaults change."
no_action_reason: "No API, data or permission changes; the new presentation ships with the frontend image on normal deployment."
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

As a platform administrator, open Administration > Platform access: a badge
beside the page title says whether filtering is on, and the Whitelist tab shows
its Users and Teams sub-tabs without a second "Whitelist" heading. In the Rules
tab, "Test with my account" shows two banners: one for the rule, one for
whether you keep access.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Some labels changed (for example "Opens" instead of "Accesses" in the
invitation-links dialog, "Not checked" instead of "Verification unavailable"
in the activation review). Internal administrator guides quoting the previous
labels may need an update.

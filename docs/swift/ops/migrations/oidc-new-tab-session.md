---
schema: 1
title: "Keep the requested page and session when an in-app page opens in a new tab"
impact: none
configuration: none
configuration_reason: "Only browser-side sign-in redirect handling and in-app link attributes change; no configuration keys, defaults or identity-provider settings change."
no_action_reason: "The identity-provider client, its redirect URIs and stored data are unchanged; the fix takes effect with a normal frontend deployment."
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

While signed in, click Help Center in the main navigation: the Help Center
opens in a new tab without a sign-in page. Paste a deep link such as `/help`
into a fresh tab: after sign-in, the tab shows that page instead of the home page.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

A deep link opened from outside the application (bookmark, e-mail) still goes
through the identity provider, which shows its sign-in form when its own SSO
session has expired.

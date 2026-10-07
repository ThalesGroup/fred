---
schema: 1
title: "Apply the UI theme before the first paint and make every theme self-contained"
impact: none
configuration: none
configuration_reason: "Frontend stylesheets and a static boot script only; no configuration key, default or chart value changes."
no_action_reason: "The theme boot script ships with the frontend image and preserves stored choices. Custom proxies must permit /theme-boot.js; external token consumers follow the separate neutral-palette migration guidance."
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

The frontend serves a new static file, `/theme-boot.js`, with
`Cache-Control: no-cache`. Deployments that front the frontend with their own
proxy or content security policy must allow this same-origin script
(`script-src 'self'` is enough).

This theme-isolation change adds no further package token changes. External
`@fred-oss/design-tokens` consumers must still follow the
[token migration guidance](neutral-surface-scale.md) for the neutral palette
changes shipped in this release. Package publication and adoption are separate
from deploying Fred.

## Validation

Pick the Cloud theme and dark mode in the profile page, then reload: the page
appears directly in Cloud dark, without showing another theme first.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.

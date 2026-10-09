---
schema: 1
title: "Expose contact support in the Help Center"
impact: none
configuration: none
configuration_reason: "The Help Center reuses the existing contactSupportLink frontend property; no configuration keys or defaults change."
no_action_reason: "Only frontend rendering changes; existing configured support destinations appear after normal deployment, with no data or API changes."
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. The existing `contactSupportLink` value
is reused; an empty value keeps the support action hidden.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Open the Help Center through the global navigation. With `contactSupportLink`
configured, verify that "Contact support" appears in the header across help
sections and articles in both languages, and opens the configured destination
in a new tab. With an empty value, verify that the action is absent.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The support destination's availability depends on the existing configured URL.

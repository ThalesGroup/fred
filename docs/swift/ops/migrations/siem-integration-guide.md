---
schema: 1
title: "Document SIEM log integration and detection scenarios"
impact: none
configuration: none
configuration_reason: "This contribution changes only operator documentation; no deployment setting, chart value, or runtime default changes."
no_action_reason: "Existing deployments and data are unchanged; the guide is available without a special upgrade or migration step."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required for the upgrade. The guide describes optional SIEM integration work for deployments that choose to collect these events.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Open `docs/swift/platform/SIEM-INTEGRATION.md` and confirm that the collection route, Entra ID sources, and twelve detection scenarios are present.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The guide does not configure a relay, Entra export, or SIEM rule. Those integrations require separate deployment validation.

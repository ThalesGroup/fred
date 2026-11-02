---
schema: 1
title: "Return capability routes with execution preparation"
impact: none
configuration: none
configuration_reason: "A response field is derived from the approved public base; no configuration is read or added."
no_action_reason: "The change ships with the normal deployment and stores no new data."
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

Open a conversation with a capability that ships a router: the preparation response lists it in capability_base_urls.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.

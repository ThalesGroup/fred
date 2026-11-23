---
schema: 1
title: "Show one chat card per object in a message"
impact: none
configuration: none
configuration_reason: "Only the frontend chat rendering changes; no backend contract, chart value or configuration file is touched."
no_action_reason: "The frontend now hides earlier versions of an object already present in the same message; stored conversations and parts are unchanged."
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

Ask an agent with the writable document capability to create a document and revise it twice in the same answer: the message shows one card for the document, its last version. Web citations still show one chip each.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Only parts within one message are merged; an object updated across several answers still shows one card per answer.

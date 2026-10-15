---
schema: 1
title: "Keep contact support on platform refusal, not team invitations"
impact: none
configuration: none
configuration_reason: "Only frontend presentation changes; the existing contactSupportLink setting is unchanged."
no_action_reason: "No API, data or permission change is required; the new presentation ships with a normal frontend deployment."
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. The configured support destination still
serves platform access refusal and admission-verification errors.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Open a team invitation link and verify that its invitation, loading, invalid-link
and temporary-error states have no contact-support action. A person denied normal
platform access should still see "Request access" when a support link is
configured.

## Rollback

Use the normal frontend rollback procedure; no data migration is involved.

## Limitations

An invalid invitation still needs a new link from its inviter; the page does not
offer a support destination for that case.

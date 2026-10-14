---
schema: 1
title: "Friendlier access-denied and team invitation pages"
impact: none
configuration: none
configuration_reason: "Frontend presentation and wording only; the pages read the existing siteDisplayName and contactSupportLink frontend properties, whose keys and defaults do not change."
no_action_reason: "No API, stored data, permission or chart value changes; the new pages take effect with a normal frontend deployment."
---
## Applicability

Fred deployments with platform access filtering or team invitation links.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

The platform name shown at the top of these pages is the existing
`siteDisplayName` frontend property ("Fred" when unset). "Request access" on
the access-denied page opens the existing `contactSupportLink` property and is
hidden when that property is empty.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Open a revoked or expired invitation link (`/join/<token>`): the page says the
invitation link is no longer valid and offers no retry button. Sign in with an
account that is not admitted while filtering is on: the access-denied page
shows the platform name, the account's name and email, and two numbered steps.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

An invitation link that is no longer valid does not say whether it expired or
was revoked or suspended, nor which team it led to.

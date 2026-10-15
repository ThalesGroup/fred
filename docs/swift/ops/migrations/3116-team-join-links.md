---
schema: 1
title: "Team admins share an invite link with people who already have platform access"
impact: minor
configuration: none
configuration_reason: "The feature uses the existing platform-access tables and team permissions; no chart value, secret or environment variable is added or changed."
---

## Applicability

Fred deployments where platform access is available (authenticated users,
machine-to-machine authentication and ReBAC enabled). Team admins there get an
**Invite link** action in the team Members tab; elsewhere the action is hidden.
Platform administrators' Free-team links keep their behavior.

## Prerequisites

Back up the shared control-plane database, as for any schema migration.

## Configuration

No configuration changes are required.

## Upgrade

Apply the control-plane Alembic head before deploying the new control plane.
This contribution's revision, `c3a7e5d9f1b2`, adds `kind` (server default
`free`) and `paused` (server default `false`) to `platform_access_links`, so
every existing link stays an active Free-team link. If the release includes
later control-plane revisions, run the chain once to its head.

## Validation

As a team admin, open the Members tab, choose **Invite link** and enable the
invitation. Open the link with another account that has platform access: it
joins the team as a member. Turn the switch off: the same link now shows "This
invitation link is no longer valid"; turn it on again and it works. With
platform filtering on, an account that is not admitted lands on the
platform-access refusal page. The platform administrators' Free-link history
does not list the team link.

## Rollback

Back up the database before downgrading. Downgrading `c3a7e5d9f1b2` deletes
every team invite link before dropping both columns; Free links are kept.
Memberships granted through team links are not removed.

## Limitations

A team link only adds people who are already admitted to the platform; it never
admits anyone. A team has one link, with no expiry or use cap; it stays valid
after its creator stops being a team admin, until a team admin pauses or
replaces it.

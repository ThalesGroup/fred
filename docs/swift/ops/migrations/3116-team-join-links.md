---
schema: 1
title: "Team invite links, and Free admission limited to people who joined through a Free link"
impact: minor
configuration: none
configuration_reason: "The feature uses the existing platform-access tables and team permissions; no chart value, secret or environment variable is added or changed."
---

## Applicability

Fred deployments where platform access is available (authenticated users,
machine-to-machine authentication and ReBAC enabled). Team admins there get an
**Invite link** action in the team Members tab; elsewhere the action is hidden.

Deployments that use **Link access** (Free) on teams with platform filtering
enabled are affected by an admission change: a Free team now admits only the
people who enrolled through one of its Free links, not every member. Authorized
teams still admit every member.

## Prerequisites

Back up the shared control-plane database, as for any schema migration.

If filtering is enabled and some teams use Link access, identify the members of
those teams who did not enroll through a Free link: people added by hand, and
people who joined before Fred recorded Free-link joins. After the upgrade they
lose the Free source and are refused unless another source applies. Before
upgrading, decide for each such person or team: grant individual exceptions in
the Platform access whitelist, authorize the team (every member admitted), or
let them re-enroll through a Free link after the upgrade.

## Configuration

No configuration changes are required.

## Upgrade

Apply the control-plane Alembic head before deploying the new control plane
and the other backends: every backend that checks platform access now requires
`platform_access_links` and `platform_access_link_joiners` at startup. This
contribution's revision, `c3a7e5d9f1b2`, adds `kind` (server default `free`) and
`paused` (server default `false`) to `platform_access_links`, so every existing
link stays an active Free-team link. If the release includes later
control-plane revisions, run the chain once to its head.

## Validation

As a platform administrator, open the activation preview: members of Free teams
appear with a Free source only if they enrolled through a Free link. As a team
admin, open the Members tab, choose **Invite link** and enable the invitation.
Open the link with another account that has platform access: it joins the team
as a member and lands on the team page. Turn the switch off: the same link now
shows "This invitation link is no longer valid"; turn it on again and it works.
With filtering on, an account that is not admitted lands on the platform-access
refusal page.

## Rollback

Back up the database before downgrading. Downgrading `c3a7e5d9f1b2` deletes
every team invite link before dropping both columns; Free links are kept.
Memberships granted through team links are not removed. An older release
derives Free admission from any membership again.

## Limitations

A team link only adds people who are already admitted to the platform; it never
admits anyone. A team has one link, with no expiry or use cap; it stays valid
after its creator stops being a team admin, until a team admin pauses or
replaces it. Cleaning up revoked or expired Free-link history deletes its join
records and withdraws the Free source of the people who joined through those
links; they stay team members.

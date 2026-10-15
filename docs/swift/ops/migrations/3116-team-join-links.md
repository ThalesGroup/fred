---
schema: 1
title: "Team admins share join links with people who already have platform access"
impact: minor
configuration: none
configuration_reason: "The feature uses the existing platform-access tables and team permissions; no chart value, secret or environment variable is added or changed."
---

## Applicability

All Fred deployments. Team admins get an **Invite link** action in the team
Members tab. Platform administrators' Free-team links keep their behavior.

## Prerequisites

Back up the shared control-plane database, as for any schema migration.

## Configuration

No configuration changes are required.

## Upgrade

Apply the control-plane Alembic head before deploying the new control plane.
This contribution's revision, `c3a7e5d9f1b2`, adds a `kind` column to
`platform_access_links` with server default `free`, so every existing link stays
a Free-team link. If the release includes later control-plane revisions, run
the chain once to its head.

## Validation

As a team admin, create an invite link from the Members tab and open it with
another account that has platform access: it joins the team as a member and
appears in the link's joiners. With platform filtering on, open the same link
with an account that is not admitted: it lands on the platform-access refusal
page and does not join. The platform administrators' Free-link history does
not list the team link.

## Rollback

Back up the database before downgrading. Downgrading `c3a7e5d9f1b2` deletes
every team join link (and their join history) before dropping the column; Free
links are kept. Memberships granted through team links are not removed.

## Limitations

A team link only adds people who are already admitted to the platform; it never
admits anyone. Links have no use cap and stay valid after their creator stops
being a team admin, until they expire or a team admin revokes them.

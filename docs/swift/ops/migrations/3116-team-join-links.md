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

Free-team membership is stored in ReBAC (OpenFGA), not in SQL, so compare two
lists. Before upgrading, list the people the database records as Free-link
joiners (every existing link is a Free link at this point):

```sql
SELECT t.id AS team_id, t.name, j.user_id
FROM teammetadata t
JOIN platform_access_links l ON l.team_id = t.id
JOIN platform_access_link_joiners j ON j.link_id = l.id AND j.deleted_at IS NULL
WHERE t.platform_access_free
ORDER BY t.id;
```

Then list each Free team's members (team Members tab, or the `member` tuples of
`team:<team_id>` in OpenFGA). Members missing from the SQL result lose the Free
source. After the upgrade, the activation preview shows them without a Free
source. Teams with `platform_access_free` and no row in the result admit nobody
through Free any more and no longer count as an admission source when
filtering is enabled.

If the backends use different database roles, every backend that checks
platform access (control plane, knowledge-flow, fred-agents and other runtimes,
anything using the ReBAC SDK with platform access) now reads
`platform_access_links` and `platform_access_link_joiners` at startup and on
filtered requests. Grant read access to each such role before deploying:

```sql
GRANT SELECT ON platform_access_links, platform_access_link_joiners TO <backend_role>;
```

A table-level grant also exposes `platform_access_links.token`, the reusable
plaintext link token. To avoid that, grant only the columns the readers use:

```sql
GRANT SELECT (id, team_id, kind) ON platform_access_links TO <backend_role>;
GRANT SELECT (link_id, user_id, deleted_at) ON platform_access_link_joiners TO <backend_role>;
```

The control-plane role keeps full access, as it owns both tables. A backend
whose role cannot read them refuses to start and logs a WARNING naming the
error type and SQLSTATE (`42501` for a missing privilege).

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

Development databases only: an earlier, unreleased version of `c3a7e5d9f1b2`
added `kind` alone. It was edited in place to also add `paused`. A database that
ran the earlier version must run `alembic downgrade 24c2f88374fe` then
`alembic upgrade head` (this deletes its team invite links), or add the column:
`ALTER TABLE platform_access_links ADD COLUMN paused BOOLEAN NOT NULL DEFAULT false;`.

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
links; they stay team members. Removing a person from a team, or the person
leaving it, deletes their join records on that team's Free links: being added
back by hand or through a team invite link does not restore the Free source,
only a new Free enrollment does.

Impact level: `minor` because deployments using Free-team admission need a
targeted review and remediation before upgrading. The change can refuse
previously admitted members without another access source, but it does not
replace the admission model or require an incompatible data migration.

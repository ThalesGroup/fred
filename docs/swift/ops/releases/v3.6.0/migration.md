# Migration guide — v3.6.0

Upgrade from: `code/v3.5.0`
Operational impact: **minor** (minimum version: `3.6.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Coordinated v3.6.0 upgrade and rollback

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.6.0/docs/swift/ops/migrations/000-v3-6-0-release-preparation.md)

### Applicability

Upgrade from Fred v3.5.0 to v3.6.0 with paired code and chart releases. This
sequence combines the procedures below and adds no migration of its own. Python
package publication remains a separate maintainer operation.

### Prerequisites

Back up the shared control-plane database and preserve the previous images,
chart and values. Rehearse the rollout and rollback with private overlays.

If platform filtering is enabled and any team uses Link access (Free), compare
that team's current members with its recorded Free-link joiners as described in
the team invite link note. Decide who needs an individual exception, an
authorized team, or a new Free enrollment before deploying new readers.

For each Knowledge Base pod, identify its publishing client and exact prefix.
Review existing published definitions and decide which publishers to register.
If participating backends use separate database roles, identify the roles that
need read access to the platform access link tables.

### Configuration

Register Knowledge Base publishers in the Fred chart values before deploying
the new control plane. The list stays empty on deployments without Knowledge
Base pods. Keep the existing `security.user_directory` selection. Release
preparation adds no other setting; `configuration_prod.yaml` is for local Docker
Compose, not the production reference.

### Upgrade

#### Required coordinated rollout

1. Apply the Free-team admission decisions before the upgrade where continuous
   access is required. A person left to re-enroll through a Free link may be
   refused in the meantime.
2. Apply the control-plane Alembic head with the new migration image before
   starting updated backends. Revision `c3a7e5d9f1b2` adds `kind` and `paused`
   to existing links; the Fred chart's migration hooks are disabled by default,
   so run the deployment's migration job or equivalent command explicitly.
3. Grant each separate backend database role the read access specified in the
   team invite link note, after the new columns exist and before starting the
   updated services. Column grants avoid exposing reusable link tokens.
4. Deploy the matching Fred chart, updated control plane and frontend with the
   registered Knowledge Base publishers. The control plane must start before
   Knowledge Base pods replay publication. The frontend and control plane must
   both be updated before using the revised user-directory controls.
5. Deploy updated Knowledge Flow and agent runtime pods, then Knowledge Base
   pods. Validate admission and publication before resuming normal traffic.

#### Optional activation and user data

- If platform filtering is still off, use the updated configured-directory
  lookup when reviewing the initial import and whitelist before activating it.
  A previously completed import stays completed; add missing identities through
  **Add users** instead of expecting another import.
- No document re-ingestion or search reindex is required. Previously orphaned
  data and partially failed unlinks are not repaired by this release.

### Validation

Confirm the control-plane migration head, startup of every participating
backend, and admission for affected Free-team members. Check that directory
search finds the intended identities, that team invitation links admit only
people who already have platform access, and that every registered Knowledge
Base pod publishes successfully. Check a current document search and a large
folder's inventory and deletion using the linked validation instructions.

### Rollback

Stop affected services before changing schema or images. Restore the previous
chart revision with its own values; if reusing current values with the older
chart, remove `knowledge_bases.publishers` first. An in-place downgrade of
`c3a7e5d9f1b2` deletes team invite links and restores the older, broader Free
admission rule. Use the database backup for a coordinated rollback when old
images have not been validated against the current schema and data. Recheck
platform admission before reopening traffic.

### Limitations

The chart does not enforce this deployment order. Private database grants,
overlays and Knowledge Base client identities require operator validation.
Stored Knowledge Base definitions are not revoked automatically. The paired
Fred tags do not publish Python packages.

## Use canonical document inventory for folder reads and deletion

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.6.0/docs/swift/ops/migrations/2845-complete-folder-inventory.md)

A normal Knowledge Flow image deployment applies the fix without migration or reindexing.

See the source note for applicability, validation and rollback.

## Enforce current document scope in corpus search

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.6.0/docs/swift/ops/migrations/3091-document-access-validation.md)

Normal Knowledge Flow deployment applies the search restriction without a schema migration or reindex.

See the source note for applicability, validation and rollback.

## Team invite links, and Free admission limited to people who joined through a Free link

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.6.0/docs/swift/ops/migrations/3116-team-join-links.md)

### Applicability

Fred deployments where platform access is available (authenticated users,
machine-to-machine authentication and ReBAC enabled). Team admins there get an
**Invite link** action in the team Members tab; elsewhere the action is hidden.

Deployments that use **Link access** (Free) on teams with platform filtering
enabled are affected by an admission change: a Free team now admits only the
people who enrolled through one of its Free links, not every member. Authorized
teams still admit every member.

### Prerequisites

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

### Configuration

No configuration changes are required.

### Upgrade

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

### Validation

As a platform administrator, open the activation preview: members of Free teams
appear with a Free source only if they enrolled through a Free link. As a team
admin, open the Members tab, choose **Invite link** and enable the invitation.
Open the link with another account that has platform access: it joins the team
as a member and lands on the team page. Turn the switch off: the same link now
shows "This invitation link is no longer valid"; turn it on again and it works.
With filtering on, an account that is not admitted lands on the platform-access
refusal page.

### Rollback

Back up the database before downgrading. Downgrading `c3a7e5d9f1b2` deletes
every team invite link before dropping both columns; Free links are kept.
Memberships granted through team links are not removed. An older release
derives Free admission from any membership again.

### Limitations

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

## Show the case-sensitive switch in platform access rules

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.6.0/docs/swift/ops/migrations/3117-show-platform-access-case-switch.md)

The access rule API and saved policies are unchanged; the switch appears after a normal frontend deployment.

See the source note for applicability, validation and rollback.

## Keep contact support on platform refusal, not team invitations

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.6.0/docs/swift/ops/migrations/3119-remove-invitation-support-link.md)

No API, data or permission change is required; the new presentation ships with a normal frontend deployment.

See the source note for applicability, validation and rollback.

## Amend platform access directory guidance

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.6.0/docs/swift/ops/migrations/3122-platform-access-directory.md)

### Applicability

This note amends the directory-dependent instructions in [2965-platform-access-planning.md](https://github.com/ThalesGroup/fred/blob/code/v3.6.0/docs/swift/ops/migrations/2965-platform-access-planning.md), specifically Upgrade steps 4 and 5 and their validation. It applies to authenticated Fred deployments using platform access, especially Keycloak deployments with completed initial imports. Follow the other instructions in note 2965 as published.

### Prerequisites

Keycloak mode requires the existing Keycloak administration service account to read users. Local mode continues using the Fred database. No database migration is required.

### Configuration

Keep the existing `security.user_directory` selection: `keycloak` for Keycloak identities, `local` for Fred's local identities. The two directories are alternative modes, not a combined directory.

### Upgrade

Deploy the updated control plane and frontend together before applying these amendments to note 2965:

1. **Step 4, Import existing users:** Before the first import, preview and import human identities from the configured directory. Keycloak mode includes accounts created directly in Keycloak and federated accounts already known to Keycloak after their first login. Local mode uses Fred's `users` table. The one-time import and removable exception behavior in note 2965 still applies. A completed import does not run again: it neither adds Keycloak accounts missed by the earlier Fred-only snapshot nor restores exceptions administrators removed. For an existing completed import, compare intended directory users with the whitelist and use **Add users** for missing exceptions before activating filtering.
2. **Step 5, Add individual exceptions:** Replace "existing Fred users" with "existing identities in the configured directory." Search and select Keycloak identities in Keycloak mode or Fred users in local mode. Individual exceptions and their identifiers remain in Fred; the whitelist displays current profiles from the selected directory. An exception whose directory profile has disappeared remains visible by its ID and can be removed. Team exceptions and their membership behavior are unchanged.
3. **Step 5, Activation review:** The population review now uses the configured directory. Review its Allowed, Blocked and Verification unavailable results before confirming as described in note 2965.

### Validation

For the amended steps 4 and 5, search for an account created directly in Keycloak but not yet used in Fred, add it to the whitelist, and confirm its current username and names appear. Confirm a federated account already known to Keycloak also appears. In local mode, confirm searches and grants use Fred users. Check the initial-import preview before the first import and the population review before activation. Unavailable directory reads must produce an error instead of an empty population. Retain the other validation checks in note 2965.

### Rollback

Roll back the control plane and frontend together. Persisted exceptions and T0 completion remain in SQL. An older control plane can display newly materialized Keycloak reference rows, but it will again use local Fred profiles and cannot find other Keycloak-only accounts.

### Limitations

The initial import is a fixed snapshot of identities returned by the selected directory, not a scan of the upstream Active Directory. Rule matches still require fresh verified claims observed by Fred; a Keycloak profile alone cannot prove them.

## Prepare independently versioned Python packages for releases

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.6.0/docs/swift/ops/migrations/independent-python-release-versions.md)

Existing deployments need no action because this change prepares future Python package releases without changing running code or data.

See the source note for applicability, validation and rollback.

## Knowledge Base publication requires operator-registered publishers

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.6.0/docs/swift/ops/migrations/register-knowledge-base-publishers.md)

### Applicability

Deployments that run Knowledge Base pods. Until now any service identity could
publish a Knowledge Base definition, and the first client to publish under a
prefix owned it. From this release the Control Plane only accepts publications
from clients listed in `knowledge_bases.publishers`, each under the one prefix
listed for it. The list is empty by default: a deployment that does not list
its Knowledge Base clients sees their next publication refused with HTTP 403:
the pod's publish step, run once per deployment, exits with an error.

Deployments without Knowledge Base pods need no action: the empty default
changes nothing for them.

### Prerequisites

For each Knowledge Base pod, know its confidential client id (the token's
`azp`) and the prefix it publishes under (its `knowledge_base.prefix`
setting). No IAM, OpenFGA or database change is needed.

### Configuration

Before upgrading, list each Knowledge Base client and its prefix in the Fred
chart values, under
`applications.control-plane-backend.configuration.knowledge_bases.publishers`:

```yaml
knowledge_bases:
  publishers:
    - client_id: kb-acme
      prefix: acme.kb
```

A client may hold several entries. A prefix may appear only once, and no
registered prefix may cover another (`acme` and `acme.kb`): the Control Plane
refuses to start and names both entries. The prefix must be exactly the one the
pod publishes under, not a parent or a child of it.

### Upgrade

1. Add the `publishers` list above to the Control Plane values.
2. In Admin > Features > Knowledge Bases, review the published definitions.
   A definition already stored by a client you do not list stays in the
   catalog: it stays usable by the teams it is enabled for, but its pod can no
   longer republish it. Disable it for those teams if it should not be there.
3. Deploy the Control Plane normally, then deploy Knowledge Base pods as
   usual: each deployment replays its publication.

A prefix already bound to one client in the catalog stays bound to it: listing
it for another client does not move it, and that client's publication is
refused.

### Validation

- The Control Plane starts with the new values.
- Each Knowledge Base pod's publish step succeeds, and its definition appears
  in Admin > Features > Knowledge Bases.
- A refused publication answers 403 with a detail naming the client and
  `knowledge_bases.publishers`.

### Rollback

`helm rollback` restores the previous revision with its own values and needs
nothing more. To deploy the previous chart version with your current values
instead, remove `knowledge_bases.publishers` first: the previous chart's values
schema refuses the unknown key. No data is migrated, and publication returns to
the previous rule (the first client to publish under a prefix owns it).

### Limitations

Registration controls who publishes, not what a published pod may write: one
client still serves every team a definition is enabled for. Definitions stored
before the upgrade are not revoked automatically. The upgrade has been checked
with unit tests and configuration validation, not rehearsed on a production
deployment.

## Restore the UI settings theme tiles' look

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.6.0/docs/swift/ops/migrations/ui-settings-theme-tiles-look.md)

Visual change to one admin page; theme settings, archive themes and the API are untouched.

See the source note for applicability, validation and rollback.

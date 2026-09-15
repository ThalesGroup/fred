## Why

Team administrators are part of the security chain: they decide who belongs to a team, delegate resource administration and answer for its usage. Today a user holds full `team_admin` authority the moment the relation is written, without ever being told what the role commits them to, and nothing records that they agreed. Each deployment needs to state those responsibilities in its own words and keep proof that every administrator accepted them before acting as one (issue #2658).

## What Changes

- New legal markdown document, the team administrator charter (`team-admin-charter.md` and `team-admin-charter.fr.md`), served and overridable like the terms of use: a generic template ships in the frontend image, a deployment replaces it from its theme archive.
- New control-plane setting `app.team_admin_charter_version`. Unset means the feature is off and nothing below applies.
- New OpenFGA relation `team.pending_team_admin`, part of `team_member` and nothing else. A nominated admin who has not accepted the configured version gets it instead of `team_admin`, so they hold a member's rights only, in every service.
- `POST /control-plane/v1/team-admin-charter` records the acceptance (audited) and turns every `pending_team_admin` of the caller into `team_admin`. One acceptance covers every team. `GET` on the same path returns when the caller accepted the configured version.
- At startup, when the configured version changed, the control-plane moves admins between `team_admin` and `pending_team_admin` to match.
- Frontend: the charter page replaces the pages of a team where the user is a pending admin while the team has no accepted admin, and a notice leads to it otherwise; a Responsibilities section in team settings, where pending admins accept; an "Admin (pending)" chip in the member list.
- Refactor: `GcuPage` and `GdprPage` share one markdown loading hook, which the charter reuses.

Not breaking: with the setting unset, behaviour is unchanged. Turning it on for an existing deployment makes every existing administrator pending until they accept, which is the intent.

## Capabilities

Capabilities here are OpenSpec spec domains (`openspec/specs/<name>/`), unrelated to Fred agent capabilities.

### New Capabilities

- `team-admin-charter`: the charter document and its override, the pending admin relation, acceptance and promotion, reconciliation on version change, and the team pages that lead a pending admin to accept.

### Modified Capabilities

None.

## Impact

- fred-core: `schema.fga` and its compiled JSON, `RelationType.PENDING_TEAM_ADMIN`, `lookup_resources` accepting a relation.
- Control-plane backend: configuration model, two tables and their migrations, nomination writes in `teams/service.py` and the importer, the acceptance endpoint, the startup reconciliation.
- Frontend: charter gate and page, Responsibilities section, role chips and labels, markdown hook refactor, regenerated `controlPlaneOpenApi.ts`, i18n.
- Theme tooling: `build-theme-archive.sh` and the frontend README list the new document.
- Docs: `CONTROL-PLANE-PRODUCT-CONTRACT.md` §54, `authz-endpoint-matrix.yaml`, `REBAC.md`, `TERMS_OF_USE.md`.

## Why

Team administrators are part of the security chain: they decide who belongs to a team, delegate resource administration and answer for its usage. Today a user holds full `team_admin` authority the moment the relation is written, without ever being told what the role commits them to, and nothing records that they agreed. Each deployment needs to state those responsibilities in its own words and keep proof that every administrator accepted them before acting as one (issue #2658).

## What Changes

- New legal markdown document, the team administrator charter (`team-admin-charter.md` and `team-admin-charter.fr.md`), served and overridable exactly like the terms of use: a generic template ships in the frontend image, a deployment replaces it from its theme archive.
- New control-plane setting `app.team_admin_charter_version`. Unset means the feature is off and nothing below applies.
- The control-plane records each user's acceptance of a charter version in the database, and exposes two endpoints: one tells the caller whether they must accept, the other records the acceptance and emits an audit event.
- A `team_admin` who has not accepted the current version is denied the administrator-only team permissions (`can_update_info`, `can_administer_members`, `can_administer_editors`, `can_administer_analysts`, `can_administer_admins`), and those permissions are left out of the team permissions returned to the frontend. The `team_admin` relation itself is still granted, revoked and counted as today.
- One acceptance per user covers every team they administer. Changing the configured version requires every administrator to accept again.
- Frontend: a pop-up on the pages of a team the user administers, never on the home page, while their acceptance is pending (Accept or Later), and a "Responsibilities" section in team settings to read the charter and accept it.
- Refactor: `GcuPage` and `GdprPage` share one markdown loading hook, which the charter reuses.

Not breaking: with the setting unset, behaviour is unchanged. Turning it on for an existing deployment suspends every existing administrator's rights until they accept, which is the intent.

## Capabilities

Capabilities here are OpenSpec spec domains (`openspec/specs/<name>/`), unrelated to Fred agent capabilities.

### New Capabilities

- `team-admin-charter`: the charter document and its override, acceptance recording, the rule that administrator-only team permissions require acceptance of the current version, and the prompts that lead an administrator to accept.

### Modified Capabilities

None. `frontend-package-archives` is unrelated.

## Impact

- Control-plane backend: configuration model, a new acceptance table and its Alembic migration, the team permission check and permission projection in `teams/service.py`, a new router for the two endpoints.
- No change to the OpenFGA model, to fred-core, to knowledge-flow or to fred-runtime: every administrator-only team permission is checked in the control-plane only.
- Frontend: the pop-up, the team settings section, the markdown hook refactor, the regenerated `controlPlaneOpenApi.ts`, i18n.
- Theme tooling: `build-theme-archive.sh` and the frontend README list the new document.
- Docs: a dated section in `CONTROL-PLANE-PRODUCT-CONTRACT.md`, `authz-endpoint-matrix.yaml`, the team admin section of `REBAC.md`, `TERMS_OF_USE.md`.

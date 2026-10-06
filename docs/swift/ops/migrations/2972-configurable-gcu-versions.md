---
schema: 1
title: "Persist configurable CGU acceptance per version"
impact: minor
configuration: none
configuration_reason: "The existing app.gcu_version string and charter settings retain their keys, defaults and optional behavior."
---
## Applicability

Deployments upgrading control-plane and the backends sharing the Fred users
table, whether or not CGU gating is currently enabled.

## Prerequisites

Back up the shared database. Deploy backend versions together: the old ORM
expects an enum, while the new version reads text and per-version acceptance.

## Configuration

No configuration changes are required. Existing `v1` stays valid. Use a new,
case-sensitive `app.gcu_version` identifier only when publishing new terms.
Configure the same active CGU version in all enforcing backends.

## Upgrade

1. Stop old control-plane, knowledge-flow and agent backends that read the shared
   users table. Do not mix old and new readers during this migration.
2. Run control-plane `alembic upgrade head` with the new release. Revision
   `a7e9c2d41063` converts `users.gcuVersionAccepted` from enum `V1` to text `v1`,
   creates `user_gcu_acceptances` and seeds it from existing acceptance data.
3. Start updated backends and deploy the regenerated frontend. No changes to the
   other backend migration trees are needed.

## Validation

Confirm legacy accepted versions read as `v1` and acceptance dates and storage
counters are preserved. On isolated validation data, configure an unaccepted
`v2`: protected human requests return 403 until `POST /gcu` succeeds, then
`GET /user` returns `cguValidated: "v2"`. Return to already accepted `v1` and
confirm access needs no new acceptance. Default-team enrollment must not repeat.

## Rollback

Stop updated readers before downgrade. Downgrade can restore the old enum only
when every stored acceptance, including history, is `v1` or null. It refuses
other versions before changing data. Once a newer version is accepted, restore
a coordinated pre-upgrade backup or make a separate, explicit data decision;
do not delete consent records to bypass the guard.

## Limitations

Historical timestamps missing in legacy data remain null; they are not invented.
Only acceptance evidence present at upgrade can be seeded. CGU history retains
new acceptances after upgrade. External consumers of `UserRow.gcuVersionAccepted`
must now read a string rather than `.value`. `GcuVersionsType.V1` remains accepted
as legacy input to the user store. Custom `BaseUserStore` implementations must
implement `has_accepted_gcu_version` using per-version evidence.

The administrator charter already has per-version acceptance. Its team-scoped
gate and startup reconciliation remain unchanged; changing a charter version
requires control-plane restart and refreshed team data.

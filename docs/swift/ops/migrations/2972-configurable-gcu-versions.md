---
schema: 1
title: "Store the latest configurable CGU acceptance in users"
impact: minor
configuration: none
configuration_reason: "The existing app.gcu_version string and charter settings retain their keys, defaults and optional behavior."
---
## Applicability

Deployments upgrading control-plane and the backends sharing the Fred users
table, whether or not CGU gating is currently enabled.

## Prerequisites

Back up the shared database. Deploy backend versions together: the old ORM
expects an enum, while the new version reads text. Back up any GCU history introduced by an earlier
checkout of this PR before the corrective revision removes it.

## Configuration

No configuration changes are required. Existing `v1` stays valid. Use a new,
case-sensitive `app.gcu_version` identifier only when publishing new terms.
Configure the same active CGU version in all enforcing backends.

## Upgrade

1. Stop old control-plane, knowledge-flow and agent backends that read the shared
   users table. Do not mix old and new readers during this migration.
2. Run control-plane `alembic upgrade head` with the new release. Revision
   `a7e9c2d41063` converts `users.gcuVersionAccepted` from enum `V1` to text `v1`,
   creates the earlier PR history table, then `e6b8d2a41074` removes that table.
   The final schema keeps only the existing user columns. If `a7e9c2d41063` has
   already been applied, its enum conversion is skipped; Alembic runs the missing
   identity revision and the corrective revision. Both PR revisions are
   kept because the earlier PR migration has already been executed locally;
   the applied revision and its parent are not rewritten. The chain is
   `c4d7e2a91b30 -> {a7e9c2d41063, b4e8d2a9c613} -> e6b8d2a41074`,
   with one head. The corrective revision also joins the immutable OIDC identity
   migration newly merged into `swift`, so either already-applied branch can
   upgrade without stamping or skipping the other branch's schema changes.
3. Start updated backends and deploy the regenerated frontend. No changes to the
   other backend migration trees are needed.

## Validation

Confirm legacy accepted versions read as `v1` and acceptance dates and storage
counters are preserved. On isolated validation data, configure an unaccepted
`v2`: protected human requests return 403 until `POST /gcu` succeeds, then
`GET /user` returns `cguValidated: "v2"`. Return configuration to `v1` and
confirm access requires acceptance again because the stored version is `v2`.
Default-team enrollment must not repeat. Confirm `user_gcu_acceptances` is
absent and the current version/timestamp in `users` survives the correction.

## Rollback

Stop updated readers before downgrade. Downgrading `e6b8d2a41074` recreates the
intermediate history table from current user acceptances only; removed older
history needs the pre-correction backup. Downgrading `a7e9c2d41063` can restore
the old enum only when every stored acceptance is `v1` or null; it refuses other
versions before changing data. If a current newer acceptance must be retained,
restore a coordinated pre-upgrade backup or make a separate, explicit data
decision. Do not delete consent records to bypass the guard.

## Limitations

Historical timestamps missing in legacy data remain null; they are not invented.
Only the latest CGU version and timestamp are retained, matching the original
GCU policy. The corrective migration intentionally removes earlier PR history. External consumers of `UserRow.gcuVersionAccepted`
must now read a string rather than `.value`. `GcuVersionsType.V1` remains accepted
as legacy input to the user store. The existing user-store interface is retained.

The administrator charter already has per-version acceptance. Its team-scoped
gate and startup reconciliation remain unchanged; changing a charter version
requires control-plane restart and refreshed team data.

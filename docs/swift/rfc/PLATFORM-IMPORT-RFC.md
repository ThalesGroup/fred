# RFC — Platform Import/Export (swift-native contract)

**ID:** MIGR-05 · **Status:** done — see `id-legend.yaml`. Closed out 2026-07-25.
**Owner:** Dimitri · **Surface:** control-plane-backend (`import_export/`)
**Extends:** [`TASK-EVENT-STREAM-RFC.md`](TASK-EVENT-STREAM-RFC.md) (task/event infra).
**Backlog:** [`KEA-MIGRATION-BACKLOG.md`](../backlog/KEA-MIGRATION-BACKLOG.md) §0bis.

---

## Closed out — see the canonical contract

This RFC shipped as designed: swift-native atomic import/export/reset
(baseline 2026-07-16), the kea-import path (agent prompt/tuning transfer,
chat-context→prompt migration, OpenFGA tuple restore with role
transformation, teams/platform roles from the Keycloak realm export,
identity reconciliation by username) and the standalone `realm_file` upload +
full-teardown `POST /reset-full` for the production cutover (both 2026-07-24).

The full, current, load-bearing contract — endpoint list, bundle/manifest
format, `document_uid` join-key rule, stage-reconciliation rule, `users.json`
two-phase provisioning, kea transform rules, teardown ordering — now lives in
**[`CONTROL-PLANE-PRODUCT-CONTRACT.md` §27](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md#27-contract-notes--migr-05-platform-importexportreset-finalized-2026-07-25)**.
This file stays only as a closed-out design record; design deliberation,
alternatives considered, and live-validation evidence are in
`git log -p -- docs/swift/rfc/PLATFORM-IMPORT-RFC.md`.

**Remaining open item:** MIGR-05.17 — user-state/GCU-row migration,
deliberately out of #1954's scope (see `KEA-MIGRATION-BACKLOG.md` §0bis). Not
part of this contract; tracked as its own future item.

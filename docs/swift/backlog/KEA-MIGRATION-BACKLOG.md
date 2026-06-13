# Kea→Swift Migration Backlog

Epic: **MIGR-00** — Kea→Swift production cutover

This backlog tracks the workstreams needed to cut over from Kea (production) to
Swift (new architecture). Owner of each sub-item = the person doing the work.
Set `owner:` in `id-legend.yaml` when a ticket is picked up.

---

## §0 Platform prerequisite — identity bootstrap (MIGR-04)

Must be completed and verified **before** any application data (Postgres `fred_kea`,
OpenFGA tuples) is imported into a target environment. Owned by platform/ops.

- [ ] **MIGR-04** — Bootstrap the target (S3NS) Keycloak by exporting on-prem users **with
  their `id` (UUID)** and importing them so each user's `sub` is preserved across environments.
  — *Fred keys all ownership and OpenFGA tuples on the Keycloak `sub`; a fresh Keycloak mints
  new UUIDs and orphans every user. SSO brokering alone preserves nothing.*
  — owner: platform/ops (Sébastien)
  — runbook: [`ops/KEYCLOAK-IDENTITY-BOOTSTRAP-S3NS.md`](../ops/KEYCLOAK-IDENTITY-BOOTSTRAP-S3NS.md)
  — acceptance: one real user logs into S3NS via SSO and their token `sub` equals their on-prem UUID
  — note: the application team rehearses the data migration locally with a **single shared
  Keycloak** (kea + swift), which faithfully models the post-bootstrap state; it does not test
  the bootstrap itself, which is why this item is owned by platform/ops.

---

## §1 Cherry-picks and code adaptations (MIGR-01)

Commits or features from the Kea codebase that need to be cherry-picked or
re-implemented for Swift. For each item, note the source commit/PR and what
adaptation is needed (e.g. API contract change, dependency replacement).

Legend: **[needed]** = blocking for production cutover · **[good-to-have]** = quality / dev-experience

### Needed

- [ ] **MIGR-01.01** — Upload warning banner on document upload drawer and chat attachments
  — *SSI requirement: prevent accidental upload of sensitive files*
  — source: [#1597](https://github.com/ThalesGroup/fred/commit/34ea331a3) `34ea331` · [#1634](https://github.com/ThalesGroup/fred/commit/7b6320bc3) `7b6320b`
  — adaptation: check if chat attachment component exists in Swift; both commits may need to be applied

- [ ] **MIGR-01.02** — Fix GCU acceptation button on specific resolutions + placement fixes (delete agent button, add-member popover, select popover)
  — *GCU acceptance was broken on some screen sizes, reported in production*
  — source: [`4fc90cc`](https://github.com/ThalesGroup/fred/commit/4fc90cc8d)

- [ ] **MIGR-01.03** — Dockerfile base image bumps: Node + nginx
  — *CVE fixes requested by SSI on frontend image*
  — source:
    - [ ] [#1635](https://github.com/ThalesGroup/fred/commit/a41540422) `a414404`
    - [X] [#1647](https://github.com/ThalesGroup/fred/commit/38d4880ce) `38d4880`

- [ ] **MIGR-01.04** — Add `created_at` / `updated_at` timestamps to all ORM tables
  — *Required to verify production KPIs*
  — source: [#1612](https://github.com/ThalesGroup/fred/commit/e2be3fb7c) `e2be3fb`

- [ ] **MIGR-01.05** — Migrate to trunk-based development with unified release tag
  — *Rename main branch to `main`; single tag triggers a release*
  — source: [#1622](https://github.com/ThalesGroup/fred/commit/67916e113) `67916e1`

- [X] **MIGR-01.06** — Garbage-collect uploaded files after processing to prevent `/tmp` clogging
  — *Prevents disk exhaustion in the Temporal worker in production*
  — source: [#1605](https://github.com/ThalesGroup/fred/commit/ea048fe06) `ea048fe`

- [X] **MIGR-01.07** — Guard against `undefined` before calling `.toLowerCase()` in frontend
  — *Fixes a frontend crash reported by a user*
  — source: [#1611](https://github.com/ThalesGroup/fred/commit/026f21a6a) `026f21a`

- [X] **MIGR-01.08** — Fix broken link in team join-request email
  — *Wrong URL in the invite email*
  — source: [#1589](https://github.com/ThalesGroup/fred/commit/5dd8a8f4d) `5dd8a8f`

- [X] **MIGR-01.11** — Inherit `extraVolumes` and `extraVolumeMounts` in Helm hook Job
  — *Migration hook Jobs were missing volume mounts defined at chart level*
  — source: [#1659](https://github.com/ThalesGroup/fred/commit/7dce0561c) `7dce056`

- [X] **MIGR-01.12** — Add fast PDF processor
  — *New processor significantly reduces PDF ingestion time*
  — source: [#1626](https://github.com/ThalesGroup/fred/commit/3ab0af7a3) `3ab0af7`

- [X] **MIGR-01.13** — Mitigate knowledge-flow worker memory pressure during PDF medium-rich ingestion
  — *Prevents OOM crashes on large/rich PDFs in production*
  — source: [#1624](https://github.com/ThalesGroup/fred/commit/45db88821) `45db888`

- [X] **MIGR-01.14** — Cap concurrent uvicorn connections, configurable via Helm values and Makefiles
  — *Prevents connection overload; tunable per environment*
  — source: [#1627](https://github.com/ThalesGroup/fred/commit/688c4fa91) `688c4fa`

- [X] **MIGR-01.15** — Add custom `RetryPolicy` support for Temporal activities
  — *Allows per-activity retry tuning to avoid cascading failures*
  — source: [#1576](https://github.com/ThalesGroup/fred/commit/6550bb73d) `6550bb7`

### Good to have

- [ ] **MIGR-01.09** — Remove SCSS, migrate to pure CSS className syntax
  — *Removes old SCSS layer; project is now pure CSS*
  — source: [#1636](https://github.com/ThalesGroup/fred/commit/419b79554) `419b795`

- [X] **MIGR-01.10** — Fix company-managed CA certificate handling in local dev environment
  — *Required for developers working on Leap*
  — source: [#1620](https://github.com/ThalesGroup/fred/commit/403bf3aff) `403bf3a`

---

## §2 Postgres data/schema migration and backfill scripts for Fred tables(MIGR-02)

Schema diffs and backfill scripts for existing production data.
Each row represents one backfill script or migration step.

### Required

- [ ] **MIGR-02.01** — Cherry-pick `created_at` / `updated_at` timestamps on all ORM tables
  — *Prerequisite for KPI queries on production data*
  — depends on: MIGR-01.04 (same commit, must land first)

- [ ] **MIGR-02.02** — Backfill script: migrate data from `agent` → `agent_instance`, then drop `agent`
  — *`agent` table is the Kea model; Swift uses `agent_instance` — production data must be migrated before cutover*

### Optional

- [ ] **MIGR-02.03** — Backfill script: migrate conversations from `session` → `session_metadata`
  — *Table rename between Kea and Swift; existing sessions would be lost without this*

- [ ] **MIGR-02.04** — Handle `session_history` schema change
  — *Schema differs between Kea and Swift; assess: migrate in place, transform, or accept history loss*

---

## §3 Feature parity — Kea features missing in Swift (MIGR-03)

Features present in Kea production that are not yet in Swift.
For each item: assess whether to port as-is, adapt to Swift architecture, or drop
with a written rationale.

- [ ] **MIGR-03.01** — Session attachments — add document to a conversation directly
  — *Users could attach documents inline in a chat session in Kea*

- [ ] **MIGR-03.02** — Message feedback — leave a rating with 5 stars and a comment on a chat message
  — *Feedback feature was available in Kea; used for quality monitoring*

- [ ] **MIGR-03.03** — Source citation in chat — display source references alongside agent responses
  — *Kea showed which documents/sources were used in the response*

---

## Progress

| Workstream | Total | Done | Remaining |
| ---------- | ----- | ---- | --------- |
| MIGR-04 Identity bootstrap (platform prerequisite) | 1 | 0 | 1 |
| MIGR-01 Cherry-picks | 15 (13 needed + 2 good-to-have) | 9 | 6 |
| MIGR-02 DB migration | 4 (2 required + 2 optional) | 0 | 4 |
| MIGR-03 Feature parity | 3 | 0 | 3 |

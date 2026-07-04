# Fred 2.0.2 — Implementation Workplan (operational, not a contract)

**This is the working checklist for building CTRLP-12.** It is *not* the RFC. The design
& rationale live in [`rfc/FRED-2.0.2-RGPD-READY-RFC.md`](rfc/FRED-2.0.2-RGPD-READY-RFC.md);
this file is just *how we build it, one reviewable step at a time*.

## How to use this (handoff protocol — read first)

A session (me, or a fresh Claude) picks up like this:
1. Read the RFC §0–§6 and this file's **Ground rules**.
2. Find the **first unchecked step** in the **Rev. 2 progress tracker**. Do **only that step**.
3. Run its **Done when** checks. Paste the output.
4. **Stop.** Post the step's **Review checklist** for a human/cross-review. Do not start the next step.
5. A reviewer ticks the box here (and notes the commit SHA) before the next step starts.

## Ground rules (the mandate)

- **Less code, more feature.** Before writing anything, find the existing primitive and
  reuse it. Each step names what to reuse and the *minimal* genuinely-new code. A reviewer
  who spots re-implemented existing behaviour **rejects the step.**
- **One step = one commit = one review.** Small, independently shippable, independently
  revertible. Conventional message `feat(CTRLP-12): …` (or `test(CTRLP-12): …`).
- **No scope creep.** A step does exactly its line. Anything extra → a new step.
- **Green before stop.** `make code-quality` + `make test` (in the touched project root)
  must pass at the end of every step. Never stop on red.
- **Order = risk (rev. 2).** Consolidate the data model first (Phase R); then the
  server-initiated-erase **auth prerequisite** (Phase C); then erase-at-expiry + sweeps
  (Phase E); then migration coverage (Phase M); the deferred UX + any grace window is
  **last** and gated on Phase E proving real erasure (Phase D). eval-authz after AUTHZ-01.
- **Hard gate (rev. 2).** Deferred delete is **never enabled, and never a default**, before
  its erase-at-expiry can authenticate and complete (Phase C+E). A hidden-but-never-erased
  conversation is a defect, not a milestone.
- **Fewer tables (rev. 2).** A per-team setting is a **field on `team_metadata`**, never its
  own table. Any new table must be justified against reusing an existing store.

## Definition of done (the whole increment) — RFC §1

(1) erasure complete & provable; (2) "delete" means delete; (3) retention bounded &
team-governed; (4) evaluation authorised & scoped; (5) identity stays pseudonymised.
**Rev. 2 additions:** (6) deferred/idle erasure actually completes at expiry via an
authenticated worker (RFC §3.C); (7) per-team retention survives a platform migration
(RFC §3.D).

---

## Target correction (rev. 2 — 2026-07-03)

A first implementation pass + independent review showed the increment is **not mature**.
Three faults, and the redefinition that fixes them (see RFC rev. 2 §3.B/§3.C/§3.D):

1. **Data model** — retention got its **own** `team_policy_override` table for two settings.
   → **Fold into `team_metadata`** (columns, in `fred_core` — **accepted**), reuse
   `GET`/`PATCH /teams/{id}`, delete the table/store/endpoints. Net: +2 tables → +3 columns,
   ~3 fewer files, one fewer migration; the resolver reads off the fetched team record
   (removes a store dep). A future setting is a column, never a table.
2. **Server-initiated erasure under-specified** — the expiry worker has no authenticated
   identity, so the deferred path hides but never erases (and was shipped **default-on** for
   teams: a regression that stops cleaning attachments). → Deferred delete is **removed as a
   default**, and only ships once the worker **auth (Phase C)** and **erase-at-expiry
   (Phase E)** are implemented and tested.
3. **Import/export neglected** — the bundle covers agents/tags/document-metadata only, not
   team settings (team branding isn't exported either). → **Phase M** adds `team_metadata`
   (incl. retention) to the migration — one table covers branding + retention + future
   settings; session `deleted_at` / checkpoint-owner are explicitly excluded (not
   platform-migrated).

**Kept as-is (solid immediate-erasure core):** `erase_session` fan-out + receipt (A1/A2),
the per-store isolation (Q3), the KPI anonymise correctness + index migration (A3→Q1,
`a6ec8bb0`), the `session_metadata.deleted_at` soft-hide column.

**Superseded / to rework:** `team_policy_override` (B2) and the `/retention` endpoints
(B4/B5) → Phase R; deferred-by-default (A5) and the shipped caps (Q2) → Phases D/R;
`checkpoint_thread_owner` (A4, currently write-only, no reader) → moves into Phase E with its
consumer. The rev. 1 tracker below is **historical**; the rev. 2 phases are the plan of
record.

## Rev. 2 progress tracker (plan of record)

**Phase R — data-model consolidation**
- [x] **R1+R2** (folded) `982099b9` — removed `team_policy_override` (model/store/migration `c1d2e3f4a5b6` + all wiring); retention now 3 nullable columns on `team_metadata` in `fred_core` (`team_delete_grace`, `max_idle`, `retention_updated_by`), read/written via existing `GET`/`PATCH /teams/{id}` (resolved view embedded on `TeamWithPermissions`; `UpdateTeamRequest` extended; 422 on over-cap); `/retention` endpoints retired; resolver reads off the already-fetched team record (store dep removed); cap = ceiling, unset ⇒ immediate delete. Migration re-pointed `d2e3f4a5b6c7`→`e7f8a9b0c1d2`, new `e3f4a5b6c7d8` (single head). Net −296 LOC. **control-plane 223 green + fred-core 219 green; code-quality green both.** _Folded R1+R2 per maintainer (broken resolver between the two avoided)._
- [x] **R3** `44f28bcf` — Data & Retention panel re-pointed at the extended team API (reads embedded `team.retention`, writes via `useUpdateTeamMutation`); dead `/retention` hooks + tag removed; control-plane client regenerated (dropped 2 endpoints + `UpdateTeamRetentionRequest`, added `retention` to team types); "preview — not yet enforced" caption added (flips to enforced at D1). tsc + prettier green.
- [ ] **R4** ~~Reference chart values + configmap parity~~ → **superseded by the definitive path (2026-07-04, see note below): folded into D1.** The regression is closed by making deferred delete *actually erase* (C→E→D), not by gating it off. Chart/config parity handled when D1 enables real windows.

> **Decision (2026-07-04, maintainer): pursue the definitive deferred-delete path.**
> Rather than the R4 config gate + "preview" half-state, build the real feature so
> "erase later" genuinely erases: **C1 → C2 → E1 → D1** (small green commits).
> `can_manage_platform` already exists in `fred_core` → C1 is unblocked (AUTHZ-01 now
> owned by Dimitri while Simon is out). This **reverses the rev. 2 "deferred last" risk
> ordering** deliberately. R3's "preview — not yet enforced" caption flips to enforced
> at D1. R4 is folded into D1; E2/E3/M2 remain as follow-ups.

**Phase C — server-initiated erasure auth (prerequisite)**
- [x] **C1** `9cedd5d7` — `can_manage_platform` admin branch on runtime checkpoint-delete, runtime history-delete, KF `/fast/delete/{document_uid}`: waives per-user ownership, keeps authN; fails closed when ReBAC disabled. Extracted module-level helpers (`_caller_can_manage_platform`, `_authorize_fast_ingest_delete`) so it's offline-unit-testable. Reuses the existing AUTHZ-01 permission (already in `fred_core`), no fork. runtime 408 + KF 321 green.
- [x] **C2** `82a6c391` — control-plane service-token minter: wired the existing `M2MTokenProvider` (cached client-credentials) from the `control-plane` SA (`security.m2m`); `ApplicationContext.get_service_bearer()` → `"Bearer …"`, fails closed (retryable) without the secret. control-plane 228 green.

**Phase E — erase-at-expiry + sweeps (after Phase C)**
- [x] **E1** `99d34521` — lifecycle expiry now runs `erase_session` as the service principal (C1+C2), threading the queue row's real `user_id`/`team_id`/`session_id` (user_id was dropped); queue done **only** on `receipt.ok` (partial / bearer-mint-fail / missing-owner leave it queued for retry). `trigger`/reason not carried. Lazy imports keep the scheduler↔product cycle and the Temporal sandbox graph clean. control-plane 231 green.
- [ ] **E2** `IDLE_EXPIRED` sweep (`updated_at < now − max_idle`; dry-run preview)
- [ ] **E3** `checkpoint_thread_owner` + write-on-`aput` **+ reader** (per-user / age erase) — introduced here, with its consumer; **coordinate the shared checkpoint schema with MEMORY-02 (Marc)**

**Phase M — migration (import/export)**
- [x] **M1** `e4f0a4d3` — Added `team_metadata` (branding + retention columns) to the export/import bundle via the existing `postgres/<table>.jsonl` pattern; skip-if-present import; round-trip + idempotent-skip tests (225 green). Also fixes the pre-existing team-branding export gap.
- [ ] **M2** **Explicitly exclude** `session_metadata.deleted_at` + `checkpoint_thread_owner` from the bundle (conversations/runtime are not platform-migrated) — documented, not a silent half-state

**Phase D — deferred UX + explicit grace windows (LAST; gated on Phase E proven)**
- [x] **D1** `187fad37` — deferred delete enabled + enforced now that erase-at-expiry is real. `_resolve_delete_window` returns the team's OWN set value (clamped ≤ cap) or None: **immediate by default, deferred only when a team opts in.** The platform cap is a ceiling, never an implicit default window (closes the R4 gate without removing the caps). R3 caption flipped "preview — not yet enforced" → enforcement notice (en/fr). control-plane 232 + frontend green.

**Independent**
- [ ] **V1** Evaluation endpoints ReBAC authz (after AUTHZ-01) — was E1
- [ ] **DOC1/DOC2** DOC-RENAME / DOC-TAGS (own RFCs)

---

## Rev. 2 step details (implement these, not the historical tracker)

> Template per step: **Goal · Reuse · New code · Files · Done when · Review checklist · Depends on · Commit.**

### R1 — Remove `team_policy_override`
- **Goal:** delete the per-setting table introduced in the first pass and return per-team
  settings to one home.
- **Reuse:** existing `TeamMetadataStore` will become the settings home in R2; no
  replacement store is created here.
- **New code:** none; this is removal and dependency cleanup.
- **Files:** remove `models/team_policy_override_models.py`,
  `teams/policy_override_store.py`, and the `*_add_team_policy_override.py` migration;
  remove imports/accessors from `alembic/env.py`, `app/context.py`,
  `product/dependencies.py`, and tests.
- **Done when:** `rg team_policy_override apps/control-plane-backend` returns only
  historical docs, not application code; Alembic has a single valid head.
- **Review checklist:** table count goes down; no replacement table/blob/KV store appears;
  no runtime behaviour changes except removing the old override dependency.
- **Depends on:** none.
- **Commit:** `refactor(CTRLP-12): remove team policy override table`

### R2 — Retention fields on `team_metadata`
- **Goal:** persist `team_delete_grace` and `max_idle` as fields on the existing
  `team_metadata` store, with audit, and resolve them without a separate policy store.
- **Reuse:** `TeamMetadataRow`, `TeamMetadataStore`, `TeamMetadataPatch`,
  `GET/PATCH /teams/{id}`, existing `CAN_UPDATE_INFO` team update authorization, and the
  existing duration validator.
- **New code:** nullable typed columns (`team_delete_grace`, `max_idle`,
  `retention_updated_by` or equivalent audit field), patch/read projection fields, and a
  resolver adapter that reads from the already-fetched team metadata record. Cap remains a
  ceiling; unset team value means immediate delete.
- **Files:** `libs/fred-core/fred_core/teams/team_metatada_models.py`,
  `libs/fred-core/fred_core/teams/metadata_store.py`,
  control-plane team schemas/service/API, one Alembic migration, resolver tests.
- **Done when:** owner PATCH on `/teams/{id}` can set/clear values; value above cap returns
  422; omitted fields preserve current values; explicit null clears; GET returns the
  resolved view; unset value resolves to immediate delete.
- **Review checklist:** no `/retention` endpoint, no new table, no hand-written duplicate
  schema outside the team API; resolver reuses `evaluate_purge_policy` for platform caps.
- **Depends on:** R1.
- **Commit:** `feat(CTRLP-12): fold retention into team metadata`

### R3 — Retention UI uses the team API
- **Goal:** keep the Settings tab UX but point it at the extended team endpoint.
- **Reuse:** generated control-plane client, existing team settings route/page, existing
  permission display from team permissions.
- **New code:** adapt the Data & Retention panel to read/write via generated team hooks;
  show "preview — not yet enforced" until Phase E is complete.
- **Files:** `apps/frontend/src/rework/.../TeamSettingsRetention/*`,
  generated control-plane API files after `make update-control-plane-api`, locale strings.
- **Done when:** frontend code-quality passes; owner can edit; non-owner can view only;
  the UI uses generated types/hooks only.
- **Review checklist:** no raw `fetch`, no local duplicate API types, no copy implying
  deferred erase is enforced before Phase E.
- **Depends on:** R2.
- **Commit:** `feat(CTRLP-12): use team api for retention settings`

### R4 — Config and chart deferral gate
- **Goal:** make the reference config and Helm chart safe: no default value activates
  deferred delete before Phase E.
- **Reuse:** existing `conversation_policy_catalog.yaml` and chart ConfigMap rendering.
- **New code:** none beyond config/doc updates.
- **Files:** `apps/control-plane-backend/config/conversation_policy_catalog.yaml`,
  `deploy/charts/fred/values.yaml`, tests that load both configurations.
- **Done when:** reference config and chart both leave `team_delete_grace` and
  `personal_delete_grace` unset unless explicitly opted in; config tests assert parity.
- **Review checklist:** platform cap remains distinct from grace window; no `P30D` default
  silently reactivates deferred delete.
- **Depends on:** R2.
- **Commit:** `fix(CTRLP-12): keep deferred delete off by default`

### C1 — Admin branch on service delete endpoints
- **Goal:** let a platform service principal erase at expiry without pretending to be the
  original user.
- **Reuse:** AUTHZ-01 `can_manage_platform`; existing runtime and Knowledge Flow delete
  endpoints; existing authentication dependencies.
- **New code:** ownership-bypass branch only after authn succeeds and the caller holds
  org-level `can_manage_platform`.
- **Files:** runtime `agent_app.py` session/checkpoint delete paths, Knowledge Flow
  `/fast/delete/{document_uid}` path, authz tests.
- **Done when:** service principal with `can_manage_platform` deletes by `session_id` /
  `document_uid`; ordinary non-owner remains denied; unauthenticated remains denied.
- **Review checklist:** bypass waives ownership only, never authentication; no parallel
  internal unauthenticated endpoint; implementation rides AUTHZ-01, not a fork.
- **Depends on:** AUTHZ-01.
- **Commit:** `feat(CTRLP-12): allow platform-managed erasure deletes`

### C2 — Control-plane service-token minter
- **Goal:** give the lifecycle worker a valid bearer for runtime and Knowledge Flow erase
  calls.
- **Reuse:** existing `control-plane` Keycloak service-account configuration.
- **New code:** small client-credentials minter/cache plus dependency injection into the
  lifecycle erase path.
- **Files:** control-plane config models/context, service-token helper, lifecycle
  dependencies/tests.
- **Done when:** tests prove a minted bearer is attached to runtime/KF calls; missing or
  audience-invalid config fails closed with a retryable lifecycle error.
- **Review checklist:** no stored user bearer; token audience is explicit for runtime and
  KF; no broad auth helper unrelated to this need.
- **Depends on:** C1 can be developed in parallel behind fakes, but end-to-end requires C1.
- **Commit:** `feat(CTRLP-12): mint service bearer for lifecycle erasure`

### E1 — Lifecycle expiry calls `erase_session`
- **Goal:** make deferred expiry a real full erasure, not a metadata delete.
- **Reuse:** `ConversationErasureService`, purge queue store, existing receipt semantics,
  checkpoint-before-history ordering.
- **New code:** lifecycle action loads the queued row's real `session_id`, `team_id`,
  `user_id`; calls `erase_session` with the service bearer; marks queue done only when
  `receipt.ok`. The queue's **`trigger` (reason) is deliberately NOT carried** — `erase_session`
  does not depend on it and the queue does not store it (decision (b): erase is erase,
  whatever the reason; no `trigger` column, no audit-of-reason for now).
- **Files:** `scheduler/lifecycle_actions.py`, queue/candidate structures, lifecycle
  dependencies, tests.
- **Done when:** success marks done; partial receipt leaves queue pending; retry is
  idempotent; the real `user_id`/`team_id`/`session_id` are threaded (not dropped).
- **Review checklist:** no parallel delete path; no done-on-partial; `erase_session` receives
  the queue row's own `user_id`/`team_id` (not a hard-coded value).
- **Depends on:** C1, C2.
- **Commit:** `feat(CTRLP-12): erase deferred sessions at expiry`

### E2 — Idle sweep
- **Goal:** enqueue conversations whose last activity exceeds the team's `max_idle`.
- **Reuse:** `session_metadata.updated_at`, team retention resolver, purge queue store, dry-run
  pattern from lifecycle tooling.
- **New code:** dry-run preview and guarded enqueue pass for `IDLE_EXPIRED`.
- **Files:** scheduler runner/policies, queue model if trigger storage is needed, tests.
- **Done when:** dry-run reports candidates without writing; active run enqueues due
  sessions; unset `max_idle` produces no candidates; caps are respected.
- **Review checklist:** dry-run default for destructive/admin operation; no direct deletion
  in the sweep; erasure still flows through E1.
- **Depends on:** E1.
- **Commit:** `feat(CTRLP-12): enqueue idle conversation erasures`

### E3 — Checkpoint owner index with consumer
- **Goal:** introduce `checkpoint_thread_owner` only together with a reader that uses it for
  per-user/age erase.
- **Reuse:** `FredSqlCheckpointer` table self-init, `session_history` backfill, existing
  `adelete_thread`.
- **New code:** side table, best-effort write on `aput`, backfill, and the per-user/age
  reader used by the lifecycle/per-user erase path.
- **Files:** `libs/fred-runtime/fred_runtime/runtime_support/sql_checkpointer.py`,
  runtime tests, coordination note with MEMORY-02.
- **Done when:** owner write never fails a turn; backfill is idempotent; reader enumerates
  expected threads; deleting a thread removes owner row too.
- **Review checklist:** not write-only; schema coordinated with MEMORY-02; no checkpoint
  auth path starts trusting incomplete owner data without fallback.
- **Depends on:** E1/E2 shape, MEMORY-02 coordination.
- **Commit:** `feat(CTRLP-12): add checkpoint owner index with purge reader`

### M1 — Export/import `team_metadata`
- **Goal:** make team settings, branding, and retention survive platform migration.
- **Reuse:** existing import/export bundle pattern for `postgres/<table>.jsonl`.
- **New code:** serialize/deserialize `team_metadata` with retention fields.
- **Files:** `import_export/exporter.py`, `import_export/importer.py`, `bundle.py` if table
  metadata needs updating, frontend migration tests if surfaced.
- **Done when:** export/import round-trip into a fresh platform preserves description,
  privacy, banner key, storage fields, `team_delete_grace`, `max_idle`, and audit field.
- **Review checklist:** one table covers branding + retention; no separate retention export;
  idempotent import skips or merges consistently with existing semantics.
- **Depends on:** R2.
- **Commit:** `feat(CTRLP-12): include team metadata in platform migration`

### M2 — Document runtime-state migration exclusions
- **Goal:** make non-migrated conversation/runtime state explicit.
- **Reuse:** bundle manifest/docs.
- **New code:** manifest/documentation entries only unless exporter needs an explicit
  exclusion list.
- **Files:** import/export docs/tests and RFC/backlog if needed.
- **Done when:** tests or manifest assert `session_metadata.deleted_at` and
  `checkpoint_thread_owner` are not bundled; docs say conversations/runtime state are out
  of platform migration scope.
- **Review checklist:** no silent half-state; retention remains included through
  `team_metadata`.
- **Depends on:** M1.
- **Commit:** `docs(CTRLP-12): document conversation state migration exclusions`

### D1 — Enable deferred delete
- **Goal:** turn on hide-now/erase-at-expiry semantics only after the worker path is proven.
- **Reuse:** `deleted_at`, purge queue, E1 lifecycle erasure, team/personal grace settings.
- **New code:** delete-button branch for configured explicit grace windows, with defaults
  still unset unless ops deliberately configures them.
- **Files:** product delete service/API, policy config, chart values, tests.
- **Done when:** team and personal configured windows hide immediately and erase at expiry;
  queue done only on `receipt.ok`; no configured window means immediate erase.
- **Review checklist:** no implicit default grace from platform cap; no hidden-but-expired
  un-erased state; chart and reference config remain explicit.
- **Depends on:** E1, R4.
- **Commit:** `feat(CTRLP-12): enable deferred delete after erasure worker`

### V1 — Evaluation ReBAC
- **Goal:** close the evaluation authorization gap.
- **Reuse:** AUTHZ-01 ReBAC check pattern, existing per-team evaluation scoping.
- **New code:** `CAN_READ` for list/get, `CAN_UPDATE_AGENTS` for create/cancel,
  `CAN_READ_CONVERSATIONS` for real-conversation campaigns.
- **Files:** evaluation API/service tests.
- **Done when:** non-member create/list is 403; manager create is allowed; real-conversation
  campaign without `CAN_READ_CONVERSATIONS` is 403.
- **Review checklist:** no `require_admin`/`@authorize`; no new permission invented.
- **Depends on:** AUTHZ-01.
- **Commit:** `feat(CTRLP-12): authorize evaluation endpoints with ReBAC`

---

## Progress tracker (rev. 1 — HISTORICAL; superseded by the rev. 2 phases above)

> Kept for the commit trail only. The **rev. 2 phases** (Target correction, above) are the
> plan of record. Items below marked done reflect what was built in the first pass. Do not
> implement from this section; several entries are intentionally superseded (data model,
> deferred-by-default, checkpoint owner) per rev. 2.

Workstream **B — team-governed retention** (control-plane only, pure reuse):
- [x] **B1** Policy fields: `team_delete_grace` + `max_idle` — ✅ reviewed, `7f2ec68f` (177 tests green; DRY validator). B3 note: surface the 2 fields through `PolicyEvaluationResult`.
- [x] **B2** `team_policy_override` table + store + migration — ✅ reviewed, `ae4f40ea` (178 green; single alembic head; pure-persistence store)
- [x] **B3** Retention resolver (reuse `evaluate_purge_policy` + clamp) — ✅ reviewed, `11523609` (195 green; pure clamp, edge cases tested). Forward: revisit cap-resolution trigger when USER_DELETED/IDLE_EXPIRED land (A5/A6).
- [x] **B4** `GET /teams/{id}/retention` — ✅ reviewed, `12f60795` (197 green; CAN_READ, delegates to resolver, test asserts endpoint == resolver)
- [x] **B5** `PATCH /teams/{id}/retention` — ✅ reviewed, `79e6d022` (200 green; owner-only, server-side 422, partial semantics, PATCH==GET resolution). **Retention backend B1–B5 complete.**
- [x] **B6** Frontend "Data & Retention" tab — ✅ reviewed, `3e1dc9a1` (tsc+prettier green; generated hooks only; PATCH invalidates GET; i18n). **Workstream B COMPLETE (team-governed retention, end-to-end).** Manual: confirm visual render in-app.

Workstream **A — complete, provable erasure**:
- [x] **A0** Spike: control-plane → runtime erasure — ✅ reviewed, `de83c342`. **HTTP chosen** (§A0); endpoints + ordering constraint verified in code.
- [x] **A1** Extract `ConversationErasureService.erase_session` + `ErasureReceipt` — ✅ reviewed, `d8e168af` (202 green; pure refactor, receipt = RFC §3.A, test seams preserved)
- [x] **A2** Add history + checkpoint deletion to `erase_session` — ✅ reviewed, `dd9d7dc0` (205 green; checkpoint-before-history, runtime resolution reused, isolation + unresolved tested). ⚠️ **Discovered:** if checkpoint erase fails but history succeeds, the checkpoint is orphaned & un-retryable (ownership check needs history) — resolve in A5/A6.
- [x] **A3** KPI eraser — ✅ reviewed, `0a446ede` (cp 208 + fred-core green; anonymise not delete, reuses update_by_query, absent-store no-op, to_thread). ⚠️ **Correction (quality phase, Q1 `85e55437`):** the original A3 filter (`scope_type=session`+`scope_id`) matched NO real KPI row — the runtime emits `dims.session_id`; the "query matches real emit shape" claim was wrong and the test used a fabricated shape. Fixed in Q1.
- [x] **A4** `checkpoint_thread_owner` table + write-on-`aput` + backfill (runtime) — ✅ reviewed, `f053157a` (397 runtime tests green; best-effort aput never fails a turn; age-key always, identity via injection/backfill; per-user purge). Forward: injecting `__fred_user_id/team_id` at invocation sites would populate identity at write-time (optional). NB: re-committed clean after an unrelated UX refactor was un-bundled.
- [x] **A5** Delete button → both deferred — ✅ reviewed, `36aeab60` (212 green; personal_delete_grace platform-only/not-overridable, hide+enqueue, orphan fix landed in erase_session, null→immediate). Forward for A6: lifecycle must process `USER_DELETED` → `erase_session` (until then deferred deletes don't fully erase at expiry); A0 server-auth gap still open.
- [~] **A6** Server-initiated (lifecycle/idle) erase — 🔬 **spike ✅ reviewed, `69dc21b0`** (decision `## A6 decision`: service token + AUTHZ-01 `can_manage_platform` admin branch; **linchpin verified** — AUTHZ-01 RFC §3.1/§3.3 D already specifies it, lines 72/99). Decomposed:
  - [ ] **A6a** runtime + KF admin branch: `can_manage_platform` bypasses the per-user ownership check on the 3 delete endpoints (keep authn) — 🔒 **BLOCKED on AUTHZ-01 (Simon)**
  - [ ] **A6b** control-plane service-token minter (client-credentials for the existing `control-plane` SA; audience accepted by runtime + KF)
  - [ ] **A6c** lifecycle `delete_conversation_and_mark_done` → `erase_session` (thread `user_id`/`team_id`/`trigger` from the queue; **queue entry NOT-done until `receipt.ok`**; reuses A2 order + orphan skip)
  - [ ] **A6d** `IDLE_EXPIRED` sweep (`session_metadata.updated_at < now − max_idle`; dry-run preview; flag-guarded)

**E — governed evaluation** (after AUTHZ-01 lands):
- [ ] **E1** ReBAC authz on evaluation endpoints

**D — bundled document features** (own RFCs; independent):
- [ ] **D1** DOC-RENAME endpoint + FRONT-09 UI
- [ ] **D2** DOC-TAGS add-label UI

**Q — quality phase** (independent re-review → [CTRLP-12-QUALITY-REVIEW.md](CTRLP-12-QUALITY-REVIEW.md); dispatch/review board → [CTRLP-12-DISPATCH.md](CTRLP-12-DISPATCH.md); 2026-07-02):
- [x] **Q1** KPI anonymise → emitted `dims.session_id` (blocker 1: A3's original `scope_type/scope_id` filter matched NO real KPI row) — ✅ reviewed, `85e55437`
- [x] **Q2** platform retention caps shipped + resolver rejects override when no cap (finding 3) — ✅ reviewed, `00c126d9` (caps `P30D`/`P365D`, D1)
- [x] **Q3** `erase_session` isolates attachment + metadata steps (finding 4) — ✅ reviewed, `30e717a1`
- [x] **Q4** idempotent purge-queue enqueue (finding 12) — ✅ reviewed, `cd4007bb`
- [x] **Q5** checkpointer owner test type annotations (L1) — ✅ reviewed, `4d9e5cb8`
- [x] **Q6** Apache headers on 7 new backend files (finding 19) — ✅ reviewed, `7427ef9b`
- [x] **Q7** coverage: soft-delete hide, PATCH overlay, resolver failures (findings 9/10/11) — ✅ reviewed, `998d9bca`
- [x] **Q8** doc convergence + contract reconcile (findings 5/13/14/15/16) — this commit

---

## A0 decision — how control-plane erases runtime stores

**Chosen: (a) HTTP.** control-plane calls the runtime's `DELETE /agents/checkpoints/{id}`
then `DELETE /agents/sessions/{id}`, mirroring the existing `_delete_knowledge_flow_attachment`
helper. **(b) shared-DB is impossible in standalone and fragile in prod** (evidence below).

### Level 1 — Broad (architect / user view)

A conversation's data is spread across services, and **each service owns and deletes its
own store.** control-plane owns the sidebar metadata + attachment records; the runtime that
served the chat owns the transcript (`session_history`) and the LangGraph checkpoint; KF owns
the attachment bytes/vectors. Erasure is a fan-out of small HTTP `DELETE`s — control-plane
never reaches into another service's database.

```
  erase_session(session_id)                     [control-plane ConversationErasureService]
        │
        ├─ session_metadata.delete            (own DB — already done)
        ├─ attachments → KF /fast/delete/{uid}  (HTTP, existing _delete_knowledge_flow_attachment)
        └─ resolve runtime base_url for this session   ── A2 adds ──▶
                └─ DELETE {base_url}/agents/checkpoints/{session_id}   (checkpoint blobs)
                └─ DELETE {base_url}/agents/sessions/{session_id}      (transcript rows)
```

We pick HTTP because the runtime is a **separate deployable with its own storage** — in
standalone it literally has its own SQLite file, and in prod there are **several runtimes**
(`fred-agents`, `fred-samples-agents`, `rags-agents`), each owning its own tables. There is no
single "runtime database" for control-plane to open. HTTP also reuses the runtime's own
per-user ownership checks and is identical in shape to the KF cleanup we already ship — so it
is both the *most portable* and the *least new code*.

### Level 2 — Detail (implementer view)

**Evidence table**

| Question | Finding | Cite |
|---|---|---|
| Same DB in **standalone**? | **No.** control-plane → `~/.fred/control-plane/control_plane.sqlite3`; runtime → `~/.fred/fred-agents/runtime.sqlite3`. Two separate files; control-plane cannot open the runtime's. | [configuration.yaml:51-53](../../apps/control-plane-backend/config/configuration.yaml#L51-L53), [configuration.yaml:42-44](../../apps/fred-agents/config/configuration.yaml#L42-L44) |
| Same DB in **prod**? | Both point at pg `host/database=fred` — *physically colocated* — but control-plane holds no engine for the runtime's schema, and it is one of several runtimes. Colocation is a deployment accident, not a contract. | [configuration_prod.yaml:45-50](../../apps/control-plane-backend/config/configuration_prod.yaml#L45-L50), [configuration_prod.yaml:48-53](../../apps/fred-agents/config/configuration_prod.yaml#L48-L53) |
| One runtime or many? | **Many.** 3 runtime sources registered, each a distinct service + base_url. A session's history/checkpoint live in whichever one served it → per-session resolution is mandatory; a single shared engine can't model this. | [configuration.yaml:64-76](../../apps/control-plane-backend/config/configuration.yaml#L64-L76) |
| Which runtime owns a session? | Resolve: `session_metadata(session_id).agent_instance_id` → `agent_instance.source_runtime_id` → `runtime_catalog_sources[runtime_id].base_url`. `base_url` is the server-side internal URL control-plane already uses for runtime calls. | [session_metadata_models.py:23](../../apps/control-plane-backend/control_plane_backend/models/session_metadata_models.py#L23), [agent_instances/store.py:44](../../apps/control-plane-backend/control_plane_backend/agent_instances/store.py#L44), [service.py:1589-1634](../../apps/control-plane-backend/control_plane_backend/product/service.py#L1589-L1634) |
| `base_url` used server-side? | Yes — control-plane already httpx-fetches the runtime via `source.base_url` (MCP catalog, template aggregation). Erasure reuses the same field; `ingress_prefix` is browser-only. | [service.py:904](../../apps/control-plane-backend/control_plane_backend/product/service.py#L904) |
| Runtime DELETE endpoints | `DELETE /agents/sessions/{session_id}` → `{"deleted": n}`, 200; scoped to caller's `user_id`. `DELETE /agents/checkpoints/{session_id}` → 204; ownership confirmed via history store. | [agent_app.py:2370-2402](../../libs/fred-runtime/fred_runtime/app/agent_app.py#L2370-L2402), [agent_app.py:2698-2733](../../libs/fred-runtime/fred_runtime/app/agent_app.py#L2698-L2733) |
| Cross-service template | `_delete_knowledge_flow_attachment`: `httpx.AsyncClient`, `Authorization` header pass-through, `raise_for_status`, `HTTPStatusError`/`RequestError` → 502. A2 copies this shape. | [service.py:1078-1137](../../apps/control-plane-backend/control_plane_backend/product/service.py#L1078-L1137) |
| Auth today | Only pattern is **caller-bearer pass-through** (KF helper). control-plane mints **no** service token for backend calls; the M2M Keycloak client is Keycloak-Admin-only. | [service.py:1095](../../apps/control-plane-backend/control_plane_backend/product/service.py#L1095) |

**Concrete calls A2 makes** (per session, after resolving `base_url` as above):

1. `DELETE {base_url}/agents/checkpoints/{session_id}` — **first**.
2. `DELETE {base_url}/agents/sessions/{session_id}` — **second**, read `{"deleted": n}` into the receipt.

Each with `headers={"Authorization": authorization}`, `httpx.AsyncClient(timeout=…)`,
`raise_for_status`, wrapped exactly like the KF helper. Runtime is resolved from the session's
`agent_instance_id`, not assumed — a session that ran on `rags-agents` is erased on
`rags-agents`.

**Ordering constraint (must handle):** the checkpoint endpoint confirms ownership *via the
history store* ([agent_app.py:2722-2731](../../libs/fred-runtime/fred_runtime/app/agent_app.py#L2722-L2731)).
Delete the checkpoint **before** the history — reverse order deletes the history rows the
ownership check needs, yielding a 403 and a leaked checkpoint.

**Idempotency / failure:** history DELETE returns `{"deleted": 0}` for an already-gone or
non-owned session (no error) → second erase is a clean no-op. Per the A2 review checklist,
one store's failure must not abort the others: catch per-call, record `ok=false`+error in the
`ErasureReceipt`, continue.

**Edge cases & open risks:**
- **No `agent_instance_id` on a session** (legacy/orphan rows, nullable column) → can't resolve
  the runtime. A2 records `skipped/unresolved` in the receipt rather than guessing a runtime.
- **Runtime source disabled/removed** from `runtime_catalog_sources` → same: record, don't fail.
- **Lifecycle/idle path (A6) has no user token.** The runtime DELETEs are user-scoped and the
  only auth pattern today is bearer pass-through. A2's *delete-button* path (A5) has the caller's
  token and is unblocked; **A6's server-initiated erase needs the service token +
  `can_manage_platform` admin branch chosen below.** Flagging here so the dependency remains
  visible to the implementation steps.

## A6 decision — how a server-initiated (lifecycle) erase authenticates

**Chosen: (a) service token + admin branch.** control-plane mints a
**client-credentials access token** for its existing `control-plane` service
account and presents it as the `authorization` bearer to the erase endpoints;
the runtime + KF delete endpoints gain an **admin branch** — AUTHZ-01's
org-level `can_manage_platform` — that **skips the per-user ownership check**
(ownership was already validated when the item was enqueued). **This is
AUTHZ-01 work, not a parallel scheme** (RFC §3.3 D already names
`session/checkpoint` for the admin branch), so A6a is sequenced behind AUTHZ-01
and coordinated with Simon. Rejected alternatives: an unauthenticated
internal endpoint (trusts the network, not identity — off-model), replaying a
stored user token (deferred window is days/weeks; tokens expire and storing
long-lived user bearers is an RGPD/security liability), and direct shared-DB
delete (already rejected in §A0 — no shared engine, several runtimes).

### Level 1 — Broad (architect / user view)

A deferred/lifecycle erase has **no human in the loop and no user token** — the
scheduler runs in Temporal/memory with only a queue row. Every store erase it
must drive is **user-scoped today** (runtime DELETEs check history ownership;
KF `/fast/delete` requires a user JWT), and the runtime even **rejects tokens
without a `sub`**, so a raw machine token is a 401. The fix keeps Fred's
**single identity model**: the server acts as a **platform-admin service
principal**, and the erase endpoints recognise that principal via AUTHZ-01's
`can_manage_platform` and waive the *ownership* check (never the *authn* check).

```
  lifecycle tick / IDLE sweep        [control-plane scheduler — no user, no bearer]
        │  (queue row: session_id, team_id, user_id)
        ├─ mint service token  ── Keycloak client-credentials (control-plane SA) ──▶ Bearer
        └─ erase_session(...)  with Authorization: Bearer <service token>
                └─ DELETE {runtime}/agents/checkpoints/{id}   ┐ admin branch:
                └─ DELETE {runtime}/agents/sessions/{id}      │ can_manage_platform
                └─ DELETE {kf}/fast/delete/{uid}              ┘ ⇒ skip ownership check
        ⇒ queue entry stays NOT-done until the receipt is ok (retry-safe)
```

### Level 2 — Detail (implementer view)

**Evidence table**

| Question | Finding | Cite |
|---|---|---|
| Runtime `DELETE /agents/sessions` auth | `Depends(_authenticated_user)` → `KeycloakUser`; ownership = `history_store.delete_session(session_id, user_id=caller_uid)` filters `WHERE user_id`. No caller ⇒ deletes all rows for the session. | [agent_app.py:2374-2402](../../libs/fred-runtime/fred_runtime/app/agent_app.py#L2374-L2402), [postgres_history_store.py:345-347](../../libs/fred-core/fred_core/history/postgres_history_store.py#L345-L347) |
| Runtime `DELETE /agents/checkpoints` auth | `Depends(_authenticated_user)`; ownership = `session_belongs_to_user(session_id, caller_uid)` else **403**. | [agent_app.py:2703-2733](../../libs/fred-runtime/fred_runtime/app/agent_app.py#L2703-L2733), [postgres_history_store.py:354-369](../../libs/fred-core/fred_core/history/postgres_history_store.py#L354-L369) |
| KF `/fast/delete/{uid}` auth | `Depends(get_current_user)` → requires a user JWT; will not accept a bare M2M token. | [ingestion_controller.py:1027-1040](../../apps/knowledge-flow-backend/knowledge_flow_backend/features/ingestion/ingestion_controller.py#L1027-L1040) |
| Does the runtime accept a machine token? | `decode_jwt` **requires a `sub` claim** → **401** if absent. A Keycloak *service-account* client-credentials token **does** carry `sub` (= SA user id), so it passes authn but then **fails ownership** (SA owns no history) ⇒ needs the admin branch. | [oidc.py:423-430](../../libs/fred-core/fred_core/security/oidc.py#L423-L430) |
| Does control-plane mint a service bearer today? | **No.** The M2M client is **KeycloakAdmin-only** (group/user mgmt); it never mints an access token for calling runtime/KF. All cross-service auth = **caller-bearer pass-through**. | [keycloack_admin_client.py:35-62](../../libs/fred-core/fred_core/security/keycloak/keycloack_admin_client.py#L35-L62), [service.py:1115-1128](../../apps/control-plane-backend/control_plane_backend/product/service.py#L1115-L1128), [erasure_service.py:64-66](../../apps/control-plane-backend/control_plane_backend/sessions/erasure_service.py#L64-L66) |
| Service-account config already present? | `client_id: control-plane`, `secret_env_var: KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET`, realm URL — enabled in prod. | [configuration_prod.yaml:87-91](../../apps/control-plane-backend/config/configuration_prod.yaml#L87-L91), [configuration.yaml:85-89](../../apps/control-plane-backend/config/configuration.yaml#L85-L89) |
| Lifecycle path today | `delete_conversation_and_mark_done` = single `session_store.delete(session_id)`; no token, no cross-service call. | [lifecycle_actions.py:53-83](../../apps/control-plane-backend/control_plane_backend/scheduler/lifecycle_actions.py#L53-L83) |
| Does the queue carry the erase inputs? | Row has `session_id`+`team_id`+`user_id`; but `list_due_conversation_candidates` **drops `user_id`** and hard-codes `MEMBER_REMOVED`. Data is present, not yet threaded. | [purge_queue_models.py:16-18](../../apps/control-plane-backend/control_plane_backend/models/purge_queue_models.py#L16-L18), [lifecycle_actions.py:40-49](../../apps/control-plane-backend/control_plane_backend/scheduler/lifecycle_actions.py#L40-L49) |
| AUTHZ-01 fit | §3.1 adds org-level `can_manage_platform: admin` covering "policies/purge, **lifecycle**"; §3.3 D keeps `session/checkpoint` ownership with an **admin branch → `can_manage_platform`**. | [RBAC-TO-REBAC-MIGRATION-RFC.md:72](rfc/RBAC-TO-REBAC-MIGRATION-RFC.md#L72), [RBAC-TO-REBAC-MIGRATION-RFC.md:99](rfc/RBAC-TO-REBAC-MIGRATION-RFC.md#L99) |

**What each service must change**
- **Runtime** (A6a): on `DELETE /agents/sessions|checkpoints`, add an admin branch —
  if the caller holds org `can_manage_platform`, skip the history-ownership check and
  delete by `session_id` alone. Keep authn (valid token, `sub` present); waive only authz.
- **Knowledge Flow** (A6a): same admin branch on `/fast/delete/{uid}`.
- **control-plane** (A6b): add a **service-token minter** beside the existing M2M client
  (client-credentials grant for `control-plane`, audience accepted by runtime **and** KF);
  attach it as `authorization` in the lifecycle erase path. Verify token audience against
  each validator (may need a Keycloak audience mapper).
- **AUTHZ-01 dependency:** A6a rides the AUTHZ-01 change to those ownership sites — **do not
  fork a second bypass.** Coordinate with Simon so the admin branch is `can_manage_platform`.

**A6 implementation sub-steps**
- **A6a — service-erase admin branch (runtime + KF).** `can_manage_platform` bypass of the
  per-user ownership check on the three delete endpoints. **Depends on AUTHZ-01** (§3.1 schema
  + §3.3 D). Coordinate with Simon (AUTHZ-01).
- **A6b — control-plane service token.** Mint + attach the client-credentials bearer for the
  lifecycle erase. Config already present (`control-plane` SA).
- **A6c — lifecycle → `erase_session`.** Swap `delete_conversation_and_mark_done` from
  `session_store.delete` to `ConversationErasureService.erase_session(...)` with the service
  token; thread `user_id`+`team_id`+`session_id` from the queue row (stop dropping `user_id`).
  The `trigger`/reason is **not** carried (erase doesn't need it; no `trigger` column —
  decision (b)). **Keep the queue entry NOT-done until `receipt.ok`** (reuses the A2
  checkpoint-before-history ordering + orphan skip; retry-safe).
- **A6d — `IDLE_EXPIRED` sweep.** Periodic pass enqueues `session_metadata.updated_at < now −
  max_idle` (B1 policy); **dry-run preview** reports counts without deleting; flag-guarded.

**Open risks**
- **AUTHZ-01 not yet landed** → A6a is blocked on it; sequence A6a after AUTHZ-02/03 touch the
  ownership sites. A6b/A6c/A6d (control-plane + sweep) can proceed against a feature flag but the
  end-to-end erase is not authorised until A6a lands. **Coordinate with Simon (AUTHZ-01).**
- **Token audience** must be accepted by runtime **and** KF validators — verify each
  `decode_jwt` audience config; a Keycloak client audience mapper may be required.
- **`security_enabled=False` (dev)** already bypasses ownership entirely (no-security = global
  eraser). The admin branch must **fail-closed when security is ON** and open only for
  `can_manage_platform`.
- **Idempotency / partial failure:** keep the queue entry un-done until the receipt is ok; a
  second run is a clean no-op (history DELETE returns `{"deleted": 0}`).

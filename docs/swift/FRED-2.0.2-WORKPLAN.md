# Fred 2.0.2 — Implementation Workplan (operational, not a contract)

**This is the working checklist for building CTRLP-12.** It is *not* the RFC. The design
& rationale live in [`rfc/FRED-2.0.2-RGPD-READY-RFC.md`](rfc/FRED-2.0.2-RGPD-READY-RFC.md);
this file is just *how we build it, one reviewable step at a time*.

## How to use this (handoff protocol — read first)

A session (me, or a fresh Claude) picks up like this:
1. Read the RFC §0–§6 and this file's **Ground rules**.
2. Find the **first unchecked step** in the Progress tracker. Do **only that step**.
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
- **Order = risk.** Workstream B (self-contained, pure reuse) first; A (some cross-service)
  next; eval-authz after AUTHZ-01 settles; UI/doc last.

## Definition of done (the whole increment) — RFC §1

(1) erasure complete & provable; (2) "delete" means delete; (3) retention bounded &
team-governed; (4) evaluation authorised & scoped; (5) identity stays pseudonymised.

---

## Progress tracker

Workstream **B — team-governed retention** (control-plane only, pure reuse):
- [x] **B1** Policy fields: `team_delete_grace` + `max_idle` — ✅ reviewed, `7f2ec68f` (177 tests green; DRY validator). B3 note: surface the 2 fields through `PolicyEvaluationResult`.
- [x] **B2** `team_policy_override` table + store + migration — ✅ reviewed, `ae4f40ea` (178 green; single alembic head; pure-persistence store)
- [x] **B3** Retention resolver (reuse `evaluate_purge_policy` + clamp) — ✅ reviewed, `11523609` (195 green; pure clamp, edge cases tested). Forward: revisit cap-resolution trigger when USER_DELETED/IDLE_EXPIRED land (A5/A6).
- [ ] **B4** `GET /teams/{id}/retention`
- [ ] **B5** `PATCH /teams/{id}/retention`
- [ ] **B6** Frontend "Data & Retention" tab

Workstream **A — complete, provable erasure**:
- [ ] **A0** Spike: how does control-plane reach runtime `session_history` + checkpoint? (decide HTTP vs shared-DB)
- [ ] **A1** Extract `ConversationErasureService.erase_session` + `ErasureReceipt` from existing `delete_session`
- [ ] **A2** Add history + checkpoint deletion (the gaps) to `erase_session`
- [ ] **A3** KPI eraser (the one new store method) — anonymise by default
- [ ] **A4** `checkpoint_thread_owner` table + write-on-`aput` + backfill (runtime)
- [ ] **A5** Delete button → personal immediate / team deferred
- [ ] **A6** Lifecycle purge action → `erase_session`; add `IDLE_EXPIRED` sweep

**E — governed evaluation** (after AUTHZ-01 lands):
- [ ] **E1** ReBAC authz on evaluation endpoints

**D — bundled document features** (own RFCs; independent):
- [ ] **D1** DOC-RENAME endpoint + FRONT-09 UI
- [ ] **D2** DOC-TAGS add-label UI

---

## Steps

> Template per step: **Goal · Reuse · New code · Files · Done when · Review checklist · Depends on · Commit.**

### B1 — Policy fields `team_delete_grace` + `max_idle`
- **Goal:** the policy can express, per team, the deferred-delete window and the idle cap.
- **Reuse:** `PolicyAction` / `PolicyActionOverride` / `_merge_action` already exist and
  already handle `retention`. Add two optional fields the same way.
- **New code:** two `str | None` fields on each model (with the existing ISO-8601 validator)
  + two lines in `_merge_action`. Nothing else.
- **Files:** `scheduler/policies/policy_models.py`, `scheduler/policies/policy_engine.py`.
- **Done when:**
  - `make test` (control-plane) green.
  - A new unit test proves: a catalog with `team_delete_grace`/`max_idle` in `default` and a
    `rules` override parses, and `_merge_action` takes the override when present, else default.
- **Review checklist:** fields are *optional* (no migration of the YAML required); validator
  reused (not re-written); no behaviour change to `retention`/`mode`/`cancel_on_rejoin`.
- **Depends on:** none.
- **Commit:** `feat(CTRLP-12): add team_delete_grace + max_idle policy fields`

### B2 — `team_policy_override` table + store + migration
- **Goal:** persist a per-team override (already-drafted model file).
- **Reuse:** model mirrors `purge_queue_models`; store mirrors `SessionMetadataStore`
  (get + upsert via `s.merge`); migration mirrors the `session_metadata` Alembic file.
- **New code:** finalize `models/team_policy_override_models.py` (done); a tiny store
  (`get(team_id)`, `upsert(team_id, fields, updated_by)`); one Alembic migration.
- **Files:** `models/team_policy_override_models.py`, new `teams/policy_override_store.py`,
  new `alembic/versions/*_add_team_policy_override.py`, wire accessor in `app/context.py`.
- **Done when:**
  - `alembic upgrade head` applies cleanly on a fresh SQLite (`make test` bootstraps this).
  - Store unit test: upsert then get round-trips; second upsert updates `updated_at`/`updated_by`.
- **Review checklist:** one row per team (PK = team_id); no FK that SQLite won't enforce;
  store has no business logic (pure persistence); accessor cached like the others in context.
- **Depends on:** none (parallel to B1).
- **Commit:** `feat(CTRLP-12): team_policy_override table + store`

### B3 — Retention resolver (the "less code" gem)
- **Goal:** compute, per team, `{platform_max, team_value, effective, source}` for each of
  `team_delete_grace` and `max_idle`.
- **Reuse:** `evaluate_purge_policy(...)` resolves the platform value (the **cap**) with
  specificity — call it, don't reimplement. `duration_to_seconds` for the clamp compare.
- **New code:** one pure function `resolve_team_retention(policy, override, team_id) -> view`:
  `effective = min(team_value ?? platform_max, platform_max)`; `source = "team" if team_value
  set and ≤ cap else "platform"`.
- **Files:** new `scheduler/policies/retention_resolver.py` + unit test.
- **Done when:** unit tests cover: no override → effective = platform & source=platform;
  override < cap → effective = override & source=team; override > cap → **rejected/clamped**
  (resolver returns cap + a `would_exceed` flag the PATCH uses for 422); override = cap → team.
- **Review checklist:** pure function, no I/O; reuses `evaluate_purge_policy` for the cap;
  the clamp direction is "team may only tighten" (≤ cap), never extend.
- **Depends on:** B1.
- **Commit:** `feat(CTRLP-12): per-team retention resolver (clamp to platform cap)`

### B4 — `GET /teams/{id}/retention`
- **Goal:** read the resolved view for the team settings tab.
- **Reuse:** team-permission gate pattern from `update_team` /
  `_validate_team_and_check_permission`; catalog via `app/context.get_policy_catalog()`;
  the B3 resolver; the B2 store.
- **New code:** one endpoint + `TeamRetentionView` schema + a thin service function.
- **Files:** `product/api.py`, `product/service.py`, `product/schemas.py`.
- **Done when:** TestClient: a member (`CAN_READ`) gets 200 with the 4-field view; the view
  matches the resolver for a team with and without an override.
- **Review checklist:** gated on `CAN_READ`; no write; reuses the resolver (no inline policy
  logic in the endpoint); response typed (regenerate client only in B6).
- **Depends on:** B2, B3.
- **Commit:** `feat(CTRLP-12): GET team retention view`

### B5 — `PATCH /teams/{id}/retention`
- **Goal:** the owner sets the per-team value, bounded by the cap.
- **Reuse:** same permission pattern (`CAN_UPDATE_INFO`, owner) as branding update; B2 store;
  B3 resolver for the bound check.
- **New code:** one endpoint + `UpdateTeamRetentionRequest`; validate each field `≤ cap`
  (resolver `would_exceed`) → `422`; persist via store with `updated_by = caller.uid`.
- **Files:** `product/api.py`, `product/service.py`, `product/schemas.py`.
- **Done when:** TestClient: owner sets value < cap → 200 + persisted; value > cap → 422;
  non-owner (`CAN_READ` only) → 403; re-GET reflects the change with `source=team`.
- **Review checklist:** owner-only; cap enforced server-side (never trust client); `updated_by`
  recorded; no new permission introduced.
- **Depends on:** B4.
- **Commit:** `feat(CTRLP-12): PATCH team retention (owner, clamped)`

### B6 — Frontend "Data & Retention" tab
- **Goal:** the visible feature — owner edits retention beside a read-only platform cap.
- **Reuse:** `TeamSettingsPanel` tab pattern (Members/Parameters/Evaluations already exist);
  generated RTK Query hooks (regenerate the control-plane client).
- **New code:** `TeamSettingsMenuPanels.RETENTION` + `TeamSettingsRetention.tsx` (read-only
  platform column, editable team column gated by `CAN_UPDATE_INFO`) + nav entry + governance copy.
- **Files:** `TeamSettingsPanel.tsx`, new `TeamSettingsRetention/…`, `TeamSettingsNavbar.tsx`;
  run `make update-control-plane-api`.
- **Done when:** `make code-quality` (frontend `tsc` + prettier) green; tab renders; owner sees
  editable field + read-only cap, manager sees read-only.
- **Review checklist:** uses generated types/hooks (no hand-written fetch/types); permission
  gate matches backend; copy explains the eval-window link (RFC §4).
- **Depends on:** B4, B5.
- **Commit:** `feat(CTRLP-12): team Data & Retention settings tab`

### A0 — Spike: control-plane → runtime reachability (decision step, ~no code)
- **Goal:** decide the *least-code* way for `erase_session` to delete `session_history` and
  checkpoint rows: (a) HTTP to the runtime DELETE endpoints (mirror
  `_delete_knowledge_flow_attachment`), or (b) shared Postgres → reuse
  `PostgresHistoryStore.delete_session` / `FredSqlCheckpointer.adelete_thread` directly.
- **Done when:** a 5-line note appended here states: do control-plane and runtime share one
  Postgres engine in standalone *and* prod? which runtime owns a session's history (single vs
  per-pod)? chosen approach + why. Reviewer agrees before A2.
- **Review checklist:** the choice is justified by config evidence (cite files), not assumed.
- **Depends on:** none. **Commit:** docs-only note in this file.

### A1 — Extract `erase_session` + `ErasureReceipt` from existing `delete_session`
- **Goal:** one reusable erasure entry point; today's `delete_session` already erases
  attachments + KF document (vectors/content/object) + metadata.
- **Reuse:** lift the existing body of `delete_session` (`product/service.py:2403`) into
  `ConversationErasureService.erase_session`, returning a per-store `ErasureReceipt`. The
  delete-button handler calls the new service. **Behaviour unchanged this step.**
- **New code:** `ErasureReceipt` model; the service wrapper. No new deletes yet.
- **Files:** new `sessions/erasure_service.py`, `product/service.py` (delegate), `product/api.py`.
- **Done when:** existing delete-button tests still pass (regression); a new test asserts the
  receipt lists attachments + metadata stores with counts.
- **Review checklist:** pure refactor — diff shows *moved* code, not rewritten; receipt shape
  matches RFC §3.A; no store deleted twice.
- **Depends on:** none (parallel to B). **Commit:** `refactor(CTRLP-12): extract erase_session + ErasureReceipt`

### A2 — Add history + checkpoint deletion to `erase_session`
- **Goal:** close two of the three erasure gaps.
- **Reuse:** the A0 decision — either the runtime DELETE endpoints (mirror the KF httpx helper)
  or `PostgresHistoryStore.delete_session` + `FredSqlCheckpointer.adelete_thread` directly.
- **New code:** two erasers added to the service + receipt entries.
- **Files:** `sessions/erasure_service.py` (+ runtime client helper if HTTP).
- **Done when:** integration/unit test: after `erase_session`, `history_store.get(session_id)`
  is `[]` and the checkpoint thread is gone; receipt shows non-zero history/checkpoint counts.
- **Review checklist:** uses the existing delete primitives (not new SQL); idempotent (second
  erase → zero, ok); failure of one store doesn't abort the others (receipt records it).
- **Depends on:** A0, A1. **Commit:** `feat(CTRLP-12): erase history + checkpoint`

### A3 — KPI eraser (the only genuinely-new store method)
- **Goal:** remove/anonymise KPI rows for the subject.
- **Reuse:** the OpenSearch `delete_by_query`/`update_by_query` pattern already used in the
  vector store; the KPI store/index already exists.
- **New code:** one `anonymise_for_session(session_id)` (null `user_id`/`session_id`/`exchange_id`)
  on the KPI store, called by the service. Hard-delete mode optional.
- **Files:** `fred_core/kpi/…` (new method), `sessions/erasure_service.py`.
- **Done when:** unit test: after anonymise, no KPI row carries the subject's ids; aggregate
  row count unchanged.
- **Review checklist:** anonymise is the default (RFC §3.3); reuses the existing query pattern.
- **Depends on:** A1. **Commit:** `feat(CTRLP-12): KPI anonymise eraser`

### A4 — `checkpoint_thread_owner` table + write-on-`aput` + backfill (runtime)
- **Goal:** give checkpoints an owner + age key (enables per-user erase + idle sweep).
- **Reuse:** `FredSqlCheckpointer` already self-inits its tables; backfill from `session_history`.
- **New code:** the side table; a best-effort owner write in `aput` (**must never fail a turn**);
  a one-shot backfill; a per-user purge that enumerates `thread_id`s.
- **Files:** `fred_runtime/runtime_support/sql_checkpointer.py`, runtime Alembic.
- **Done when:** unit test: each `aput` writes exactly one owner row; backfill matches
  `SELECT DISTINCT thread_id`; a failed owner write does not raise out of `aput`.
- **Review checklist:** write is best-effort/guarded; no change to checkpoint read path;
  coordinate with MEMORY-02 (Marc) — confirm no schema clash.
- **Depends on:** none (runtime-side). **Commit:** `feat(CTRLP-12): checkpoint_thread_owner index`

### A5 — Delete button → personal immediate / team deferred
- **Goal:** "delete means delete" with the eval window for teams.
- **Reuse:** `is_personal_team_id`; the existing purge queue + lifecycle for the deferred path;
  `session_metadata` gains one nullable `deleted_at` (sidebar list filters it).
- **New code:** the branch in the handler; `deleted_at` column + migration + list filter;
  enqueue `USER_DELETED` at `now + team_delete_grace`.
- **Files:** `product/api.py`/`service.py`, `models/session_metadata_models.py` + migration,
  `sessions/store.py` (list filter).
- **Done when:** test: personal delete → `erase_session` immediately, all stores 0; team delete
  → row hidden (`deleted_at` set), `session_history` still readable, queue entry due at window.
- **Review checklist:** personal vs team via `is_personal_team_id`; team path reuses the queue
  (no new scheduler); history retained for the window (eval).
- **Depends on:** A1, A2, B1/B3 (for the window value). **Commit:** `feat(CTRLP-12): delete = erase (personal now, team deferred)`

### A6 — Lifecycle purge → `erase_session`; add `IDLE_EXPIRED` sweep
- **Goal:** member-removal and idle expiry both run the *complete* erase.
- **Reuse:** `delete_conversation_and_mark_done` (today a single `session_store.delete`) calls
  `erase_session`; the periodic lifecycle pass adds the idle query.
- **New code:** swap the action body (flag-guarded one release); `IDLE_EXPIRED` trigger + the
  `session_metadata.updated_at < now − max_idle` query.
- **Files:** `scheduler/lifecycle_actions.py`, `scheduler/lifecycle_runner.py`, policy models.
- **Done when:** test: member-removal purge erases all stores (receipt); idle sweep enqueues +
  erases sessions past `max_idle`; dry-run preview reports counts without deleting.
- **Review checklist:** flag-guarded rollback; dry-run default; reuses `erase_session` (no
  parallel delete logic).
- **Depends on:** A1, A2, B1. **Commit:** `feat(CTRLP-12): complete lifecycle erase + idle sweep`

### E1 — ReBAC authz on evaluation endpoints (after AUTHZ-01)
- **Goal:** governed per-team evaluation.
- **Reuse:** the ReBAC check pattern AUTHZ-01 establishes (NOT `require_admin`/`@authorize`).
- **New code:** `CAN_READ` (list/get), `CAN_UPDATE_AGENTS` (create/cancel),
  `CAN_READ_CONVERSATIONS` (real-conversation campaigns) on `evaluations/api.py`.
- **Done when:** test: non-member create/list → 403; manager create → ok; real-conversation
  campaign without `CAN_READ_CONVERSATIONS` → 403.
- **Review checklist:** uses the AUTHZ-01 pattern; no new permission; coordinate with EVAL-01 (Odélia).
- **Depends on:** AUTHZ-01 landed. **Commit:** `feat(CTRLP-12): authz on evaluation endpoints`

### D1 / D2 — bundled document features
- Follow their own RFCs (`DOCUMENT-RENAME-RFC`, `DOCUMENT-TAGS-RFC`). D1 = rename endpoint
  (metadata-only) + FRONT-09 UI; D2 = add-label UI over the implemented v1 API. Each: one
  commit, `make code-quality` + `make test` green, manual UI check. Independent of A/B/E.

---

## Suggested order for "today"
B1 → B2 → B3 → B4 → B5 → B6 (a full, demoable, self-contained vertical: team-governed
retention), reviewing after each. Then A0 (spike) gates the erasure work. E1 waits on AUTHZ-01.

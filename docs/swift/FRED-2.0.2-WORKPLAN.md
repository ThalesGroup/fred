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
- [x] **B4** `GET /teams/{id}/retention` — ✅ reviewed, `12f60795` (197 green; CAN_READ, delegates to resolver, test asserts endpoint == resolver)
- [x] **B5** `PATCH /teams/{id}/retention` — ✅ reviewed, `79e6d022` (200 green; owner-only, server-side 422, partial semantics, PATCH==GET resolution). **Retention backend B1–B5 complete.**
- [x] **B6** Frontend "Data & Retention" tab — ✅ reviewed, `3e1dc9a1` (tsc+prettier green; generated hooks only; PATCH invalidates GET; i18n). **Workstream B COMPLETE (team-governed retention, end-to-end).** Manual: confirm visual render in-app.

Workstream **A — complete, provable erasure**:
- [x] **A0** Spike: control-plane → runtime erasure — ✅ reviewed, `de83c342`. **HTTP chosen** (§A0); endpoints + ordering constraint verified in code.
- [x] **A1** Extract `ConversationErasureService.erase_session` + `ErasureReceipt` — ✅ reviewed, `d8e168af` (202 green; pure refactor, receipt = RFC §3.A, test seams preserved)
- [x] **A2** Add history + checkpoint deletion to `erase_session` — ✅ reviewed, `dd9d7dc0` (205 green; checkpoint-before-history, runtime resolution reused, isolation + unresolved tested). ⚠️ **Discovered:** if checkpoint erase fails but history succeeds, the checkpoint is orphaned & un-retryable (ownership check needs history) — resolve in A5/A6.
- [x] **A3** KPI eraser — ✅ reviewed, `0a446ede` (cp 208 + fred-core green; anonymise not delete, reuses update_by_query, query matches real emit shape, absent-store no-op, to_thread)
- [x] **A4** `checkpoint_thread_owner` table + write-on-`aput` + backfill (runtime) — ✅ reviewed, `f053157a` (397 runtime tests green; best-effort aput never fails a turn; age-key always, identity via injection/backfill; per-user purge). Forward: injecting `__fred_user_id/team_id` at invocation sites would populate identity at write-time (optional). NB: re-committed clean after an unrelated UX refactor was un-bundled.
- [x] **A5** Delete button → both deferred — ✅ reviewed, `36aeab60` (212 green; personal_delete_grace platform-only/not-overridable, hide+enqueue, orphan fix landed in erase_session, null→immediate). Forward for A6: lifecycle must process `USER_DELETED` → `erase_session` (until then deferred deletes don't fully erase at expiry); A0 server-auth gap still open.
- [ ] **A6** Lifecycle purge action → `erase_session`; add `IDLE_EXPIRED` sweep — ⚠️ **auth resolved by spike → see `## A6 decision`** (service token + AUTHZ-01 `can_manage_platform` admin branch; splits into A6a–A6d, A6a depends on AUTHZ-01). ⚠️ **orphan (§A2):** on checkpoint-erase failure, skip history erase so retry can still delete the checkpoint; keep the queue entry un-done until both ok.

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
  token and is unblocked; **A6's server-initiated erase needs a service token or an internal
  admin auth path — OPEN, to resolve in A6, not A0.** Flagging now so A6 doesn't discover it late.

---

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

### A5 — Delete button → both deferred (team eval window / personal security window)
- **Goal:** delete = hide-now + full erase after a governed window. **Team** window is the
  owner-set `team_delete_grace` (eval); **personal** window is a **platform** `personal_delete_grace`
  (RSSI/post-incident access — **not user-overridable**, so a user can't evade it). Either
  window unset/null → immediate erase (back-compat).
- **Reuse:** `is_personal_team_id` (picks the window source only); the existing purge queue +
  lifecycle for the deferred path; the B3 resolver for the effective **team** window;
  `session_metadata` gains one nullable `deleted_at` (sidebar list filters it).
- **New code:** platform `personal_delete_grace` on the policy config (`PurgePolicy`, platform-
  level, NOT per-team — mirror the B1 optional-duration field); the branch in the handler;
  `deleted_at` column + migration + list filter; enqueue `USER_DELETED` at `now + window`.
- **Files:** `scheduler/policies/policy_models.py` (personal_delete_grace), config catalog,
  `product/api.py`/`service.py`, `models/session_metadata_models.py` + migration,
  `sessions/store.py` (list filter), `erasure_service.py` (orphan fix).
- **Done when:** test: team delete → hidden (`deleted_at`), `session_history` still readable,
  `USER_DELETED` queue entry due at `now + team_delete_grace`; **personal delete → hidden +
  queue entry due at `now + personal_delete_grace` (NOT immediate); a user cannot override it**;
  both unset → immediate erase. Plus the orphan test (checkpoint-fail → history skipped).
- **Review checklist:** window source correct per space; `personal_delete_grace` is platform-only
  (no per-team/user override path); team path reuses the queue (no new scheduler); history
  retained for the window; orphan fix present.
- **Depends on:** A1–A4, B1/B3 (window values). **Commit:** `feat(CTRLP-12): delete = deferred erase (team + personal windows)`

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

---

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
  token; thread `user_id`+`team_id`+`trigger` from the queue row (stop dropping `user_id` /
  hard-coding `MEMBER_REMOVED`). **Keep the queue entry NOT-done until `receipt.ok`** (reuses
  the A2 checkpoint-before-history ordering + orphan skip; retry-safe).
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

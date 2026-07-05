# CTRLP-12 (Fred 2.0.2 RGPD-ready) — Merged Triage Review

**Role:** independent incoming coordinator, re-verifying two prior reviews against code.
**Supersedes:** the prior single-reviewer note that lived at this path (its content is
fully folded in below). The Codex review remains at `CTRLP-12-CODEX-QUALITY-REVIEW.md`.
**Scope:** exactly `git diff swift..HEAD` @ `1864748b` — pure CTRLP-12 (retention,
erasure, KPI anonymise, checkpoint owner, team-settings UX, docs). AUTHZ/ReBAC excluded.
**Method:** every finding from both reviews re-verified against `file:line` (read the code,
not the reviewer). Verdicts are mine. No fixes applied.

---

## Executive summary

**Production-ready? No.** Two independent blockers, both re-confirmed against code. One
is *worse* than either prior review stated.

The code that was written is genuinely high quality — clean erasure fan-out, an auditable
`ErasureReceipt`, a pure well-tested resolver, honest per-store isolation tests for the
stores that *are* isolated. But two load-bearing claims of the "provable erasure" feature
do not hold in a real deployment.

### Top 3 risks

1. **KPI anonymise is a no-op in production (BLOCKER, newly sharpened).** The anonymise
   query filters on `dims.scope_type == "session" AND dims.scope_id == <session_id>`.
   **No runtime KPI emit site ever sets that shape** — conversation KPIs carry
   `dims.session_id` + `dims.user_id` (and `exchange_id`), never `scope_type`/`scope_id`.
   The *only* place `scope_type="session"` exists is the anonymise unit test's fabricated
   fixture. So after a receipted "success", KPI rows retaining **`user_id`** (a direct
   identifier) + `session_id` survive indefinitely. The test proves the script works on a
   shape production never writes. This is the single most important finding — it is why an
   independent pass mattered: the prior Claude review marked this path "tested/good."

2. **Deferred delete never fully erases (BLOCKER, when any grace window is set).** The B6
   UI lets an owner set `team_delete_grace`; `delete_or_defer_session` (A5) then hides the
   row and enqueues a `USER_DELETED` entry — but the *only* queue consumer
   (`lifecycle_actions.delete_conversation_and_mark_done`) hardcodes trigger
   `MEMBER_REMOVED` and calls `session_store.delete()` (one metadata row), **never**
   `erase_session`. A6 (the consumer→erase wiring) is not in this diff. Runtime transcript,
   checkpoint, KPI, attachments survive while the UI reports "deleted." Default catalog
   ships windows unset → path degrades to immediate erase, so this is latent until a window
   is configured — but B6 ships the button to configure it.

3. **"Team may only tighten" guardrail is off in the default deployment (major).** The
   resolver takes a team override **as-is, unbounded** when `platform_max is None`, and the
   shipped `conversation_policy_catalog.yaml` defines **no** `team_delete_grace`/`max_idle`
   cap. So via B6 an owner can *loosen* retention arbitrarily — the opposite of the RFC
   guarantee — unless every deployment remembers to set caps.

**Recommendation:** do not enable delete-grace windows or advertise KPI erasure until
blockers 1–2 are fixed. Blocker 1 is a small, self-contained fix (filter on the dim the
runtime actually emits + a test using the real shape). Blocker 2 is the A6 workstream.

Also note: **two uncommitted working-tree changes** are sitting on the branch
(`opensearch_kpi_store.py` param fix + a checkpointer test type-annotation fix) — loose
ends that must be committed or reverted before any PR (see L1).

---

## Merged findings (verdict per finding, most severe first)

Legend — Verdict: **CONFIRMED** (reproduced against code) · **NEEDS-INTENT** (validity
depends on why it was built this way — ask maintainer) · **FALSE-POSITIVE** (with proof).
Src: X=Codex, C=prior Claude, ✦=sharpened/added by this pass.

| # | Sev | Verdict | Src | File:line | Issue | Why it matters | One-line fix |
|---|-----|---------|-----|-----------|-------|----------------|--------------|
| 1 | **blocker** | CONFIRMED ✦ | X, ✦ | `libs/fred-core/.../opensearch_kpi_store.py:258-260` | Anonymise filters `scope_type="session"`+`scope_id`; **no runtime emit sets that shape** (they set `dims.session_id`+`dims.user_id`). Only the test fabricates it. | Erasure receipt reports success while `user_id`+`session_id` persist in every conversation KPI row. RGPD promise false. | Filter on `dims.session_id == session_id` (the emitted dim); add a test using the real `context_aware_tool`/`react_runtime` dim shape. |
| 2 | **blocker** | CONFIRMED | X, C | `scheduler/lifecycle_actions.py:44,77` ⇄ `product/service.py:2681` | Consumer hardcodes `MEMBER_REMOVED` and calls `session_store.delete()`, not `erase_session`. A6 not wired. | Deferred deletes (any grace window) skip the whole fan-out at expiry. | Gate B6/A5 behind A6, **or** route `USER_DELETED`/idle work through `ConversationErasureService` and preserve the trigger. |
| 3 | **major** | CONFIRMED / NEEDS-INTENT | X, C | `scheduler/policies/retention_resolver.py:84-90` + `config/conversation_policy_catalog.yaml` | `platform_max is None` → team value unbounded; catalog ships no `team_delete_grace`/`max_idle` cap. | Owner can loosen retention via B6 — opposite of guardrail. | Require a platform ceiling, or reject a team value when no cap is configured. **Intent Q:** is a per-deployment cap assumed? |
| 4 | **major** | CONFIRMED | X | `sessions/erasure_service.py:104-135` | Attachment + metadata steps have **no** try/except; only KPI/checkpoint/history are isolated — yet docstring (`:86`) says "each store is isolated." | One Knowledge-Flow cleanup failure raises out of `erase_session`, no receipt, downstream stores never attempted. Bites harder once A6 routes deferred deletes here. | Wrap attachments + metadata as their own receipt-producing steps; continue on failure. |
| 5 | **major** | CONFIRMED / NEEDS-INTENT | X, C | `sessions/store.py:153-163` (`get`) vs `:177` (`list_by_team`) | `get()` (→ `_get_owned_session_record` → `get_session`, attachment list/create) does not filter `deleted_at`; only `list_by_team` does. | Soft-deleted conversation still fetchable/attachable by id during the grace window — a UI hide, not an access boundary. | Filter `deleted_at IS NULL` in `get`, or 404 owned soft-deleted reads. **Intent Q:** is post-delete read intended (personal_delete_grace "security review")? |
| 6 | **major** | CONFIRMED | X, C | `runtime_support/sql_checkpointer.py:634-635` + purge/backfill | `__fred_user_id`/`__fred_team_id` only *read*, never injected at write time; `purge_threads_for_user`/`backfill_*` have **no production callers**. | Live threads get `user_id=NULL` owner rows → per-user checkpoint purge silently misses them once A6 lands. | Inject identity at invocation sites, or document per-user erase as backfill-gated. Tie to A6. |
| 7 | **major** | CONFIRMED / NEEDS-INTENT | X | `scheduler/policies/policy_models.py` (no `IDLE_EXPIRED`) | UI exposes `max_idle` but no trigger/sweep erases idle sessions. | Advertised control does nothing. | Add trigger + sweep + dry-run + tests. **Intent Q:** is this the A6d item, out of this diff by design? |
| 8 | minor | CONFIRMED / NEEDS-INTENT | X | `pages/.../TeamSettingsPage.tsx:43` + `hooks/useSelectedTeam.ts:61-64` | Whole settings area gated on `can_administer_owners`; but retention component + backend GET (`CAN_READ`) support read-only for non-owners. | Members/managers cannot view the platform cap the read-only UI was built to show. | Gate per-section; allow retention GET for readers. **Intent Q:** loosen the settings gate this increment? |
| 9 | minor | CONFIRMED | C | `sessions/store.py` mark_deleted/`list_by_team` — **test gap** | Real SQL exercised only via in-memory fake (`test_main.py`); no DB-level test asserts a soft-deleted row is hidden. | A broken UPDATE/WHERE passes CI. | Add `test_metadata_stores.py`: `mark_deleted` then assert `list_by_team` excludes it. |
| 10 | minor | CONFIRMED | C | `product/service.py update_team_retention` — **test gap** | Partial-overlay-over-existing-record + explicit-null-clears branch untested (all PATCH tests start `record=None`). | Core PATCH semantics unverified. | Add a PATCH-over-existing test (omit one field, null another). |
| 11 | minor | CONFIRMED | C | `sessions/erasure_service.py:203-228` — **test gap** | Only the `agent_instance_id is None` resolver branch is tested; instance-not-found + disabled-source untested. | 2/3 unresolved-runtime paths unverified. | Add two resolver-failure tests. |
| 12 | minor | CONFIRMED | C | `scheduler/queue_store.py:49` (`s.merge`, PK `session_id`, `status=PENDING`) | Re-enqueue of same session resets status→PENDING and advances `due_at`. | API replay can postpone erasure indefinitely (UI hides row, so mostly API-reachable). | Only enqueue if no pending entry, or don't advance `due_at` on re-enqueue. |
| 13 | minor | CONFIRMED | X | `product/api.py:~1023` | Endpoint docstring: "Returns 204 … when the session does not exist"; service raises 404. | Clients encode wrong idempotency expectation. | Make delete idempotent, or fix docstring/tests to 404. |
| 14 | minor | CONFIRMED | X | `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` (`session_purge_queue` warning) | Contract says don't use the purge queue as retention mechanism; A5 enqueues into it. | Doc vs impl disagree. | Reconcile once queue is trigger-aware + erase-wired (blocker 2). |
| 15 | minor | CONFIRMED | C | `docs/swift/backlog/BACKLOG.md:3296` | Says personal delete is "immediate … delete means delete"; A5 makes it deferred when `personal_delete_grace` set. | Design text vs implemented behaviour. | Reconcile the backlog text with A5's both-spaces-deferred model. |
| 16 | minor | CONFIRMED | X, C | `docs/swift/PMO-BOARD.md:49`, workplan vs `id-legend.yaml`/BACKLOG | PMO row still "RFC-first / proposed (2026-06-30)", Execution `TBD`, despite ~16 merged commits; workplan ticks vs id-legend "proposed" diverge. | Governance not converged (CLAUDE.md §3.6). | Set PMO status + Execution ref to branch/PR; align id-legend/BACKLOG/workplan. |
| 17 | minor | CONFIRMED | C | `sql_checkpointer.py:~660` `backfill_thread_owners_from_history` | Owner picked via `func.min(user_id)`/`func.min(team_id)`. | Mixed-identity session → arbitrary lexicographic owner. | Assert single owner, or pick earliest by timestamp. |
| 18 | minor | CONFIRMED | C | `TeamSettingsRetention.tsx:~43` | `isLoading` from PATCH discarded (no disable-while-saving); GET `isError` unhandled; `platform_max` unused for inline validation. | Overlapping PATCHes; no error affordance; 422 round-trip to learn a value exceeds cap. | Pull `isLoading`/`isError`; disable while saving; pre-validate vs `platform_max`. |
| 19 | nit | NEEDS-INTENT | X, C | 7 new backend files (list below) | No Apache header. | control-plane-backend convention is **header-less** (15/103 files carry it); fred-core/runtime/frontend files correctly *do* have headers. | **Policy Q:** if "all new files carry header", add to the 7 (trivial batch). Otherwise compliant. |
| 20 | nit | CONFIRMED | X | erasure runtime HTTP helpers `_erase_runtime_checkpoint`/`_erase_runtime_history` | Share client/exception shape. | Minor drift risk. | Optional shared helper once more call sites exist. Acceptable as-is. |
| 21 | nit | CONFIRMED | C | `alembic/.../d2e3f4a5b6c7...py` | `session_metadata.deleted_at` unindexed; `list_by_team` now filters it. | Full-scan risk only at scale. | Optional partial index `WHERE deleted_at IS NULL`. |

### Loose ends (not in either review's table)

| # | Sev | Verdict | Item | Detail |
|---|-----|---------|------|--------|
| L1 | major | CONFIRMED | **Uncommitted working-tree changes** on the branch | `opensearch_kpi_store.py`: `update_by_query(conflicts=…, refresh=…)` → `params={…}` (defensive, plausibly correct, **untested** — the fake swallows both forms). `test_sql_checkpointer_owner.py`: `RunnableConfig` annotation + `list(...)` wrap (looks like a type-check/lint fix). **Both must be committed or reverted before a PR** — and if the reported-green test/lint depended on them, that must be re-run. |

---

## Test coverage (error paths + edges, not line count)

**Genuinely strong (real side-effect assertions, not tautological):**
- Erasure per-store isolation for the stores that *are* isolated — KPI-fail and history-fail
  isolation, receipt `ok` aggregation, exact HTTP call order (`test_main.py`).
- Checkpoint-before-history ordering + orphan guard: checkpoint-fail asserts history DELETE
  is **never** issued — the strongest test in the set.
- Runtime-unresolved (no `agent_instance_id`): runtime stores fail, KPI/metadata still erased.
- Resolver clamp boundaries: team==cap, team>cap→`would_exceed`, `platform_max=None`, both-None,
  original-string preservation.
- `personal_delete_grace` non-overridability: `_RaisingOverrideStore` proves the override store
  is never consulted on the personal path. Strong negative test.

**Gaps that map onto real risk:**
- **KPI anonymise is tested only against a fabricated `scope_type="session"` shape the runtime
  never emits (blocker 1).** The test is green *and wrong*. Highest-priority coverage fix.
- Attachment/KF cleanup failure isolation — untested (finding 4); the code isn't isolated there.
- `mark_deleted` + `list_by_team` hide — DB-level test missing, fake only (finding 9).
- `update_team_retention` partial-overlay over an existing record — untested (finding 10).
- `_resolve_runtime_base_url` — 2/3 failure branches untested (finding 11).
- No end-to-end test that the deferred path erases at expiry (mirrors the code gap, blocker 2).
- No test the queue distinguishes `MEMBER_REMOVED` from `USER_DELETED`/future `IDLE_EXPIRED`.

**Note on runnability:** the Codex pass could not execute pytest (no `uv`/venv on its PATH); this
pass verified statically. `make test` in each touched module still needs to be run green before
any fix is called done (per Ground rules).

---

## Missing Apache headers — 7 new backend files

Convention is **per-directory**. New fred-core / fred-runtime / frontend files correctly carry
the header. These 7 sit in `control-plane-backend`, where the local convention is header-less
(15/103 files carry it). So none violates its *local* convention — action needed **only if**
policy is "all new source files carry the header regardless of neighbors":

- `apps/control-plane-backend/alembic/versions/c1d2e3f4a5b6_add_team_policy_override.py`
- `apps/control-plane-backend/alembic/versions/d2e3f4a5b6c7_add_session_metadata_deleted_at.py`
- `apps/control-plane-backend/control_plane_backend/models/team_policy_override_models.py`
- `apps/control-plane-backend/control_plane_backend/scheduler/policies/retention_resolver.py`
- `apps/control-plane-backend/control_plane_backend/sessions/erasure_service.py`
- `apps/control-plane-backend/control_plane_backend/teams/policy_override_store.py`
- `apps/control-plane-backend/tests/test_retention_resolver.py`

## Duplication / dead code

No blocker-grade copy-paste. Good reuse: resolver reused by GET/PATCH/`_resolve_delete_window`;
frontend uses generated RTK hooks; checkpoint delete reuses `adelete_thread`. Owner-index API
(`purge_threads_for_user`, `backfill_*`) is dead *for now* — intentional A6 scaffolding, flagged
as finding 6 for the latent correctness trap, not as code to delete. Runtime HTTP delete helpers
lightly duplicated (finding 20, acceptable).

---

## What I verified vs could not

**Verified (read code / greps):** blockers 1–2 at both call sites; the resolver `None` branch +
the shipped catalog; the erasure attachment/metadata non-isolation vs the "isolated" docstring;
`get` vs `list_by_team` filter; that **no** production path sets `scope_type="session"` (only the
test); identity-injection absence + no purge/backfill callers; the frontend gate; the DELETE
docstring vs 404; the `s.merge` re-enqueue; header status of every new file (and the header-less
control-plane convention, 15/103); the two uncommitted working-tree diffs.

**Could not verify:** live OpenSearch `update_by_query`; GKE service-to-service / service-token
behaviour; browser rendering; and I did not yet run `make test`/`make code-quality` (static pass).

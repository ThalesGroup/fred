# CTRLP-12 — Coordination & Dispatch Board

Single source of truth for finishing CTRLP-12 (Fred 2.0.2 RGPD-ready).
Companion to the merged review: [CTRLP-12-QUALITY-REVIEW.md](CTRLP-12-QUALITY-REVIEW.md).

**Roles.** Coordinator (Claude, this session): triages, decomposes, and *reviews every
returned commit* against code before it counts as done. Maintainer (Dimitri): decides open
questions, launches one agent per work item using the prompts below, and brings each result
back ("work done") for review. Executors (fresh Claude/Codex agents): each does exactly one
work item, verifies green, makes one commit, stops.

**Loop.** Coordinator says what to DECIDE / DISPATCH → maintainer dispatches → agent returns
one commit → maintainer says "work done: W#" → coordinator reviews fully → **FULLY OK** or
**CHANGES NEEDED** → continue.

**Hard rules for every executor.** One work item only; no scope creep; reuse over new code;
one commit (conventional prefix + `Co-Authored-By: Claude Opus 4.8 (1M context)
<noreply@anthropic.com>`); never `--no-verify`; never push; green `make code-quality` +
`make test` in each touched module before committing; if the code doesn't match the brief,
STOP and report.

---

## Status board

| Item | Title | Finding | Wave | Depends on | Status | SHA |
|------|-------|---------|------|-----------|--------|-----|
| C1 | KPI anonymise → emitted `dims.session_id` | blocker 1 | — | — | ✅ merged + reviewed | `85e55437` |
| C2 | Platform caps + reject override when unset | major 3 | — | — | ✅ merged + reviewed (caps P30D/P365D signed off, D1) | `00c126d9` |
| W3 | Isolate attachment + metadata erasure steps | major 4 | 1 | — | ✅ merged + reviewed | `30e717a1` |
| W5 | Idempotent purge-queue enqueue | minor 12 | 1 | — | ✅ merged + reviewed | `cd4007bb` |
| W6 | Commit checkpointer test annotations | L1b | 1 | — | ✅ merged + reviewed | `4d9e5cb8` |
| W8 | Apache headers on 7 new backend files | nit 19 | 1 | — | ✅ merged + reviewed | `7427ef9b` |
| W4 | Close coverage gaps (soft-delete/PATCH/resolver) | minor 9/10/11 | 2 | W3 (done) | ✅ merged + reviewed | `998d9bca` |
| W7 | Doc convergence + contract reconcile | minor 5/13/14/15/16 | 3 | all above (done) | ✅ merged + reviewed | `b8c7d5f7` |
| WB | A6 erase-at-expiry (+ idle sweep, owner identity) | blocker 2 / 6,7,17 | B | **Simon: A6a service token** | 🚫 blocked | — |

Legend: ✅ done · ⏳ ready · ⛔ sequenced hold · 🚫 external blocker.

---

## Decisions

**Made:** A6 built in Batch B after Simon's service token · caps ship in catalog · finding 5
= doc-only (soft-deleted stays readable by id during grace: intended) · finding 8 (loosen
settings gate) = out of scope · DELETE = fix docstring to 404 (no behavior change) · all new
files get Apache header · commit both leftover working-tree changes ·
**D1 — retention cap values accepted: `team_delete_grace: P30D`, `max_idle: P365D`**
(2026-07-02; teams may only tighten below).

**Open — needs maintainer:** none currently.

**Blocked externally:**
- WB — needs the AUTHZ-01 service-token / `can_manage_platform` admin mechanism from Simon
  before the background erase worker can authenticate its cross-service calls.

---

## Review log

| Item | Reviewed | Verdict | Notes |
|------|----------|---------|-------|
| C1 | coordinator | ✅ FULLY OK | anonymise now matches emitted `dims.session_id`; test uses real shape; 31 kpi tests green. |
| C2 | coordinator | ✅ FULLY OK | resolver rejects no-cap override; real-catalog regression tests; caps P30D/P365D (D1). |
| W3 | coordinator | ✅ FULLY OK | try/except mirrors _anonymise_kpi; test monkeypatches KF-cleanup to raise and asserts REAL side effects (metadata rows emptied, KPI call made, both runtime DELETE URLs issued) → fan-out not aborted. Cherry-picked from agent worktree; 216 offline tests green. |
| W5 | coordinator | ✅ FULLY OK | enqueue skips write when a PENDING row exists; DONE rows re-schedulable; DB test proves due_at not postponed on replay. |
| W6 | coordinator | ✅ FULLY OK | type-annotation-only; fred-runtime code-quality + 6 checkpointer tests green. |
| W8 | coordinator | ✅ FULLY OK | canonical Apache block on all 7 files (above `from __future__` where present); ruff/basedpyright green. |
| W4 | coordinator | ✅ FULLY OK | run inline. DB soft-delete (hidden from list, still get()-able); PATCH overlay (omit keeps, null clears); resolver instance-not-found + source-disabled branches (ok=false, no HTTP). 220 offline tests green. |
| W7 | coordinator | ✅ FULLY OK | run inline. DELETE docstring→404; get() soft-delete comment; product contract reconciled (purge-queue = A5 scheduler, A6 pending; soft-delete read contract); BACKLOG personal-delete text; PMO/id-legend status+exec-ref (flag A6 blocker); WORKPLAN Q1–Q8 SHAs + A3 correction. ruff clean; 220 tests green. |

**Batch A COMPLETE (8/8): C1, C2, W3–W8.** Remaining: Batch B (A6) only, blocked on Simon.

**Dispatch note (harness):** agent worktrees were created on *inconsistent* bases (a
git-worktree race — some at branch tip `0276a40f`, some at ancestor `50ecf55f` where the
CTRLP-12 files don't exist). W3's agent self-corrected to the tip; W5/W6/W8's worktrees were
mis-based, so those three were executed directly in the main tree by the coordinator. For
future waves: verify each worktree's base (`git worktree list`) right after launch, or run
small items inline.

---

## Dispatch prompts

Paste one block per fresh agent. Wave 1 (W3, W5, W6, W8) can run in parallel (disjoint
files). W4 after W3. W7 last (coordinator fills its SHA list first).

### W3 — Isolate attachment + metadata erasure steps

```
You are working in the Fred monorepo at /home/dimi/Fred/fred (branch 1883-…-ctrlp-12).
Do ONLY the task below. Do not refactor, rename, or touch unrelated files. If the code
does not match this description, STOP and report — do not guess or expand scope.

TASK (bug fix, major): In apps/control-plane-backend/control_plane_backend/sessions/
erasure_service.py, ConversationErasureService.erase_session fans out erasure across
stores and its docstring promises "Each store is isolated: one failure is recorded and
the rest run." That promise is currently BROKEN for the first two steps:
  - the attachments block (list_for_session → loop _delete_knowledge_flow_attachment →
    delete_for_session → append STORE_ATTACHMENTS result) has NO try/except, and
  - the session-metadata delete step has NO try/except.
So a single Knowledge-Flow cleanup failure (or metadata delete failure) raises straight
out of erase_session — no receipt is returned and KPI/checkpoint/history are never
attempted. The KPI/checkpoint/history steps below them ARE already isolated (see
_anonymise_kpi and the runtime helpers) — mirror that pattern.

CHANGE:
  - Wrap the attachments block (KF cleanup loop + delete_for_session) in try/except
    Exception: on failure append StoreErasureResult(store=STORE_ATTACHMENTS, ok=False,
    error=...) and CONTINUE the fan-out (do not raise). On success keep the existing
    ok=True result with deleted_count=len(attachments).
  - Wrap the session-metadata delete in try/except Exception the same way
    (STORE_SESSION_METADATA, ok=False, error=... on failure; continue).
  - Match the existing error-string style used by _anonymise_kpi.

TESTS: In apps/control-plane-backend/tests/test_main.py, add a test (mirror the existing
erasure isolation tests, e.g. the KPI-failure / history-failure isolation cases) proving:
when _delete_knowledge_flow_attachment raises, the receipt records attachments ok=False
AND session_metadata + kpi + runtime checkpoint/history are still attempted and receipted
(i.e. the fan-out was not aborted).

VERIFY (must be green before you commit):
  cd apps/control-plane-backend
  make dev            # first run only: bootstraps .venv via uv
  make code-quality
  make test           # offline unit tests
  # (targeted while iterating: VIRTUAL_ENV= .venv/bin/uv run pytest -q --disable-socket --allow-unix-socket tests/test_main.py -k erase)

DELIVERABLE: one commit, no push, do not use --no-verify. Message:
  fix(CTRLP-12): isolate attachment + metadata steps in erase_session
  <body: what/why in 3-5 lines>

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Then STOP and report: the diff, and confirmation that code-quality + tests are green.
```

### W5 — Idempotent purge-queue enqueue

```
You are working in the Fred monorepo at /home/dimi/Fred/fred (branch 1883-…-ctrlp-12).
Do ONLY the task below. Do not refactor unrelated code. If the code does not match this
description, STOP and report — do not guess or expand scope.

TASK (bug fix, minor): apps/control-plane-backend/control_plane_backend/scheduler/
queue_store.py defines enqueue(...). It builds a PurgeQueueRow (primary key = session_id)
with status=PENDING and a new due_at, then calls s.merge(row). Because the PK is
session_id, a SECOND enqueue of the same session (e.g. an API replay of the delete) merges
over the existing row — resetting status back to PENDING and pushing due_at further into
the future. That lets a repeated call indefinitely postpone the scheduled erasure.

Read the whole file first (enqueue, list_due, mark_done) to preserve existing semantics.

CHANGE: make enqueue idempotent for an already-pending session — if a PENDING entry for
that session_id already exists, do NOT overwrite it (keep its original due_at and status).
Only insert when there is no pending entry. Do not change list_due / mark_done behavior.

TESTS: In apps/control-plane-backend/tests/ (see tests/test_metadata_stores.py for the
DB-backed store test pattern), add a test: enqueue a session with due_at=T1, then enqueue
the same session with a later due_at=T2; assert the stored due_at is still T1 (erasure was
not postponed).

VERIFY (green before commit):
  cd apps/control-plane-backend
  make dev            # first run only
  make code-quality
  make test

DELIVERABLE: one commit, no push, no --no-verify. Message:
  fix(CTRLP-12): make purge-queue enqueue idempotent for pending sessions
  <body 3-5 lines>

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Then STOP and report the diff + green confirmation.
```

### W6 — Commit the checkpointer test annotation fix

```
You are working in the Fred monorepo at /home/dimi/Fred/fred (branch 1883-…-ctrlp-12).
Do ONLY the task below. If anything is unexpected, STOP and report.

CONTEXT: The working tree has an UNCOMMITTED change in
libs/fred-runtime/tests/test_sql_checkpointer_owner.py (a leftover from prior work):
it adds `from langchain_core.runnables import RunnableConfig`, changes the _config helper
return annotation from `dict` to `RunnableConfig`, and wraps a fetchall() result in
`list(...)`. These are type-annotation/lint fixes only — no behavior change.

TASK: Verify this uncommitted change is correct and self-consistent (run the gates below),
then commit it AS-IS. Do not add other changes. Do not touch any other file.

VERIFY (green before commit):
  cd libs/fred-runtime
  make dev            # first run only: bootstraps .venv via uv
  make code-quality
  make test

DELIVERABLE: one commit containing only that file, no push, no --no-verify. Message:
  chore(CTRLP-12): type annotations in checkpointer owner test

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Then STOP and report the diff + green confirmation. If code-quality/tests are NOT green
with this change, STOP and report the failure instead of committing.
```

### W8 — Apache headers on 7 new backend files

```
You are working in the Fred monorepo at /home/dimi/Fred/fred (branch 1883-…-ctrlp-12).
Do ONLY the task below. Do not modify file contents other than adding the header. If a
file already has the header, skip it and note that. STOP and report if anything differs.

TASK (nit): Prepend the standard Apache 2.0 license header to these 7 new files. Copy the
EXACT header block already used elsewhere in this repo — use
libs/fred-core/fred_core/history/history_models.py as the canonical example (the block
from the first `# Copyright …` line through `# limitations under the License.`), followed
by one blank line, then the file's existing content.

FILES:
  apps/control-plane-backend/alembic/versions/c1d2e3f4a5b6_add_team_policy_override.py
  apps/control-plane-backend/alembic/versions/d2e3f4a5b6c7_add_session_metadata_deleted_at.py
  apps/control-plane-backend/control_plane_backend/models/team_policy_override_models.py
  apps/control-plane-backend/control_plane_backend/scheduler/policies/retention_resolver.py
  apps/control-plane-backend/control_plane_backend/sessions/erasure_service.py
  apps/control-plane-backend/control_plane_backend/teams/policy_override_store.py
  apps/control-plane-backend/tests/test_retention_resolver.py

NOTE: For files that begin with `from __future__ import annotations`, the header goes
ABOVE that line. Preserve all existing content exactly.

VERIFY (green before commit):
  cd apps/control-plane-backend
  make dev            # first run only
  make code-quality   # ruff must still pass

DELIVERABLE: one commit, no push, no --no-verify. Message:
  chore(CTRLP-12): add Apache license headers to new backend files

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Then STOP and report which files were changed + green confirmation.
```

### W4 — Close coverage gaps (dispatch AFTER W3 merged; both touch test_main.py)

```
You are working in the Fred monorepo at /home/dimi/Fred/fred (branch 1883-…-ctrlp-12).
Do ONLY the task below — add tests, no production code changes. If a described behavior
does not match the code, STOP and report.

TASK (test coverage): Add three tests that assert real behavior (not tautologies).

1) DB-level soft-delete hide + intended readability. In
   apps/control-plane-backend/tests/test_metadata_stores.py (DB-backed store tests):
   create a session_metadata row, call the store's mark_deleted(...), then assert
   list_by_team EXCLUDES it, AND get() STILL RETURNS it (a soft-deleted conversation stays
   directly fetchable by id during the grace window — this is intended: post-incident /
   evaluation read). This closes a gap where the hide filter is only covered by an
   in-memory fake today.

2) PATCH-over-existing retention override. In apps/control-plane-backend/tests/test_main.py
   (see the existing PATCH /teams/{id}/retention tests), add a case that starts from an
   EXISTING stored override and PATCHes it partially: omit one governed field (asserts it
   keeps its stored value) and send explicit null for the other (asserts it clears). All
   current PATCH tests start from record=None, so this overlay path is untested.

3) Runtime-base-url resolver failure branches. In test_main.py (or the nearest erasure
   test module), cover the two untested branches of
   ConversationErasureService._resolve_runtime_base_url: (a) agent instance not found for
   team, (b) runtime source disabled/missing. Assert the checkpoint + history store results
   are ok=False with the correct "unresolved runtime" error, and no HTTP call is made.

VERIFY (green before commit):
  cd apps/control-plane-backend
  make dev            # first run only
  make code-quality
  make test

DELIVERABLE: one commit, no push, no --no-verify. Message:
  test(CTRLP-12): cover soft-delete hide, PATCH overlay, resolver failures
  <body 3-5 lines>

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Then STOP and report the diff + green confirmation.
```

### W7 — Doc convergence + contract reconcile (dispatch LAST; coordinator fills SHA list)

```
You are working in the Fred monorepo at /home/dimi/Fred/fred (branch 1883-…-ctrlp-12).
Do ONLY the doc/comment edits below. No behavior/code-logic changes except the one
docstring edit named. If a referenced line/section has moved, find it by content; if you
cannot, STOP and report.

TASK (documentation convergence — CLAUDE.md §3.6):
1) DELETE endpoint docstring: in control_plane_backend/product/api.py, the delete-session
   endpoint docstring says it returns 204 when the session does not exist, but the service
   raises 404. Fix the DOCSTRING to state 404 for a missing/non-owned session (do NOT
   change behavior).
2) Soft-delete access contract: add a short comment on PostgresSessionStore.get() in
   control_plane_backend/sessions/store.py noting that get() intentionally does NOT filter
   deleted_at — a soft-deleted conversation stays fetchable by id during the grace window
   for post-incident/evaluation read, while list_by_team hides it. Document the same
   contract in docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md.
3) Purge-queue contract: in CONTROL-PLANE-PRODUCT-CONTRACT.md, reconcile the existing
   "do not use session_purge_queue as retention mechanism" note with CTRLP-12 A5, which now
   enqueues USER_DELETED entries into it (note that full erase-at-expiry, A6, is pending).
4) Personal-delete text: in docs/swift/backlog/BACKLOG.md, the personal-delete entry says
   "immediate erase_session (delete means delete)"; reconcile it with A5's both-spaces-
   deferred behavior (immediate only when personal_delete_grace is unset).
5) Governance convergence: set the CTRLP-12 row in docs/swift/PMO-BOARD.md to the actual
   state (not "proposed/TBD") with Execution ref = the working branch; align
   docs/swift/data/id-legend.yaml and docs/swift/FRED-2.0.2-WORKPLAN.md, and record these
   CTRLP-12 quality-phase commit SHAs in the workplan tracker:
     85e55437 fix: KPI anonymise → emitted dims.session_id (blocker 1)
     00c126d9 fix: enforce platform retention caps; reject override when unset (finding 3)
     30e717a1 fix: isolate attachment + metadata steps in erase_session (finding 4)
     cd4007bb fix: idempotent purge-queue enqueue (finding 12)
     4d9e5cb8 chore: checkpointer owner test type annotations (L1b)
     7427ef9b chore: Apache license headers on 7 new backend files (finding 19)
     998d9bca test: soft-delete hide, PATCH overlay, resolver failures (findings 9/10/11)
   (Batch B / A6 — blocker 2, findings 6/7/17 — remains open, blocked on Simon's
   AUTHZ-01 service-token; do NOT mark CTRLP-12 fully done in PMO until it lands.)

VERIFY: no code logic changed; if api.py was touched, run `cd apps/control-plane-backend &&
make code-quality`. Otherwise doc-only, no gates needed.

DELIVERABLE: one commit, no push, no --no-verify. Message:
  docs(CTRLP-12): converge governance + reconcile retention contracts

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Then STOP and report the list of files changed.
```

### WB — A6 erase-at-expiry (BLOCKED — coordinator writes prompt after Simon confirms token)
```
(Not ready. Needs the AUTHZ-01 service-token / can_manage_platform mechanism. Coordinator
will author this prompt once the auth story is confirmed.)
```

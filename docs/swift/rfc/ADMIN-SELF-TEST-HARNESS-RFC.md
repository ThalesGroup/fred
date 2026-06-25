# RFC — Admin Self-Test Harness and Embedded Golden Corpus

**Status:** Draft for team review
**Author:** Dimitri Tombroff
**Date:** 2026-06-25
**Area:** `frontend`, `control-plane-backend`, `knowledge-flow-backend`, `fred-agents`
**Extends:** VALID-01 (`docs/swift/backlog/BACKLOG.md §3b.7`) — live-stack validation
**Proposed IDs:** `VALID-02` (harness), `VALID-03` (golden corpus fixture)

---

## 1. Why this RFC exists

The user-facing surface of Fred has many subtle, deployment-sensitive integration
points that no offline unit test covers: selecting a prompt from the personal or
team marketplace, choosing a search mode, scoping a document library, attaching a
file. These work in CI against fakes (`apps/fred-agents/tests/test_smoke.py`) but
that does not answer the operational question:

> _In this deployed environment, right now, with the real LLM, real vector store,
> real auth, and real corpus — does feature X actually work end-to-end for a user?_

VALID-01 answers the headless backend half of this through a YAML scenario runner.
This RFC adds the **interactive, live, in-product half**: a platform-admin-only
self-test page that drives the real product flows against a small, deterministic,
embedded **golden corpus**.

This is a complement to — not a replacement for — a future Playwright suite. The
two occupy different axes:

| Layer | Validates real UI widgets | Validates live deployed stack | Runs in CI |
| --- | :---: | :---: | :---: |
| Playwright (future) | ✅ | ⚠️ if pointed at a stack | ✅ |
| Admin self-test page (this RFC) | ✅ if it drives real components | ✅ | ❌ |
| VALID-01 scenario runner | ❌ | ✅ headless | ✅ (skips without live pod) |

---

## 2. Goals and non-goals

### Goals

1. A platform-admin-only page with ~5–10 one-click "journeys", each invoking a real
   agent request through the **real product API path** (the same RTK Query hooks the
   app uses), with a mix of options (prompt selection, search mode, library scope,
   attachment).
2. Each journey produces a deterministic **pass / fail / skipped** verdict with a
   short reason — not a wall of raw output.
3. A one-click **"create golden corpus"** action that seeds a tiny, deterministic
   fixture (two libraries + a handful of crafted documents + one or two test
   prompts) designed so that retrieval has a single provable answer.
4. A matching **"destroy golden corpus"** action; seeding is idempotent.
5. The entire harness — page, routes, and corpus seeding — is **absent unless
   explicitly enabled by configuration**, so it does not ship active in production.

### Non-goals

- Not a load/performance test.
- Not a replacement for VALID-01's headless scenarios or a future Playwright suite.
- Not a general fixtures/seed-data framework — it is scoped to validation only.
- No exact-text assertions on LLM output (see §5.3).

---

## 3. The self-test page

### 3.1 Placement and access

- New admin-only route, e.g. `rework/components/pages/AdminSelfTestPage/`, surfaced
  only in the platform-admin navigation surface.
- Two independent gates, both required:
  1. **Authorization** — platform-admin role (REBAC), enforced server-side on every
     harness endpoint, not just hidden in the UI.
  2. **Configuration** — a backend feature flag (e.g. `self_test.enabled`,
     default `false`). When off, the harness routes return `404` and the frontend
     does not render the nav entry. Production ships with it off.

### 3.2 Drive the *real* components (the key design choice)

The page must not reimplement its own prompt picker / search-mode toggle / library
scoper with ad-hoc buttons. If it does, it validates the backend but leaves the exact
UI-wiring bug class untested. Instead it **embeds and drives the real components**
already used in the chat composer (e.g. `ContextPromptPicker`, the search-mode
control, the library scoper) and asserts on the request payload and streamed
response. This way a single page covers UI wiring *and* live backend in one shot.

### 3.3 Output

Each journey row shows: name, status chip (`pass` / `fail` / `skipped`), duration,
and an expandable detail (the assertion that decided the verdict, plus a trace/KPI
link tagged as synthetic). A "run all" button runs the suite sequentially.

---

## 4. The embedded golden corpus

### 4.1 Principle — make a nondeterministic system assertable

A real RAG stack returns nondeterministic prose. The corpus is crafted so the
*retrieval* outcome is unambiguous, and assertions check **which document was
retrieved / cited**, not the exact wording.

Example fixture:

- Library **A** ("fred-selftest-alpha") contains a doc with a unique marker fact:
  _"The Fredchurro festival takes place in Marchtober."_
- Library **B** ("fred-selftest-beta") contains only unrelated content.
- Journey: ask _"When is the Fredchurro festival?"_
  - scoped to **A** → must cite the alpha doc / contain `Marchtober`.
  - scoped to **B** → must **not** surface that fact.

The same trick gives deterministic checks for:
- **search mode** — a doc retrievable by an exact rare keyword but not by paraphrase
  (and the inverse) distinguishes keyword vs semantic vs hybrid.
- **prompt selection** — a test prompt that injects a known marker phrase into the
  system instruction; the journey asserts the marker influences the output.

### 4.2 Seeding mechanism

Seeding reuses **existing** product APIs, not a new backdoor:
- libraries + documents via the knowledge-flow ingestion path,
- test prompts via the control-plane prompt API
  (`/control-plane/v1/teams/{team_id}/prompts`).

All fixture data is created under a **dedicated system/test team scope**, never a
real user's team, so it cannot pollute real libraries, prompts, KPIs, or traces.
Synthetic data is tagged so analytics/trace dashboards can filter it out.

### 4.3 Idempotency and teardown

- "Create golden corpus" is idempotent — re-running detects existing fixture by a
  stable name/tag and reconciles rather than duplicating.
- "Destroy golden corpus" removes libraries, documents, and prompts created by the
  fixture. Destroy is the inverse of create; neither touches non-fixture data.

### 4.4 Configuration gating

The corpus definition (documents, libraries, prompts, expected markers) lives behind
the same `self_test` configuration block. When disabled, no fixture data, seeding
routes, or corpus definition is loaded. This is how we keep it out of production by
default while still allowing a staging/dev operator to flip it on for a validation
run.

---

## 5. Assertion catalogue (initial journeys)

Each is structural and deterministic. Numbers are a starting set, not frozen.

1. **Bare execution** — invoke the default agent with no options; assert a streamed
   response arrives and a KPI turn is recorded.
2. **Personal prompt selection** — select a personal test prompt; assert its marker
   phrase influences the output.
3. **Team prompt selection** — same via a team-marketplace prompt; assert team-scope
   resolution works.
4. **Library scope (positive)** — scope library A; assert the alpha marker fact is
   returned.
5. **Library scope (negative/isolation)** — scope library B; assert the alpha fact is
   *not* returned.
6. **Search mode — keyword** — query a rare exact term; assert the keyword-only doc
   is retrieved.
7. **Search mode — semantic** — paraphrased query; assert the semantically-matched
   doc is retrieved.
8. **Attachment** — attach a small fixture file; assert it is referenced/usable.
9. **(Optional) HITL resume** — reuse VALID-01's `test_assistant` two-phase flow,
   driven from the UI.

### 5.3 Assertion discipline

- Assert on structure: streamed? doc cited? marker present? KPI recorded?
- Never assert exact LLM prose.
- Tolerate latency; each journey has a timeout and degrades to `fail` with a reason,
  never hangs the page.

---

## 6. Alternatives considered

1. **Playwright-only.** Tests real UI but, in CI with fakes, does not validate the
   live deployed stack (real LLM/vector store/config). Complementary, not a
   substitute; deferred.
2. **Admin page with its own ad-hoc buttons.** Simpler, but leaves the UI-wiring bug
   class untested. Rejected in favour of driving the real components (§3.2).
3. **Extend the VALID-01 YAML scenario runner only.** Already exists and is the right
   headless tool, but cannot validate the actual UI a user clicks. This RFC reuses
   its corpus and assertion philosophy rather than duplicating it.
4. **Ship corpus always-on.** Rejected — production pollution, cost, and trace noise.
   Hence the configuration gate (§4.4).

---

## 7. Impact on existing contracts

- **No new public product contract** is intended: seeding reuses existing
  knowledge-flow ingestion and control-plane prompt APIs. The harness adds
  admin-only, flag-gated endpoints only (run-journey / seed / teardown / status).
  Any such endpoint that becomes part of the frozen surface must be recorded in
  `CONTROL-PLANE-PRODUCT-CONTRACT.md`.
- Shares fixtures and assertion philosophy with VALID-01; the golden corpus should
  be authored so the headless scenario runner can consume the same fixture.
- **Note for Simon:** the VALID-01 scenario files referenced in `BACKLOG.md §3b.7`
  (`apps/fred-agents/tests/scenarios/s1_*.yaml`) are not present on disk; the corpus
  work should reconcile that before sharing fixtures.

---

## 8. Proposed tracking (to be created on confirmation)

| ID | Title | Backlog | PMO |
| --- | --- | --- | --- |
| `VALID-02` | Admin self-test harness page (real-component journeys) | new entry under BACKLOG §3b.7 | new row |
| `VALID-03` | Embedded golden corpus fixture (config-gated, idempotent seed/teardown) | new entry under BACKLOG §3b.7 | new row |

Both `parent: VALID-01`. Not created yet — pending developer confirmation per the
CLAUDE.md task lifecycle (RFC → backlog → confirmation → issue → implementation).

---

## 9. Resolved decisions and open questions

**Resolved (2026-06-25):**

1. **Team scope** → a **dedicated synthetic team** (`self_test.team_id`, default
   `fred-selftest`), never a real user's space. Safe to wipe; the harness deletes
   every document and library it creates there.
2. **Orchestration** → a **backend orchestrator** endpoint runs the suite and streams
   per-step results over SSE (chosen over client-side RTK calls), so a K8s CronJob —
   not just the UI — can drive the ~2h live-release validation.
3. **Seed and teardown ARE validation steps.** Rather than treating fixtures as inert
   setup, the campaign's ingest steps validate ingestion+indexing and its delete steps
   validate document/library deletion. Teardown always runs (even on a mid-run
   failure) so the synthetic team never leaks fixtures.

**Still open:**

- Is the feature flag a global config value, or per-environment chart value only?
- Minimum corpus size that still exercises keyword-vs-semantic distinctly without
  slow ingestion.
- Should synthetic KPI/trace data be physically separated or just tagged?
- Auth for the unattended CronJob: reuse a service-account/M2M token (the interactive
  page reuses the admin's bearer token; a cron has no user token).
- **Corpus readability constraint (learned 2026-06-25):** the caller must be able to
  *read* the libraries it creates. Admin-create on a team grants write, not read —
  so a team-owned corpus only works if the triggering identity is a *member* of that
  team. The prototype therefore defaults `team_id: personal` (the caller's own space,
  always readable). For the CronJob, either run as a service account that is a member
  of the synthetic team, or keep the corpus in that account's personal scope.

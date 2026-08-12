# PR #2309 review notes — for joint cross-check (Claude + Codex + developer)

Working notes for issue #2125 / PR #2309 ("fix(#2125): make the Keycloak
user-token refresh async, coalesced and bounded"), branch
`2125-fixturn-07-synchronous-keycloak-token-refresh-call-blocks-the-event-loop-in-async-paths`.
Captured at commit `29f551ee` ("merged latest swift", clean merge — no
conflict markers found, verified 2026-08-12).

Purpose: this branch is unusually dense (5 commits, heavy async/security
surface, 7 prior `/code-review` rounds per the PR description). The developer
asked for a `/code-review max` pass, then wants to cross-check the result
jointly with Codex before deciding what's real and what to act on. This file
is that starting point — not a verdict. Every item below was independently
re-verified against the merged HEAD (file/line still matches), not just the
pre-merge diff.

Author is trusted and the PR's own write-up is unusually rigorous (live
Keycloak runs, A/B timing, reverted-fix test proofs) — so treat the items
below as "worth a second pair of eyes," not "assumed broken."

---

## ✅ Fixed on this branch (2026-08-12)

Three items landed directly on this PR after joint Claude+Codex review,
each implemented by an independent subagent from a fully-specified brief,
then re-verified line-by-line (not just trusted) before being counted done.
Full suites green: frontend `tsc --noEmit` clean, `prettier --check` clean,
`vitest run src` 1145 passed/2 skipped; backend `make code-quality` clean,
`make test` 896 passed.

### 0. Late Keycloak refresh after explicit logout can resurrect a live bearer — FIXED
Found by Codex, severity **High** (not Critical — extends a legitimate
user's own credential past logout, doesn't mint one for an attacker).
Verified directly against `apps/frontend/node_modules/keycloak-js/dist/keycloak.js`:
`updateToken()`'s XHR handler calls `setToken()` **synchronously**,
unconditionally overwriting `kc.token`/`kc.tokenParsed`, BEFORE resolving the
promise our code awaits. `Logout()` bumps `authEpoch` and clears
`localStorage`, but a refresh that was already in flight resurrects
`keycloakInstance.token` in memory regardless — and `GetToken()` read that
live field first, before falling back to (correctly-cleared) `localStorage`.
Confirmed the existing test mock structurally could not catch this (its
`token` getter only ever moves toward `undefined`, never gets mutated back).

Fix: `sessionDied` renamed `sessionInvalidated`, its `= true` assignment
centralized inside `clearPersistedToken()` (the documented single owner of
session teardown — already called from all 3 teardown paths), and
`GetToken`/`GetRefreshToken`/`GetTokenParsed`/`GetTokenSecondsLeft` all gate
on it — dropping `GetTokenSecondsLeft`'s old `&& !tokenParsed` conjunct,
which was the exact loophole letting a resurrected `tokenParsed` suppress the
dead-session report. New regression test mutates a "live" mock value from
inside a pending `updateTokenImpl`, after `CallLogout()` has already run,
mirroring keycloak-js's real ordering. `apps/frontend/src/security/KeycloakService.ts` + `.test.ts`.

### 3→FIXED. Agent-hook refresh path discards an empty/falsy result
`kf_base_client.py`'s `_try_refresh_token` agent-hook branch now checks
`resolve_refresh_result`'s return for emptiness and returns `False` with an
error log, matching the sibling `_refresh_cb` branch's existing shape. New
test: `test_kf_base_client_refresh_shapes.py::test_agent_hook_empty_token_fails_fast_instead_of_reporting_success`.

### 5→FIXED. §8.45 collision turned out to be four collisions, not one
Re-grepping after the merge showed this PR's own 8.45/8.46/8.47/8.48 each
collided with a DIFFERENT section that landed on `swift` independently while
this PR was unmerged (CACHE-01, Alembic, FinishReason, CorpusTreeService —
8.45 alone was claimed by three different sections). Renumbered this PR's
four entries to 8.48-8.51 (after the file's real current highest, 8.47) and
updated every genuine cross-reference across 9 files (RFC, performance
review doc, code comments/docstrings, test docstrings) — carefully
distinguishing "this PR's own §8.4x" from "an unrelated section that happens
to share the old number" by reading each hit's actual topic, not
find-and-replacing. Three references confirmed-by-reading to belong to the
OTHER sections were deliberately left untouched
(`docs/swift/backlog/FRONTEND-BACKLOG.md:144`, `docs/swift/design/FILESYSTEM.md:235`,
`docs/swift/rfc/PROMPT-CACHE-TOKEN-VISIBILITY-RFC.md:5`).

---

## Deferred — split to a follow-up issue, not this PR

Explicit scoping decision (developer, 2026-08-12): this branch does not loop
for days absorbing every review finding. The three items above were small,
contained, and directly touched files this PR already owns. Everything below
goes to a separate GitHub issue linked to #2125, tracked independently.

## Security / correctness — highest priority

### 1. CORRECTED 2026-08-12 (was overstated) — cosmetic garbling + one unconfirmed redaction gap, not a live URL leak
Original note claimed `document_summarize/capability.py` and
`document_read_common.py` "still leak raw URLs" because their `raw =
str(exc).strip()` looked unredacted. Traced one layer deeper: `exc` at that
point is a `DocumentPortCallError`, and `_wrap_document_port_error` (called
from **all five** adapters' `except httpx.HTTPError` blocks, not just
search's) already runs `_redact_urls()` on the message *before*
`DocumentPortCallError.__init__` stores it — confirmed
`DocumentPortCallError` does plain `super().__init__(message)`, so
`str(exc)` returns exactly that redacted string, nothing appended. The
URL-in-an-HTTP-error-message leak this whole mechanism targets is already
closed uniformly across all 5 document tools. Two real, much smaller items
remain:

- **Cosmetic only:** `document_access/capability.py`'s `structured` flag
  (`structured = timed_out or status_code is not None`, gated at line 203)
  suppresses the redacted-but-garbled leftover text (stray quote + dangling
  "For more information check:" fragment) when it already has a clean cause
  sentence. `document_summarize/capability.py` and `document_read_common.py`
  never got this suppression, so those two still show the garbled-but-already-
  redacted tail on a timeout/HTTP-status failure. No sensitive content in it.
- **Unconfirmed gap:** for tree/summarize/markdown/extraction, only
  `httpx.HTTPError` triggers `_wrap_document_port_error`/`_redact_urls` — a
  `json.JSONDecodeError` or `pydantic.ValidationError` from
  `r.json()`/`model_validate()` inside `kf_document_client.py` (lines
  185/227/260/292/316) would skip redaction entirely. Checked whether that
  actually leaks anything: neither exception type embeds the request URL by
  default, so this is a defense-in-depth inconsistency worth closing, not a
  demonstrated leak. (`DocumentSearchAdapter` catches broad `except
  Exception`, so it doesn't have this gap — see #4 below for the tradeoff
  that creates instead.)

**Revised severity: low.** Worth a small consistency fix (port
`document_access`'s `structured` suppression to the other two files; widen
the two non-search adapters' redaction net or confirm it's not needed), not
a blocker.

### 2. Shutdown `except Exception` deliberately doesn't catch `CancelledError` — nuance found post-merge
`agent_app.py:4699-4711`. Initial read: a `CancelledError` during
`container.shutdown()` aborts the `for` loop and skips
`aclose_token_refresh_client()` — the very step §2's commit message says must
survive an unrelated step failing. **But** the code already carries a comment
explicitly owning this: *"`except Exception` deliberately lets `CancelledError`
through — a shutdown being cancelled is not a step failing."* Confirmed this
comment predates the swift merge (present at `6231389e`, the PR-branch tip
before merge) — so it's the author's own documented tradeoff, not an
oversight I'm surfacing fresh.

Open question for the three of us: the comment's stated rationale ("a raising
`container.shutdown()` must not strand the Keycloak refresh pool behind it")
is about *exceptions* in one step not blocking the others — it does not
obviously extend to *cancellation*, which by construction skips everything
after it in the loop, including the very pool the PR added the step to
protect. Is that gap intentional (pod's dying anyway, moot) or a case the
author reasoned about `Exception` but not `CancelledError` for? Worth asking
directly rather than either of us guessing.

### 3. Agent-hook refresh path discards an empty/falsy result
`kf_base_client.py:174-183`. `await resolve_refresh_result(agent_hook(),
self._agent)` — return value never checked. Compare the `_refresh_cb` branch
9 lines below (`186-193`), which explicitly does
`if not new_token: logger.error(...); return False`. A custom
`KnowledgeFlowAgentContext.refresh_user_access_token()` (not
`@runtime_checkable`, so any shape) that resolves to `""` without raising
logs "succeeded," returns `True`, and the caller retries with the same stale
token → guaranteed second 401.

### 4. `DocumentSearchAdapter.search()` catches `Exception`, siblings catch `httpx.HTTPError`
`adapters.py:843` vs. the other four adapter classes (`DocumentTreeAdapter`
1027, `DocumentSummarizeAdapter` 1107, `DocumentMarkdownAdapter` 1186,
`DocumentExtractionAdapter` 1238) — need to diff their `except` clauses
directly, but the finding was: search's broad catch swallows
`pydantic.ValidationError` from `VectorSearchClient.search()`'s
`_HITS.validate_python(raw)` and reports it as generic `DocumentPortCallError`
instead of the real type, defeating the "name its type" guarantee the PR's own
test enforces elsewhere.

### 5. Duplicate `### 8.45` heading in `RUNTIME-EXECUTION-CONTRACT.md`
Confirmed three `### 8.45` headings now exist: line 2502 (this PR's Keycloak
section), 3050 (CACHE-01, unrelated, landed independently), 3096 (Alembic
#2290). This PR's own new heading collided with something that landed on
`swift` in the interim — **the merge did not flag or renumber it**, which is
itself worth noting: number collisions across concurrent doc-editing branches
apparently don't get caught by the merge itself, only by review.

---

## Frontend regression risk (HITL / optimistic UI)

### 6. HITL restore guard checks `exchange_id` only, not "is the last message already the cancellation for this call"
`useManagedChat.ts` `restoreIfStillWanted` (~line 594) vs. `useChatSse.ts`
`sendHitlResume`'s optimistic `cancelled_by_user` insert (~line 1081). Path:
resume's `fetch()` fails before `onAccepted` → `sendHitlResume` returns
`false` → caller restores the prompt → guard only compares `exchange_id`,
which the optimistic cancellation entry shares → prompt reappears next to a
trace row already showing "cancelled."

### 7. Same optimistic `cancelled_by_user` placeholder may never get corrected on a differently-answered retry
If restore (finding 6) happens and the user's *second* answer isn't "cancel,"
the stale placeholder is only superseded by a real `tool_result` carrying the
identical `tool_call_id` streaming back. If the runtime's resume doesn't
reissue that exact id (replan, etc.), persisted history keeps saying
"cancelled" for a call that actually ran.

---

## Design debt / maintainability (non-crash — lower priority for this pass)

- Redaction helper (`_redact_urls`/`_URL_IN_TEXT`, `adapters.py`) duplicates
  an existing `knowledge-flow-backend` helper (`_redact_signed_urls`) and
  isn't wired to the MCP tool-error path (`context_aware_tool.py`), so the
  same leak class persists there for MCP tools.
- `user_token_refresher.py`'s `refresh_user_access_token_from_keycloak`
  reimplements `fred_core.M2MTokenProvider.get_token()`'s shape (POST +
  coalesce + cache) instead of sharing it — and the new AUTH-TX RFC already
  plans a *third* near-identical copy.
- `KeycloakService.ts` ~line 482: two comment paragraphs argue for opposite
  return values (`null` vs. `0`) for non-numeric `timeSkew`; only the second
  matches shipped code. Stale rationale left behind after a reversal —
  footgun for whoever reads only the first paragraph later.
- Four byte-identical `refresh_user_access_token` shim classes
  (`_VectorSearchAgentShim`, `_McpRuntimeAgentShim`, `_WorkspaceAgentShim` in
  `adapters.py`, `_MediaClientAgentAdapter` in `agent_app.py:439`) each got
  the same `def`→`async def` edit applied separately rather than
  consolidated — `agent_app.py`'s own comment on the fourth already admits
  this shape "had already drifted" once before.
- `send()` and `sendHitlResume()` in `useChatSse.ts` duplicate the full
  preflight orchestration (token preflight → abort-check → prepareExecution →
  abort-check → wire-time re-verify → abort-check) as two hand-written
  copies. The PR's own §8.50/§8.51 history shows 3 correctness patches to
  this sequence in as many days, each needing to land on both copies.
- New AUTH-TX RFC commits the two-threshold frontend preflight as permanent
  defense-in-depth rather than scaffolding retired once a server-side fix
  ships.
- `preflightTurnToken()` is awaited to full completion before
  `flushPendingWrites`/`prepareExecution`, even though neither depends on its
  result — serializes a full Keycloak round trip onto the critical path
  instead of overlapping it with `dynamicBaseQuery.tsx`'s own coalescing.
- `tool_observability.py:361` hardcodes `exception_type = "none"` on the
  handled-artifact-failure branch, overloading a field whose name/other
  branch (`type(e).__name__`) implies it always names a real exception class
  — a Grafana query written against that assumption misclassifies the
  now-dominant handled-failure population.

---

## Next step
Items 0, 3, 5 above are fixed on this branch and verified (full suites
green). Remaining items — #1 (redaction consistency, low), #2 (shutdown
`CancelledError`, needs the author's intent directly), #4 (DocumentSearchAdapter
exception-catch shape), #6/#7 (HITL restore staleness), and the
maintainability list — filed as
[issue #2337](https://github.com/ThalesGroup/fred/issues/2337), linked to
#2125, to keep this PR shippable without turning into a multi-day loop.

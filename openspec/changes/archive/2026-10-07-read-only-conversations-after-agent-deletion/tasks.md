## 1. Session details and history routing

- [x] 1.1 Add `SessionDetails` to the existing session-detail route and service, with owner/team validation, authoritative `agent_deleted` and an ingress-safe `messages_url` resolved from the persisted runtime or legacy live-instance fallback. Verify backend unit/API cases for deletion, live/disabled/suspended agents, missing routing, other owners/teams and the backwards-compatible list/create/update projections.
- [x] 1.2 Regenerate Control Plane OpenAPI and the frontend client with `make update-control-plane-api` from `apps/frontend`. Verify the generated session-detail type includes the new fields, with no handwritten response mirror or internal runtime URL.

## 2. History loading and conversation availability

- [x] 2.1 Remove execution preparation from `useSessionHistory` and consume current session details. Add an explicit unavailable result while preserving cache, stale-session guards and active-turn protection. Verify `useSessionHistory.test.tsx` for deleted-agent reload, failed history reads, unresolved routing, delayed A/B responses and a newly bound first turn.
- [x] 2.2 Derive one saved-conversation execution state in managed chat, gate eager preparation for deleted agents and add session-detail query tags tied to the stored agent. Refresh after deletion and failed preparation without inferring deletion from network errors. Verify hook/query tests for same-client deletion, unresolved metadata and switching back to a live session.

## 3. Read-only interactions

- [x] 3.1 Add localized accessible deleted-agent status in chat/sidebar agent labels and gate composer submission, keyboard/commands, retries, new-conversation, voice/file paste/drop, context selectors and attachment additions/removals. Guard the corresponding hook callbacks. Verify focused page/hook tests assert no execution or optimistic message for a deleted instance, and preserve title management, downloads and conversation deletion.
- [x] 3.2 Render historical unanswered HITL and interrupted-execution content without executable actions; guard single/batch/skip HITL and continuation/restart callbacks. Verify `ConversationThread`, `toThreadMessages` and managed-chat regressions for readable trailing prompts and no resume after deletion.
- [x] 3.3 Cover opening a deleted-agent conversation through the existing sidebar URL and subsequent navigation to a live conversation. Verify focused `ChatList`/navigation tests retain the deleted-agent entry and live chat remains usable.

## 4. Verification and close-out

- [x] 4.1 After developer scope confirmation and implementation, verify the complete lifecycle with focused backend/frontend tests: send with a live agent, delete it, reload the original conversation, inspect history and read-only actions, and open a live conversation. Honor requested manual validation first; record exact evidence and unavailable environments in these tasks or the PR.
- [x] 4.2 Update the existing product-contract session section and component-UX chat section with the implemented boundary/behavior and a link to the lifecycle spec. Reconcile the PR's migration note with the final diff. Verify `openspec validate read-only-conversations-after-agent-deletion --strict` and `make migration-check MIGRATION_BASE=origin/swift`.
- [x] 4.3 Run root `make code-quality` once before the implementation commit/push, the affected offline suites and raw `basedpyright` for a touched package with a nonempty baseline. Apply `audit-branch` against the actual PR base, obtain an independent read-only review and run `fred-performance-reviewer` for affected per-request code. Verify all findings have dispositions and record reviewed base/head, coverage, checks and exclusions in the PR.
- [x] 4.4 Reconcile tasks and delta specs with the approved implementation and sync the final requirements to main specs. Verify implementation tasks, checks and required reviews are complete before archive and draft-PR close-out.

Initial implementation verification: 277 frontend tests passed across 17 affected files; 68 offline
backend tests passed, including all 14 session-detail cases. Raw backend
basedpyright reported 0 errors. OpenAPI regeneration, strict change validation,
migration declaration validation and whitespace checks passed. Lifecycle evidence
comes from hook/page/history/API regressions; no running-stack browser campaign
or load test was performed.

Author and independent read-only reviews covered the full change against the PR's
actual `swift` base (merge-base `044475267c9b84df7e8d142280a7cddf05de6324`),
planning HEAD `07c33ac5` and the implementation diff. Runtime admission rollback,
local-creation exemption expiry and the contradictory history contract were fixed
and re-reviewed. The separate execution-availability predicate is covered during
send/HITL preparation. No findings remain in the reviewed implementation.

Root `make code-quality` passed across every configured module after correcting
import order in the new backend test. No baseline suppressions were added.

## 5. Approved name and read-only presentation refinement

- [x] 5.1 Persist `agent_display_name` on session creation and snapshot the latest name atomically on scoped agent deletion, without changing conversation activity dates. Add one migration with live-agent backfill and verify upgrade/downgrade, team isolation, rollback, renamed agents and session projections.
- [x] 5.2 Regenerate OpenAPI and the frontend client. Preserve names in sidebar, grouped headers, conversation header and inactive previews; replace the suffix with strikethrough, an accessible status and hover/focus tooltip. Verify catalog failures are not inferred as deletion.
- [x] 5.3 Keep the composer visible and disabled with read-only placeholder and matching disabled surface/text tokens. Verify native disabled controls, preserved drafts, and live-chat behavior.
- [x] 5.4 Reconcile contracts, UX documentation and migration note; prepare the issue/PR update; run affected suites, migration and specification checks, root quality and full author review plus independent read-only review. Sync and archive the refined change for delivery on the same draft PR.
- [x] 5.5 Remove the separate deletion banner at the developer's request, retain the struck agent name, disabled composer and accessible descriptions, align existing specs and refresh the PR screenshots. Verify the page regression and the browser lifecycle again.

Refinement verification: 309 frontend tests passed across 21 affected files. The
final hook correction passed its 203-case suite; the other 34 UI and 72 consumer
cases remain valid from the earlier runs. The affected offline backend suite
passed 76 cases, and the focused session regression selection passed 56 cases
(partly overlapping). Raw Control Plane basedpyright reported 0 errors, 0 warnings
and 0 notes. Root `make code-quality` passed all configured modules after the
creation/availability fixes; the final context-barrier correction also passed
frontend TypeScript, Prettier and ESLint. No baseline suppressions were added.

The real Alembic chain was exercised in an isolated SQLite database through
upgrade to the parent, seeded upgrade, downgrade and re-upgrade. Matching live
names were backfilled without changing activity dates; deleted and foreign-team
names stayed null; downgrade retained sessions. There is one new revision and
one final head. Migration-note validation, OpenAPI regeneration and whitespace
checks passed. The change and managed-conversations main spec pass strict
validation. All 17 main specs pass normal validation; global strict validation
rejects an unrelated pre-existing Purpose placeholder in frontend-surface-scale,
confirmed in origin/swift and left outside this change.

Author and independent read-only review covered the full PR against actual
`swift`, merge-base `044475267c9b84df7e8d142280a7cddf05de6324`, committed HEAD
`85a8e7400bb59a210015135163eeaac9d5e68f42` plus the refinement working diff.
The independent reviewer reproduced three actionable P2 cases, all corrected:

- Creation could miss the latest name when deletion crossed insertion. Capture
  and insertion now share deletion's scoped instance lock and transaction;
  deletion winning returns 404 without an orphan row.
- A failed local creation retained its availability exemption after a successful
  detail read. Confirmation now ends that exemption and recovers a lost POST
  response without duplicate creation or unsafe saved-session revisits.
- A later creation retry could mask a failed context PATCH. Context failures stay
  session-scoped and blocking until a context write succeeds, independently of
  creation confirmation. The exact independent replay passes after correction.

Corrective re-reviews closed all three findings. Review also covered ownership,
history routing/cache, every execution entry point, generated consumers, name
fallbacks/group identity, accessible hover/focus status, disabled tokens, and
migration rollback/date preservation. Performance review found no new blocking
I/O, external calls, LLM/tool work, metrics or shared-pod state; the database lock
orders only creation/deletion of the same instance. No remaining findings in the
reviewed scope. Live browser validation, PostgreSQL concurrency and load/p99
campaigns were not run. PostgreSQL FOR UPDATE compilation and capture/insert
transaction identity were checked; SQLite does not establish live PostgreSQL
lock behavior. Already admitted turns remain outside scope.


Playwright follow-up (2026-10-07): 7 browser scenarios passed against code HEAD
`c66d907cdefa040d4610999d880686089f4a8a02`, using the full PR frontend, local
OIDC login and synthetic API fixtures. Verified the live draft, same-client
simulated deletion/invalidation, preserved history/draft, reload, computed name
strikethrough with an unchanged title, hover/keyboard status, dark grouped list
and restored live composer/send. No uncaught page errors, unexpected requests,
deleted-agent preparation requests or execution requests occurred. Four reviewed
captures are in `docs/swift/ux/screenshots/deleted-agent-read-only/` and embedded
in the PR. This closes the browser-rendering gap for these frontend scenarios;
production-backend deletion, database migration/concurrency and LLM execution
were not exercised by this browser campaign.

Banner-removal refinement (2026-10-07): the 27 ManagedChatPage cases and the same
7 Playwright browser scenarios passed after removing the redundant deletion
banner. The struck name, disabled composer, retained draft/history and accessible
hover/focus explanations remain intact. Light/dark captures were refreshed for
the PR; no page errors, unexpected requests, deleted-agent preparation or
execution requests occurred. Validation still uses local OIDC and synthetic API
fixtures, without backend deletion or LLM execution.
Root make code-quality passed across all 16 configured modules; the main lifecycle
spec passed strict validation. Author review of the presentation-only delta found
no remaining findings; execution guards, accessible descriptions and the separate
unavailable-history notice are retained.

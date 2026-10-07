## 1. Session details and history routing

- [x] 1.1 Add `SessionDetails` to the existing session-detail route and service, with owner/team validation, authoritative `agent_deleted` and an ingress-safe `messages_url` resolved from the persisted runtime or legacy live-instance fallback. Verify backend unit/API cases for deletion, live/disabled/suspended agents, missing routing, other owners/teams and the unchanged list/create/update shape.
- [x] 1.2 Regenerate Control Plane OpenAPI and the frontend client with `make update-control-plane-api` from `apps/frontend`. Verify the generated session-detail type includes the new fields, with no handwritten response mirror or internal runtime URL.

## 2. History loading and conversation availability

- [x] 2.1 Remove execution preparation from `useSessionHistory` and consume current session details. Add an explicit unavailable result while preserving cache, stale-session guards and active-turn protection. Verify `useSessionHistory.test.tsx` for deleted-agent reload, failed history reads, unresolved routing, delayed A/B responses and a newly bound first turn.
- [x] 2.2 Derive one saved-conversation execution state in managed chat, gate eager preparation for deleted agents and add session-detail query tags tied to the stored agent. Refresh after deletion and failed preparation without inferring deletion from network errors. Verify hook/query tests for same-client deletion, unresolved metadata and switching back to a live session.

## 3. Read-only interactions

- [x] 3.1 Add the localized deleted-agent notice and exact `(deleted)` suffix in chat/sidebar agent labels and gate composer submission, keyboard/commands, retries, new-conversation, voice/file paste/drop, context selectors and attachment additions/removals. Guard the corresponding hook callbacks. Verify focused page/hook tests assert no execution or optimistic message for a deleted instance, and preserve title management, downloads and conversation deletion.
- [x] 3.2 Render historical unanswered HITL and interrupted-execution content without executable actions; guard single/batch/skip HITL and continuation/restart callbacks. Verify `ConversationThread`, `toThreadMessages` and managed-chat regressions for readable trailing prompts and no resume after deletion.
- [x] 3.3 Cover opening a deleted-agent conversation through the existing sidebar URL and subsequent navigation to a live conversation. Verify focused `ChatList`/navigation tests retain the deleted-agent entry and live chat remains usable.

## 4. Verification and close-out

- [x] 4.1 After developer scope confirmation and implementation, verify the complete lifecycle with focused backend/frontend tests: send with a live agent, delete it, reload the original conversation, inspect history and read-only actions, and open a live conversation. Honor requested manual validation first; record exact evidence and unavailable environments in these tasks or the PR.
- [x] 4.2 Update the existing product-contract session section and component-UX chat section with the implemented boundary/behavior and a link to the lifecycle spec. Reconcile the PR's migration note with the final diff. Verify `openspec validate read-only-conversations-after-agent-deletion --strict` and `make migration-check MIGRATION_BASE=origin/swift`.
- [x] 4.3 Run root `make code-quality` once before the implementation commit/push, the affected offline suites and raw `basedpyright` for a touched package with a nonempty baseline. Apply `audit-branch` against the actual PR base, obtain an independent read-only review and run `fred-performance-reviewer` for affected per-request code. Verify all findings have dispositions and record reviewed base/head, coverage, checks and exclusions in the PR.
- [x] 4.4 Reconcile tasks and delta specs with the approved implementation and sync the final requirements to main specs. Verify implementation tasks, checks and required reviews are complete before archive and draft-PR close-out.

Verification: 277 frontend tests passed across 17 affected files; 68 offline
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

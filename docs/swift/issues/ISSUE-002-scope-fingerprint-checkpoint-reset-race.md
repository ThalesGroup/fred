# ISSUE-002 - Scope fingerprint checkpoint reset race under concurrent session requests

Status: open
Owner: TBD
Target window: Constellation (2.x) migration/hardening

## Problem
The scope-change reset logic performs a read-check-await-write sequence on an in-memory fingerprint map without per-session mutual exclusion. If two coroutines for the same session run concurrently, both can observe the old fingerprint and both can delete checkpoint state.

## Why it matters
- Low probability in current UI flows, but realistic with API clients, retries, or background workers.
- Can wipe active checkpoint state mid-conversation.
- Produces non-deterministic memory loss that is hard to reproduce.

## Current evidence
- `ignored/fred/agentic-backend/agentic_backend/core/chatbot/session_orchestrator.py`: `_scope_fingerprints` map declared as shared in-memory dict.
- `ignored/fred/agentic-backend/agentic_backend/core/chatbot/session_orchestrator.py`: sequence is `get()` -> compare -> `await adelete_checkpoint_thread(...)` -> write new fingerprint.
- The `await` in the middle opens a race window for same `session.id` when requests are concurrent.

## Scope
- Active paths:
  - Not currently on the primary Swift runtime path.
- Migration relevance:
  - Important if this scope-reset behavior is ported/reimplemented in Constellation 2.x runtime/pod architecture.
- Not in scope:
  - Frontend serialization behavior (it reduces probability but does not guarantee safety for all clients).

## Proposed fix
- Option A (preferred): maintain `dict[session_id, asyncio.Lock]` and guard the full read-check-delete-write sequence under that lock.
- Option B: move fingerprint state to an atomic persistence/update primitive (higher complexity, cross-process semantics).

## Acceptance checks
- [ ] Concurrent same-session requests cannot execute reset/delete in parallel.
- [ ] At most one checkpoint deletion occurs per effective scope transition.
- [ ] Scope unchanged path remains lock-safe and low overhead.
- [ ] Add stress test with concurrent requests on same `session_id`.

## Promotion
Promoted to: none
Notes: Legacy location today; promote when Constellation migration confirms equivalent scope-reset logic in active runtime.

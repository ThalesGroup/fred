## Context

See proposal.md. The router schedules session binding separately from ordinary mutation renders. Clearing a local creation marker on every mismatching render destroys ownership while the old draft route is still visible.

## Goals / Non-Goals

Preserve the first handoff without broadening an unresolved saved-session exemption. No automatic retry or backend authorization change.

## Decisions

Clear local creation ownership on committed session changes, not arbitrary renders. Retain the effective local session identity before route commit and gate post-write continuation on a revocable submission attempt. Navigation, explicit new-chat actions and unmount revoke that attempt; finally releases only its own lock. Retain the existing authoritative deletion/mismatch checks, write barrier, failed-create retry set and send reentrancy guard. A permanent exemption for every created session would weaken later navigation checks and is rejected.

## Risks / Trade-offs

A rapid navigation away must revoke ownership even before session details arrive; regression coverage includes leaving and returning, failed writes and late preparation. No new polling, I/O or timer.

## Migration Plan

Normal frontend deployment and rollback; no operator action.

## Context

See proposal.md and the linked approved tickets. The existing catalog is startup-owned; Deep uses physical native filesystem loading.

## Goals / Non-Goals

Implement only the approved ticket outcomes and preserve existing public consumers. No remote publication, content editor or new execution authority.

## Decisions

Use focused control-plane administrative API/store with the existing feature-management gate and shared HTTP pool, bounded concurrent catalog reads. Existing tables own unrelated semantics; a small per-skill policy table naturally owns these durable exceptions, with native atomic upserts. Resolve disabled names in the existing managed-binding pooled read session; never trust body-supplied restrictions. New runtimes send X-Fred-Skill-Policy:1; active restrictions reject legacy managed resolution, preventing old replicas behind a service from bypassing policy. Catalog status blocks unsupported/unavailable disable writes. Apply immutable per-turn views to ReAct and native Deep metadata/permissions. Do not erase history or interrupt active runs.

## Risks / Trade-offs

- Strict old validators: negotiate additive catalog fields and document ordered rollout.
- Concurrent users/replicas: immutable per-run eligibility, shared policy and bounded pooled I/O; no process-local correctness state.
- Previously loaded instructions cannot be forgotten: enforcement covers new loads, not erasure of history.

## Verification and migration

Use the approved public configuration, catalog/execution, admin and UI seams. Run focused checks during slices, root quality and offline suites near completion, then independent standards/spec and performance review. Record evidence in tasks.md. Deploy schema/control plane/runtimes/frontend together with supported negotiation; rollback removes administrative restrictions before old runtimes resume.

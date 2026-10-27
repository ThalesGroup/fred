## Context

See proposal.md and the linked approved tickets. The existing catalog is startup-owned; Deep uses physical native filesystem loading.

## Goals / Non-Goals

Implement only the approved ticket outcomes and preserve existing public consumers. No remote publication, content editor or new execution authority.

## Decisions

Use a single frontend presentation helper gated by trusted builtin provenance, with dictionaries for display only. Add builtin=false defaults to summaries and load attribution for old histories/custom catalogs. Keep slugs for selection/serialization and presentation separately for visible titles. Negotiate extended catalog metadata to avoid old strict validators rejecting new fields.

## Risks / Trade-offs

- Strict old validators: negotiate additive catalog fields and document ordered rollout.
- Concurrent users/replicas: immutable per-run eligibility, shared policy and bounded pooled I/O; no process-local correctness state.
- Previously loaded instructions cannot be forgotten: enforcement covers new loads, not erasure of history.

## Verification and migration

Use the approved public configuration, catalog/execution, admin and UI seams. Run focused checks during slices, root quality and offline suites near completion, then independent standards/spec and performance review. Record evidence in tasks.md. Deploy schema/control plane/runtimes/frontend together with supported negotiation; rollback removes administrative restrictions before old runtimes resume.


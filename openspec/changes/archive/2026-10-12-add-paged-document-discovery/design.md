## Context

See proposal.md for motivation. `/documents/tree` currently resolves all metadata in a capped authorized folder listing, builds a hierarchy, then prunes it to `max_chars`. The tree port captures identity privately in the runtime adapter. `fred-core` already stores arrival in `date_added_to_kb` and has SQL-backed single-folder browsing, but that browse filters document permissions after page selection and therefore cannot directly provide this new contract.

The metadata/UI changes in #3053 are merged. This independent branch includes the updated `swift` base; its diff extends that shipped metadata contract.

## Goals / Non-Goals

**Goals:** Bounded model output, useful filename discovery and latest-known-arrival selection, reliable continuation through an authorized scope.

**Non-Goals:** Content search, label-search changes, ingestion-completion timestamps, a new capability or endpoint, and snapshot-consistent traversal while documents or permissions change.

## Decisions

### Extend the current tool with opt-in HTTP pagination

Add `name_filter`, `sort_by` (`name` or `added_to_kb`), `sort_order` (`asc` or `desc`), `limit` (1-100) and `cursor`. The agent tool defaults to 25 unique documents ordered by name ascending and forwards that explicit limit. HTTP/SDK callers omitting `limit` retain the existing budgeted tree behavior; paged-only arguments without a limit are rejected rather than ignored. Blank filters mean no filter. Match a literal case-insensitive substring against filename OR title; escape SQL wildcard characters rather than exposing SQL/regex syntax.

Add optional `next_cursor` and `has_unknown_arrivals` result fields. The latter concerns all authorized matches when arrival sorting is requested, so an agent cannot claim complete chronology merely because page one contains a known date. Preserve `tree` and `truncated`; pagination alone does not mean character-budget truncation. Include page information in both model-facing carriers. The UI shows the current page and a discreet continuation status, without raw cursors or an alarming warning.

An offset would be simpler but repeatedly scans skipped rows and shifts after insertions. Use a versioned, stateless keyset cursor carrying the last emitted sort value/uid and a normalized query/scope fingerprint. Validate its size, version, field types and fingerprint; its size bound covers a renderable position with UTF-8/Base64 expansion, so accepted long names do not produce unusable continuations; never take team, identity or permissions from it. Recompute authorization on every call. A cursor is a position, not a credential or an authenticated snapshot.

### Select authorized matches in the store

Reuse authorized folder/path resolution, preserving service-agent handling, ownership, team selection, descendant scope and the existing library/document union. Resolve matching folder descriptors without materializing every folder's item list and without the legacy 10,000-folder cap limiting a paged chronology claim. Intersect with readable document authorization before the SQL filter/order/limit, not after selecting a page. A targeted document selection remains bounded by the session/capability adapter contract.

Add a scoped page query to the existing document-store interface and PostgreSQL implementation. Fetch at most the requested page plus lookahead and hydrate metadata/labels only for page candidates. Reuse existing SQL/session helpers and provide equivalent SQLite test behavior. Inspect the real SQL plan with representative data; add an index only if the measured access path needs it, in one migration if required. Do not call `get_all_metadata` or hydrate the full corpus to return one document.

### Sort by stored arrival with an explicit unknown bucket

Order known stored arrivals by full timestamp plus uid, with unknown arrivals last in either direction. Require stored source-date presence; the model's read-time default, file creation and modification are not substitutes. The existing generic folder sorter puts nulls first descending and uses the alias `created` for arrival, so do not reuse its behavior unchanged. Return whether unknown arrivals exist among all authorized matches. A descending limit-one request can identify the latest known arrival; unknown matches require a qualified answer. All-unknown matches cannot establish chronology.

### Advance only over emitted documents

Page size and continuation operate on unique document ids, even when the tree repeats a document under several authorized folders. Keep ancestors and existing folder appearances for emitted documents; tree presentation need not become a flat list or globally chronological row layout.

Build a renderable prefix of the selected document order within the existing character budget, rather than applying arbitrary whole-branch pruning and advancing past discarded candidates. Resume after the last distinct document actually emitted, before the first omitted candidate. If one complete compact document record (including available metadata) plus its required folder path cannot fit the budget, return an explicit budget error with retry guidance instead of an empty page that advances or loops. Run CPU-bound formatting outside the request event loop. A page reduced by the character budget retains `truncated=true` and a continuation.

## Risks / Trade-offs

- Name filtering or arrival sorting may still scan matching SQL rows - inspect actual plans; bounded hydration and bounded model output are mandatory, not a claim of constant database cost.
- Authorization resource sets can be large - use existing batched lookups and safe query chunking; never introduce per-document permission calls or permission filtering after pagination.
- Inserts, renames, date edits or permission changes during traversal can change later pages - use deterministic keyset ordering and document live traversal semantics; no cross-request snapshot is promised.
- Very long names, metadata or many folder memberships can exceed a page budget - budget-aware prefix rendering and a no-progress error prevent silent loss.

## Migration Plan

The branch includes the #3053 merge from `swift`. Deploy additive request/result fields end to end, regenerate Knowledge Flow clients, and test old requests and stored traces. No data backfill or re-ingestion is planned. Deploy compatible backend and runtime versions together for the new tool arguments; normal rollback restores legacy tree discovery. Record any measured index migration in the existing operator note workflow.

## Verification decisions

The prepared PostgreSQL plan over 10,000 synthetic documents used top-N heapsort (35 kB) and completed in approximately 10 ms locally, with only two metadata records hydrated for page-plus-lookahead. No index migration was justified by this measurement; this is not a concurrency or realistic authorization benchmark. Selected-folder expansion uses bounded ancestor membership checks off the event loop. Workers without delegation caller identity use already-authorized team-folder predicates, and selected libraries constrain rendered memberships except for explicit document union members. Known cursor/budget codes preserve static retry guidance without forwarding arbitrary backend detail.

## Context

See proposal.md for scope. Baseline: swift `90ba6ba9f`, including the search containment and KPI fixes from #3115. PostgreSQL `metadata.tag_ids` is already authoritative membership, with folder-specific queries and a GIN index. There is no storage migration to design.

`MetadataService` currently intersects known candidates with document ListObjects in `get_documents_by_uids`, `get_document_metadata_in_tag`, `get_document_uids_in_tags`, `get_documents_metadata_in_tags` and `browse_documents_in_tag`. Its existing `filter_readable_document_uids` uses individual checks but an unbounded gather. Search already calls that helper in batches of ten.

`TagService.delete_tag_for_user` obtains its subtree through the UI listing service, including global tag authorization enumeration and filtered document IDs. `_delete_one_tag` trusts a filtered item list before deleting the tag. `update_tag_for_user` also computes its membership delta from the filtered folder inventory.

The active `simplify-corpus-authorization` change concerns a different team/project model. It is not a reusable plan for this compatible repair. The discarded #2845 branch is not a code source for this change.

## Goals / Non-Goals

**Goals:** repair known-candidate authorization, preserve existing rights and multi-folder membership, and prevent deletion from treating omitted documents as absent.

**Non-goals:** changing global discovery/label APIs, making every ListObjects call complete, historical data repair, asynchronous deletion, schema changes, a global concurrency limiter, atomic ingestion-versus-deletion admission, or artifact-store retry orchestration. These remain explicit follow-ups under #2845, #2561, #2144 and #3121 as applicable.

## Decisions

### Reuse the bounded candidate checker

Bound the existing helper to ten concurrent document READ checks and deduplicate UIDs per call. Fetch SQL candidates first and preserve their order when filtering. Missing metadata stays absent; denied reads stay excluded; authority errors propagate rather than becoming empty lists. Do not create per-document tasks for an entire large folder at once, and do not introduce cross-request permission caching.

Use that helper in the five known-candidate methods above. The multiple-tag methods check each unique document once per call, even if it belongs to several selected folders. Preserve the existing disabled-ReBAC engine semantics and caller identity rather than adding a service-account bypass.

Paginated browsing checks only the returned SQL page, retaining existing sort/offset/limit and store-total semantics. It does not scan the whole folder to calculate a new authorized-only total. A page can still be shorter when permissions genuinely deny some rows; global document count must no longer cause that outcome.

### Separate deletion inventory from read filtering

For document folders, select the canonical subtree using stored owner, type and path boundaries, without the UI listing's authorization enumeration or pagination. Reuse the tag store; add a scoped query if necessary, without new tables. Require DELETE permission on the selected folders before mutation. Never widen to an identically named path under another owner.

Read canonical document IDs for that subtree through the existing metadata store and require READ on all candidates before mutation. A denial or failed check refuses the operation instead of silently omitting an item. Existing per-item mutation checks remain authoritative. Do not substitute folder permission for document permission.

Preserve sequential folder processing and the existing five-item removal batches, so documents attached to both a parent and a child are not updated concurrently. Remove descendants before their container. Recheck canonical membership before deleting each folder; refuse deletion if links remain or the check fails. The UI update path benefits from complete checked inventories but retains its existing request semantics.

This is not an atomic deletion protocol: a concurrent new writer after the last membership check is outside the guarantee. Do not hold SQL locks across OpenFGA or external storage calls to pretend otherwise. Artifact deletion failures currently swallowed by the purge service remain #2144 and must not be described as fixed here.

### Cost and verification boundaries

- Read helper: N logical document READ decisions for N unique SQL candidates, at most ten concurrent checks. A page of P documents checks at most P; irrelevant documents elsewhere add no document checks.
- Deletion: work follows folders and their memberships; preflight checks are additional to existing mutation-time checks. Record logical checks and actual OpenFGA RPCs separately in tests, including existing account/status guard overhead. Do not claim one RPC per operation or global load protection.
- No new permission writes or cross-request cache. Release SQL query sessions before network authorization. Preserve existing quota transactions and document-removal semantics.
- Keep #3115's current-metadata search filter, active-team selection, attachment isolation and post-authorization KPI behavior intact.

## Risks / Trade-offs

- More checks than one global ListObjects request: bound concurrency and measure against candidate count; this intentionally trades an incomplete answer for correct bounded authorization.
- A large actual folder remains expensive: no claim of constant-time deletion or readiness for arbitrary concurrency. A server-wide limit is #2561.
- Existing orphan repair requires ownership and retention decisions after the folder row is gone: do not auto-delete data or invent replacement folders.
- General tag/label discovery can still truncate outside the repaired deletion inventory: keep remaining #2845 scope visible rather than closing the issue wholesale.

## Migration Plan

Deploy the normal Knowledge Flow image after offline checks and the developer's live validation campaign. No database, FGA schema, chart or frontend migration is required. Document that incomplete/denied deletion now fails explicitly. Rollback restores the previous truncation defect; this change does not repair previously orphaned data.

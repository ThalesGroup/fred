## Context

See [proposal](proposal.md). `VectorSearchService.search` resolves readable libraries in the ownership context, then discards that envelope for document-only queries. Explicit IDs receive only a document READ check. Each policy converts index candidates directly into hits. `MetadataService` already has targeted store lookup through `get_metadata_by_uids`; its public `get_documents_by_uids` additionally enumerates all readable documents, so it is unsuitable for this hot path. Session search incorrectly copies corpus IDs into its filter.

## Goals / Non-Goals

**Goals:** contain the reproduced search disclosures using current canonical membership, shared policy handling and request-local authorization work.

**Non-goals:** replace OpenFGA, change multi-library ownership, synchronize all index metadata, introduce projects, or promise atomic revocation of an already running request. The broader issue remains open for unlink failure recovery and other document tool boundaries.

## Decisions

1. Keep the authorized context library set separate from the selected libraries. Resolve the former once with the existing tag service. Explicit document IDs must have current metadata membership in that envelope and pass the existing caller-specific read policy. The query remains the union of selected libraries and selected documents inside the envelope. Selecting only documents never enables an implicit whole-library branch. Preserve unscoped API behavior when no ownership context is supplied; do not invent a team for similarity search.

2. Index filters remain an early narrowing optimization. Add one shared candidate gate used by semantic, strict, hybrid and hybrid fallback before hit enrichment and content-bearing diagnostics. Fetch canonical metadata for distinct corpus UIDs in batches, reject missing rows and validate current membership against the relevant branch. Check current read authorization using the existing ReBAC facade, deduplicating UIDs within the request with bounded concurrency. Propagate authority failures instead of returning unchecked results. Do not call global document ListObjects, scan the corpus or make one check per chunk. Returned library references must derive from current authorized membership, not stale index tags.

3. Keep session candidates on their existing owner/session/scope predicate. They have no corpus membership requirement, and selected corpus IDs must not restrict them. Carry this distinction from the query branch rather than trusting a candidate's claim to be a session attachment. Preserve the existing source ceilings, attachment quota and merge/ranking behavior among eligible hits.

4. Reuse the existing metadata store and authorization methods through a small focused helper rather than creating a new permission framework. Let U be distinct explicit/candidate corpus UIDs and C returned candidate chunks across enabled branches. Added metadata work is proportional to U, not the user's corpus; document authorization is at most once per distinct UID per request, with a fixed concurrency limit. Existing library resolution cost remains unchanged. Measure counts with repeated chunks and increasing irrelevant corpus size; this is not a claim of constant latency or of the future project model's permission budget.

Updating vector tags alone was rejected: delayed or failed index updates would leave the disclosure open. Filtering only after final merge was rejected: unchecked content could already reach enrichment, diagnostics or reranking. Enumerating every readable document before search was rejected because its cost grows with the entire corpus.

## Risks / Trade-offs

- Candidate rejection can produce fewer than top_k results when stale hits occupy the retrieval pool. Keep retrieval bounded and test that valid candidates survive; do not introduce an unbounded refill loop or claim exhaustive recall.
- Metadata and OpenFGA are separate stores. Enforce current membership and authorization observed in this request, fail closed on missing metadata, and test stale tags even when a stale READ grant still exists. Repairing that grant and retry sequencing is outside this slice.
- Personal, unscoped and service-agent callers share this service. Add compatibility tests for their existing authorization rules; do not turn this fix into a general bypass or silently remove supported callers.
- The passing same-session attachment and new-library-document tests do not establish that a browser upload completed before Send. Keep that UI symptom explicitly unproven.

## Migration Plan

No schema change or reindex is required for search containment. Deploy the changed Knowledge Flow image into the existing k3d environment, then rerun the document access validation and record image revisions. Update the existing migration note with the effective restriction and residual issue scope. A rollback restores the vulnerable search behavior and must not be represented as a security fix. Archive this change only after implementation and acceptance; keep #3091 open for its remaining scenarios.

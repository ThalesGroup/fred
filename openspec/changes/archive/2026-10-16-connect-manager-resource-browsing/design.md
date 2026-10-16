## Context

See proposal.md. The root router currently mounts Home and provisioning only. The historical Resources page and scoped sidebar have Python dependencies. Manager already returns generated `Folder[]` and `Document[]` contracts; documents use `(name, id)` keyset pagination. Existing resource UI uses ResourceExplorer, Breadcrumb and TablePagination.

## Goals / Non-Goals

Complete read-only discovery of persisted metadata, including empty folders and cursor boundaries. Document names remain unique within each folder; homonyms in distinct folders remain isolated. No library-to-folder compatibility adapter, Python permissions, synthetic personal identifiers, data import, download or preview. An organization remains an implicit unique boundary; URLs identify only selected spaces.

## Decisions

- Rewire the existing scoped navigation and Resources page with manager memberships and generated list hooks. Retain the page shell, explorer, name cells, breadcrumb and pagination controls. The home space selection still opens its detail; Resources is the next explicit click. Organization home keeps the space list.
- Consume the generated DTOs directly. Navigation owns a folder breadcrumb and document cursor history, reset on scope/folder changes. Fetch 51 documents to render 50 and determine whether Next is available; do not count or fetch all documents. Reuse TablePagination with an unknown-total mode that omits total/last-page claims. Folders appear on the first document page, sorted by name and id, and remain reachable by First.
- Revalidate both list queries on entering a space/folder/page, use current arguments' data only, and hide rows while fetching or on any error. Cached successful data cannot override a fresh refusal. Key navigation state by space. Successful OIDC logout/account switching performs full-page navigation and creates a fresh Redux store.
- Keep server authorization unchanged: personal admission, unique organization resolution, then OpenFGA `can_read` on the requested space. Validate any supplied folder with space-scoped SQL after authorization; nonexistent and foreign folders return 404. No folder/document-specific grants or frontend role-to-permission matrix.
- Expose the two read handlers through the existing Temporal-independent router so real browser fixtures can exercise them. Production URLs and list shapes remain identical.

Authorization inventory: Python page currently combines team/quota and knowledge-flow tag/corpus calls, and its workspace mounts labels, import and mutation consumers. None are needed for metadata browsing. Manager permits local members and inherited editors/analysts to read content; admin and organization owner alone grant no content read. Personal content has no ancestor inheritance. Direct deep links still require server checks; no role is silently promoted.

Request budget: after common admission, each list calls existing unique-organization resolution (paged user-filtered direct `Read` and hierarchy `Read` requests), then one `Check(user, can_read, space)`; no ListObjects, BatchCheck or writes are introduced. Space/folder entry issues two list requests; document page changes revalidate folders and documents. Resource listing only reads SQL; no transaction/advisory locks span OpenFGA. Organization resolution overlaps independent placements with at most 32 in flight per call, preserving each project's parent-before-organization dependency and Q(u) RPC count. Existing mutation callers retain their locks while resolving context. Authorization cardinalities are the caller's direct memberships and bounded hierarchy depth, not document count. Folder responses scale with direct child folders; documents fetch at most 51 rows per UI page. Server-side Check evaluation can traverse inherited grants and is not equivalent to one unit of work. Focused tests must measure request counts on declared fixtures; no scalability claim follows from the demo.

## Risks / Trade-offs

- Existing document pagination has no snapshot: concurrent renames can move rows across pages. Keep the backend's documented ordering and refresh semantics; do not promise a snapshot.
- Folders remain an unpaginated existing endpoint; document pages are bounded. Record this distinct cardinality in arc42.
- Direct folder links are not introduced: breadcrumb state is local and refresh returns to the space root.
- Browser fixtures seed metadata in disposable SQL after provisioning; they must not suggest that importing the demo bundle imports documents.

## Migration Plan

No schema or grant migration. Regenerate OpenAPI and its client from route registrations, deploy UI and manager together, and revert this commit to roll back browsing.

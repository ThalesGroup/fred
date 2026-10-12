## Context

Knowledge Flow already performs an authorized batched metadata read. It projects document name and embedded creation date into a tree leaf; the renderer labels that calendar day `uploaded`. The runtime adapter preserves `{tree, truncated}`; the capability currently copies only `tree` into text content and Graph blocks. The frontend displays the tree in a CodeBlock and strips bracketed ids.

## Goals / Non-Goals

**Goals:** Expose the agreed metadata through existing contracts and keep the approved folder/document presentation compact.

**Non-Goals:** New ingestion-completion tracking, exhaustive latest-document queries, chronological sorting, changed scope semantics, or arbitrary operational metadata.

## Decisions

1. Project authorized documents into a small existing leaf representation. Include `uid`, `name`, `added_to_kb`, `created`, `modified`, and available `title`, `file_type`, `mime_type`, `language`, `page_count`, `row_count`, `labels`, `source`. Do not add extra reads per document. Run the CPU-bound tree serialization/pruning in a worker thread so richer metadata does not block other requests on the event loop.
2. Serialize each document leaf as a compact JSON object on one indented line. Folder lines are JSON records with `folder` and optional `folder_id`, distinct from document `uid`. Encoding both kinds keeps allowed folder newlines and punctuation on a single tree line. JSON escapes newlines and punctuation in document names and metadata, so the frontend parses fields rather than slicing increasingly complex prose. The existing tree string and API/SDK models stay unchanged.
3. Normalize known dates to UTC ISO 8601 and preserve precision. Check whether the source arrival field was supplied when deserialized: a legacy default generated at read time is not a stored arrival. Render missing dates as null. Creation is file metadata; modification may include Fred metadata mutations; arrival is not ingestion completion.
4. Keep whole-item pruning within `max_chars`. Prepend a short incomplete-listing notice in the capability when `truncated=True`, and send identical text through both carriers. This fixed notice is outside the backend tree budget.
5. Parse the allowlisted tool's current JSON leaves and legacy text leaves into a local trace view. Render user content as text; never show internal ids or raw malformed JSON. Reuse the generic tool status view for unsupported/error content.
6. Render folder groups with compact document rows. Show name, format and localized arrival date/time. On click, expose labeled metadata; optional missing descriptive fields are omitted, and missing dates are explicit. Allow one expanded document per tool result. Preserve folder membership for documents listed more than once.
7. Compute the latest known arrival only over displayed document records, comparing instants. Label it as the most recent displayed arrival; incomplete trees keep a visible warning. Count unique displayed documents rather than claiming total corpus size.
8. Preserve legacy results: parse existing uploaded-date leaves without reinterpreting them as authoritative Fred arrival dates. They retain their historical label in the UI.

## Risks / Trade-offs

- More metadata causes earlier pruning: concise JSON keys and whole-leaf budget tests protect bounds.
- Partial trees cannot establish a global latest document: both agent instructions and UI warn about this limit.
- Legacy arrival defaults can synthesize the current clock: detect omitted fields and retain unknown dates.
- Labels/title/source may be large or contain punctuation: JSON encoding and text-only UI rendering preserve structure; oversized complete leaves are omitted by the existing budget.

## Migration Plan

No operator action or schema migration is expected. Deploy the renderer, capability and frontend together; older text results remain readable. Record the changed tool result text and UI in one migration note. Rollback restores the previous components.

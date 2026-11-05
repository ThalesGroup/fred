## Context

See proposal.md. Native document access builds separate model JSON blocks and typed citation sources. All write/import calls share one save function; history already persists attributed copies of raw NUL-bearing arguments.

## Goals / Non-Goals

Goals: one reference key across native vector search, read and summary; successful NUL-bearing writes whose stored/editor content is clean and whose normalization is disclosed.

Non-goals: rename SDK/backend VectorSearchHit fields, tree records or citation objects; remove valid Unicode, literal marker text or the replacement character; change identity, authorization or history representation.

## Decisions

- Rename `uid` only when projecting native vector-search hits into model content. Both the returned text and JSON artifact use that projection; citation sources retain their typed identity. Do not expose a duplicate legacy key. Update adjacent reading/extraction/similarity guidance that refers to this search output.
- Count and remove only U+0000 in title/Markdown before title deduplication and storage. Store and editor receive the same cleaned values, including empty values when input contains only NUL. A successful result includes removal counts in non-error text blocks so both ReAct and Graph consumers receive the disclosure. Normal successful writes retain their existing result shape.
- Retain original invocation arguments in live execution/history handling. Historical copies keep the existing attributed `[U+0000]` representation; the saved document contains neither the original NUL nor an injected marker.
- Reuse existing tables, ports and pooled clients. Work is linear in the bounded result set or write size; normalization uses local string copies and adds no I/O, shared state, locks or multi-pod coordination.

## Risks / Trade-offs

- Clients parsing native tool JSON must use `document_uid`; document the deliberate model contract change and test text/JSON/Graph consumers. Backend APIs and UI citations keep their existing contracts.
- Removal changes source text; expose counts while preserving all valid characters. Verify create, update, title deduplication and imported Markdown with real PostgreSQL.
- Captured historical search results retain `uid`; updated guidance still describes exact opaque values and tree/attachment discovery. Do not rewrite old conversations.

## Migration Plan

Deploy updated native capabilities together. No database/configuration migration or document re-ingestion. Update consumers of native search tool JSON; rollback restores the earlier output key and NUL rejection policy. Keep the existing migration note authoritative.

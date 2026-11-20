## Context

See proposal.md and issue #3477. Native read and summary tool signatures expose document_uid as a plain string; their longer docstrings already prohibit filenames. Writable-document saving forwards title/content to its existing store. PostgresHistoryStore serializes typed message parts and metadata directly to JSONB, so rejecting a tool argument alone does not make its historical copy persistable.

## Goals / Non-Goals

Implement the developer-approved parameter guidance and strict NUL rejection without changing source documents, UID values, lookup rules, permissions, or automatic retry behavior. Renaming uid output fields and adding filename resolution are excluded. Authentication failures from API campaigns are excluded. Arbitrary JSON object keys and identity fields are not document content and are outside the text-normalization contract.

## Decisions

1. Add model-visible parameter descriptions through the existing LangChain schema mechanism and check the resulting provider tool schema. Reuse one document-UID description across read and summarize; describe search as returning the exact uid to reuse. Keep the existing uid/document_uid field names for compatibility. No guessed UUID regex or discovered-reference registry.
2. In save_writable_document, inspect title and content_markdown for U+0000 before acquiring or querying a store. Return a Fred-owned non-empty TEXT block with INVALID_DOCUMENT_CONTENT, affected field/count, and correction guidance. No successful editor part or mutation on rejection. Share this path with open_writable_document; do not silently strip text or modify user-edit HTTP schemas.
3. Normalize NUL in the serialized string values of history parts and metadata to the visible marker [U+0000]. Record the replacement count and marker in the existing metadata JSON extra fields. Work on the persistence copy only; preserve original arguments, valid text, ranks, call IDs and failure status. This is diagnostic representation, not reversible encoding or model-state rewriting. No schema migration or new table is necessary.
4. Reuse the configured SQL sessions and upsert semantics. Validation and normalization are linear in the already serialized payload, require no additional I/O or coordination, and introduce no process-local state. Compare focused serialization timings to ensure the normal path stays inexpensive under concurrent turns.

## Risks / Trade-offs

- Parameter hints cannot restore an absent UID: inspect available captured contexts and report real-model outcomes separately from deterministic schema and port checks.
- Diagnostic history differs from invalid input: attribute every replacement and leave live execution untouched; test nested values, existing marker text and normal Unicode.
- SQLite accepts NUL and cannot demonstrate PostgreSQL behavior: use a disposable PostgreSQL schema for the failed-turn write/read proof when available.
- The historical absence of a whole session is observed, not a fully reproduced transaction: establish the current JSONB boundary with actual PostgreSQL rather than claiming historical causality.

## Migration Plan

Deploy the ordinary updated Python packages. No operator configuration, data rewrite, new dependency or database migration. Rollback restores old handling; already normalized history remains readable by previous readers through existing metadata extras.

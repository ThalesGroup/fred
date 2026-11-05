---
schema: 1
title: "Improve document reference guidance and preserve rejected NUL writes"
impact: none
configuration: none
configuration_reason: "Only native tool descriptions, writable-text validation and history serialization change; no configuration keys or defaults change."
no_action_reason: "Existing APIs, UID values, database tables and stored history remain compatible; normal deployment activates the correction."
---

## Applicability

Fred deployments using native document reading, summarization or writable documents.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. No database migration, re-ingestion or stored-history rewrite is required.

## Validation

Inspect the read and summary tool schemas for exact-UID parameter guidance. A writable-document call containing U+0000 must return INVALID_DOCUMENT_CONTENT without changing the document. Reload its conversation: the failed call/result must remain paired and invalid historical text must have visible notation with a replacement count.

## Rollback

Use the normal rollback procedure. Existing readers accept the additional history metadata through their existing extra-field compatibility.

## Limitations

The parameter guidance is not a guarantee of model behavior. Source documents, UID values, permissions, automatic retry policy and authentication are unchanged. NUL notation in history is an attributed diagnostic representation rather than the original character. JSON object keys and identity fields are outside this text-value normalization contract.

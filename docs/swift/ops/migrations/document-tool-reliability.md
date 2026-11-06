---
schema: 1
title: "Standardize document references and remove NUL before document saves"
impact: minor
configuration: none
configuration_reason: "Only native tool output/guidance, writable-text normalization and history serialization change; no configuration keys or defaults change."
---

## Applicability

Fred deployments using native document reading, summarization or writable documents.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the updated document capabilities together. Native search tool JSON now uses `hits[].document_uid` instead of `hits[].uid`; update custom consumers that parse that tool result. Backend search APIs and typed citation sources retain `uid`. No database migration, re-ingestion or stored-history rewrite is required.

## Validation

Inspect native search text and structured blocks for `document_uid`, with no duplicate `uid` key; copy that value into read/summary. A writable-document call containing U+0000 must succeed with NUL removed from stored/editor title and Markdown, and disclose removal counts. Reload its conversation: the successful call/result must remain paired and original NUL-bearing arguments must have attributed history notation.

## Rollback

Use the normal rollback procedure and revert custom tool-result consumers to `hits[].uid`. The earlier branch policy rejects NUL instead of removing it. Existing readers accept history metadata through their existing extra-field compatibility.

## Limitations

The parameter guidance is not a guarantee of model behavior. Existing corpus documents, UID values, permissions, retry policy and authentication are unchanged. Removal applies only to actual U+0000 in writable title/Markdown; literal marker text and valid Unicode remain intact. History notation is an attributed diagnostic representation rather than the original character. JSON object keys and identity fields are outside this text-value normalization contract.

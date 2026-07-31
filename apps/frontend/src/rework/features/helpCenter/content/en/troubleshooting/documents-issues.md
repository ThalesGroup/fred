---
title: Document issues
order: 30
description: Failed ingestion, document never cited, unsupported format.
icon: folder
---

# Document issues

## Ingestion fails or stays stuck

After upload, a document goes through the statuses **Pending** → **Processing**
→ **Ready**. If it stays stuck or shows **Error**:

- **Wait**: ingesting a large document takes time.
- **Check the format**: a corrupted or unsupported file fails (see
  [Slowness and limits](/help/en/troubleshooting/limits)).
- **Re-upload** the document if the error persists.

## A document is never cited

- **Status**: only **Ready** documents are usable. Make sure it didn't stay in
  processing.
- **Location**: a file outside a library, at the top level, is **not indexed**.
  Place it in a team-corpus library.
- **Exclusion**: check it isn't marked **Excluded from search**.
- **Agent attachment**: make sure the library is attached to the agent you're
  querying (see [Agents](/help/en/features/agents)).

## The format isn't supported

Common formats are supported (PDF, text, PPT, Excel/CSV, Markdown). An exotic
format may be rejected: convert the document to a common format before
uploading.

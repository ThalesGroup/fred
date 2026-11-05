## Why

The developer explicitly selected the remaining naming proposal and automatic NUL removal on 2026-11-05, superseding the earlier preserve-names/reject-NUL policy in #3477. Native search references should be directly reusable and a storage-incompatible NUL should not force a failed tool call and model retry.

## What Changes

- **BREAKING**: native vector-search model content exposes `document_uid` instead of `uid`, matching read/summary arguments. Update relevant guidance and verify text/JSON artifact consumers.
- Automatically remove U+0000 from writable titles and Markdown before deduplication/storage, then save successfully and disclose removal counts in the tool result.
- Preserve valid text, source/citation objects and authorization. Retain attributed history representation of raw NUL-bearing arguments.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `document-tool-reliability`: standardize native search reference naming and replace NUL rejection with automatic write normalization.

## Impact

Document-access model projection, reading/summary and adjacent document-tool guidance, writable-document save/import, focused tests and existing migration/runtime documentation. SDK/backend search-hit fields, database schemas, permissions and shared client pools are unaffected. Reuse issue #3477 and its existing branch; no PR, as requested.

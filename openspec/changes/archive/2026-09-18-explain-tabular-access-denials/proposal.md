# Proposal

## Why

Agents pass filenames or SQL aliases where tabular tools expect document UIDs, then mistake an opaque denial for an identity problem. Extract the approved fix from POC commit `3f2d58d78` for [issue #2743](https://github.com/ThalesGroup/fred/issues/2743).

## What Changes

- Share recovery guidance across tabular dataset denial paths, naming `list_tabular_documents` and explaining valid UIDs.
- Preserve permission decisions, status codes, attachment ownership behavior, and upstream tests.

## Capabilities

### New Capabilities

- `tabular-access-errors`: actionable, non-disclosing access-denial guidance.

### Modified Capabilities

None.

## Impact

Knowledge Flow tabular service and service/controller regression tests. Error text changes only; no request/response schema or generated-client changes. The extraction scope was approved in the handoff; no architecture or storage work is included.

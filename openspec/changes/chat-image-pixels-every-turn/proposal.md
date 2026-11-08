Stacked on `chat-image-descriptions` (PR A): rebase onto `swift` after A merges.

## Why

Tracking: #3496, related to #2802 (its chat slice, deterministic: no model decision).

A vision model saw a chat image only on the turn it was attached, from browser pixels; later turns answered from the Knowledge Flow description, which can be wrong.

## What Changes

- **Kept preview:** at fast ingest, Knowledge Flow stores a bounded preview of each chat image (long edge at most 1568 px; JPEG for an opaque photo, PNG otherwise), never the original. Only its uploader reads it, from its conversation; the fast delete, hence session erasure, removes it.
- **Pixels on every call:** each model call of a ReAct turn with a vision model carries the 5 newest images of the conversation, fetched once per turn, never checkpointed.
- **No competing description:** an image sent as pixels loses its vision description (SVG facts stay). Older images, non-vision models, Deep agents and failed fetches keep it.
- The browser no longer sends pixels; the image prompt rules follow.

## Capabilities

### Modified Capabilities

- `chat-image-attachments`: images seen on every turn; preview kept for the uploader.

## Impact

- `apps/knowledge-flow-backend`: `GET /knowledge-flow/v1/fast/preview/{document_uid}?session_id=`; content-store objects `chat-attachment-previews/{document_uid}`.
- `libs/fred-runtime`: vision attachments middleware; two reads per turn (control-plane session attachments, Knowledge Flow previews).
- `apps/frontend`: image data URLs removed; Knowledge Flow client regenerated.
- Token cost: up to 5 images on every vision call (about 475 prompt tokens for a 681x451 chart).

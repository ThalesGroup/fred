# Multimodal image read tool RFC

**Status:** Proposed  
**Task ID:** RUNTIME-08  
**Owner:** Simon  
**Created:** 2026-06-29

## Problem

Chat attachments can include images. The first Swift attachment implementation
placed inline image `data:` URLs in `RuntimeContext.attachments_markdown` so the
model could see the image directly. That is unsafe for production use:

- base64 image data can explode the text prompt context;
- image data in a system prompt is not the right multimodal transport;
- conversation attachments are scoped to the current conversation and user access;
- images can also come from the global document corpus, not only from chat
  attachments.

The model needs a way to inspect the full image when it is relevant, without
turning binary data into prompt text and without bypassing ReBAC/session scoping.

## Proposed solution

Add a built-in Fred runtime tool named `attachments.read_image`.

The tool exposes a single logical contract to the model while keeping the source
explicit:

```json
{
  "source": "conversation_attachment",
  "attachment_id": "attachment-123"
}
```

or:

```json
{
  "source": "document_media",
  "document_uid": "doc-123",
  "file_name": "page-1-image-2.png"
}
```

The model never receives raw storage paths or reusable presigned URLs. The tool
resolver performs the lookup and authorization checks, fetches the image from the
configured backend, and returns an image-capable payload to the runtime model call.

### Source semantics

`conversation_attachment`

- scoped by `RuntimeContext.session_id`;
- must match an attachment that belongs to the current conversation;
- must use the current user/team authorization context;
- intended for images uploaded as chat attachments.

`document_media`

- scoped by document/corpus permissions;
- must use the same ReBAC and selection model as document reads/searches;
- intended for images stored as part of an ingested document, including images
  from the global corpus.

### Runtime behavior

1. The frontend/runtime prompt only announces image metadata:
   name, mime type, size, and the stable reference needed by the tool.
2. The model calls `attachments.read_image` when it needs visual inspection.
3. The runtime validates the requested source:
   - conversation attachment requests require the current `session_id`;
   - document media requests require access to the requested document/media item.
4. The runtime fetches the image:
   - local development may use filesystem-backed storage;
   - production may use S3/MinIO/GCS-backed storage or Knowledge Flow media APIs.
5. The runtime passes the image to a vision-capable model as multimodal content.
6. If the selected model/provider cannot accept image content, the tool returns a
   clear capability error instead of silently falling back to lossy text.

### Prompt behavior

The attachment prompt suffix should state:

- conversation attachments are scoped to the current conversation;
- documents/images are limited to the current user's authorized access;
- images are available through `attachments.read_image` when that tool is listed;
- the model must not use document search as a substitute for direct image
  inspection when the user asks about image pixels/layout.

## Contract impact

### `fred-sdk`

- Add `TOOL_REF_ATTACHMENTS_READ_IMAGE = "attachments.read_image"`.
- Add typed args for the two source modes.
- Register the tool in the built-in tool catalog.

### `fred-runtime`

- Resolve the new built-in tool through the existing runtime tool resolver.
- Add a tool invoker implementation that fetches image bytes only after source
  validation.
- Keep raw image bytes out of checkpointed prompt text and system prompt strings.
- Preserve existing `knowledge.search` behavior for text retrieval.

### Frontend

- For image attachments, send metadata and a stable attachment reference, not
  base64 prompt text.
- Continue using document search controls for textual/document retrieval.
- Do not expose presigned URLs in user-visible or model-visible text.

### Knowledge Flow / storage

The first implementation may reuse existing media fetch paths for document media
and existing attachment metadata/storage keys for session attachments. If direct
blob access is needed, add the minimal backend method behind existing
authorization boundaries rather than exposing storage internals to the frontend
or model.

## Alternatives considered

### Keep base64 in the prompt

Rejected. It already caused prompt-size failures and is the wrong transport for
multimodal model input.

### Generate a vision-model description during upload

Rejected as the primary path. Descriptions are useful as a fallback/indexing aid,
but they are not equivalent to giving the model access to the image pixels. They
can miss UI details, diagrams, handwriting, small labels, or spatial relationships.

### Give the model a presigned URL directly

Rejected for the model-facing contract. Presigned URLs are storage credentials and
can be copied into answers or logs. If a backend uses presigned URLs internally,
they remain runtime-only implementation details.

### Reuse `knowledge.search`

Rejected for direct image inspection. Search remains the correct tool for text
snippets and extracted/embedded document content. Pixel/layout analysis needs a
multimodal image path.

## Security and ReBAC requirements

- The tool must never widen access beyond the current execution grant and token.
- Conversation attachments must be verified against `session_id`.
- Document media must be verified through document/corpus access checks.
- Tool output must not include raw storage keys, internal paths, or presigned URLs.
- Logs/traces may include source kind and stable IDs, but not binary payloads or
  signed URLs.

## Implementation plan

1. Stabilize the metadata-only prompt path:
   - keep base64 stripped from `attachments_markdown`;
   - include stable image references when available.
2. Add the SDK built-in tool constant and args schema.
3. Add the runtime tool invoker with mocked/offline tests for:
   - conversation attachment access;
   - document media access;
   - unsupported model/provider capability;
   - authorization/session mismatch.
4. Wire frontend attachment metadata to pass the stable image reference.
5. Validate with one local image attachment and one corpus document image.

## Open questions

1. Should the first runtime return image bytes as a `ToolInvocationResult`
   artifact, or should it re-enter the model call with a provider-native
   multimodal message block?
2. Which Knowledge Flow API is the canonical source for conversation attachment
   image bytes: session attachment storage key lookup or an explicit attachment
   media endpoint?
3. For corpus images, should the public model-facing reference be
   `(document_uid, file_name)` or a dedicated `media_id` if Knowledge Flow already
   has one?

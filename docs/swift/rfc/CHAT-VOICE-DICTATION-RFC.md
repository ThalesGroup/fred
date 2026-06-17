# RFC: Voice Dictation Into Managed Chat Composer (CHAT-11)

**Status:** Implemented (2026-06-17)  
**Author:** Codex  
**Date:** 2026-06-17  
**ID:** CHAT-11  
**Backlog:** `docs/swift/backlog/CHAT-UI-BACKLOG.md §12`  
**Contract impact:** additive Knowledge Flow OpenAPI endpoint only

---

## 1. Problem

The managed chat composer currently accepts typed text and file attachments only.
For quick notes, short prompts, and hands-busy usage, users need a simple way to
dictate a message into the existing text box without changing the runtime
protocol or introducing a full voice-assistant mode.

The repository already contains most of the required pieces:

- `RichInputField` is a reusable controlled composer component
- `useManagedChat` already owns `input`, `setInput`, and `handleSend`
- `knowledge-flow-backend` already ships a local `faster-whisper`-based
  `AudioProcessor`
- the frontend already uses the Knowledge Flow API surface via generated RTK
  Query hooks and existing auth/base-url conventions

What is missing is a narrow, non-streaming transcription path that:

- records one short clip in the browser
- sends it to Knowledge Flow
- returns plain text
- appends that text to the existing composer content without auto-sending

---

## 2. Scope And Constraints

This RFC intentionally keeps the first slice tight.

### In scope

- one authenticated Knowledge Flow transcription endpoint
- browser microphone capture with `getUserMedia` + `MediaRecorder`
- `RichInputField` opt-in mic control and UI states
- transcript insertion into the current managed chat input
- English and French labels
- offline backend tests with a fake transcription service
- frontend type/tests where feasible

### Out of scope

- realtime / partial transcription
- WebRTC or duplex voice assistant behavior
- automatic message sending after transcription
- audio persistence beyond temporary server-side files
- browser `SpeechRecognition`
- OpenAI audio APIs
- runtime / SSE contract changes

---

## 3. Proposed Solution

### 3.1 Backend: dedicated Knowledge Flow transcription surface

Add:

- `POST /knowledge-flow/v1/audio/transcriptions`

Request:

- `multipart/form-data`
- `file`: uploaded audio blob
- optional `language`: language hint, nullable

Response:

```json
{
  "text": "transcribed text"
}
```

Implementation shape:

- new small Knowledge Flow controller under `features/audio/`
- new helper/service that:
  - validates filename / extension / MIME hint
  - rejects empty uploads
  - writes the payload to a temporary file
  - calls the existing local Whisper capability
  - returns plain text
  - deletes temporary files in `finally`
- use existing Knowledge Flow user auth dependency and file-read authorization
  pattern

The service reuses the existing `AudioProcessor` model-loading path instead of
the ingestion pipeline. We explicitly do **not** create a document, schedule a
workflow, or persist markdown output for this MVP.

### 3.2 Validation policy

Use the current audio/video extension set already supported by `AudioProcessor`.
For MVP the endpoint also enforces a small fixed upload cap to prevent accidental
large recordings from hitting Whisper synchronously. The limit is intentionally
local to this endpoint and does not alter broader ingestion quotas.

### 3.3 Frontend: opt-in dictation in `RichInputField`

`RichInputField` gains optional props:

- `enableVoiceInput?: boolean`
- `onTranscribeAudio?: (file: File) => Promise<string>`
- `voiceInputDisabled?: boolean`

Behavior:

- first click: request mic access and start recording
- second click: stop recording, convert the blob to a `File`, call
  `onTranscribeAudio`
- on success: append the returned text into the controlled composer value
- never auto-send

State model:

- `idle`
- `recording`
- `transcribing`

If the browser lacks `MediaRecorder` / `getUserMedia`, the control stays
disabled and the page surfaces a normal toast error when the user attempts the
action.

### 3.4 Managed chat wiring

`ManagedChatPage` passes the opt-in props to `RichInputField`.

`useManagedChat` exposes one small helper to append dictation text into the
existing controlled `input` state. The helper is responsible for clean spacing:

- empty input -> transcript only
- existing input ending with whitespace -> direct append
- otherwise -> prepend one space before the transcript

### 3.5 Frontend API path

Preferred path: regenerate the Knowledge Flow RTK Query client from the backend
OpenAPI spec and use the generated mutation hook. This keeps the new endpoint on
the standard authenticated fetch/base-url path and avoids one-off `fetch`
helpers.

---

## 4. Alternatives Considered

| Alternative | Reason rejected |
| --- | --- |
| Browser `SpeechRecognition` | Inconsistent browser support and explicitly out of scope |
| Reusing the full ingestion/document pipeline | Too heavy for a synchronous chat-composer action; adds persistence and scheduler concerns |
| OpenAI audio transcription API | Explicitly forbidden for this feature |
| Frontend-only local WASM transcription | Much larger download/runtime cost than reusing the existing backend model |
| New runtime endpoint | Wrong boundary; transcription belongs to Knowledge Flow, not chat execution |

---

## 5. Contract Impact

Frozen contracts in `RUNTIME-EXECUTION-CONTRACT.md` and
`CONTROL-PLANE-PRODUCT-CONTRACT.md` do not change.

Additive contract change:

- Knowledge Flow OpenAPI adds `POST /knowledge-flow/v1/audio/transcriptions`

Frontend impact:

- regenerate `apps/frontend/src/slices/knowledgeFlow/knowledgeFlowOpenApi.ts`

---

## 6. File Map

Expected implementation areas:

- `apps/knowledge-flow-backend/knowledge_flow_backend/features/audio/`
- `apps/knowledge-flow-backend/tests/features/`
- `apps/frontend/src/rework/components/shared/molecules/RichInputField/`
- `apps/frontend/src/rework/components/pages/ManagedChatPage/`
- `apps/frontend/src/locales/en/translation.json`
- `apps/frontend/src/locales/fr/translation.json`
- generated Knowledge Flow OpenAPI client

---

## 7. Execution Note

The repository workflow normally requires a GitHub issue between confirmation
and implementation. For this local Codex session, the developer explicitly asked
to create the tracking docs and proceed immediately, so the GitHub-issue step is
treated as waived for this change.

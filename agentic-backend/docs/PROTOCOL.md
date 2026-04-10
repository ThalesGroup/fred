# Chat WebSocket Protocol (Current)

This document describes the current WebSocket protocol used by Fred chat.

The old `question/answer/interaction` payload shape is obsolete.
The current transport is message-oriented and aligned with `ChatMessage`.

## 1. Client → Backend

The client sends one of two message types.

### 1.1 Ask

```json
{
  "type": "ask",
  "session_id": "session-123",
  "agent_id": "Basic ReAct V2",
  "message": "Peux-tu m'aider ?",
  "runtime_context": {}
}
```

Notes:

- `agent_id` or `internal_profile_id` must be present
- `runtime_context` is optional transport input, not a persisted protocol contract
- `internal_profile_id` is used for internal capabilities such as `log_genius`

### 1.2 Human Resume

```json
{
  "type": "human_resume",
  "session_id": "session-123",
  "exchange_id": "exchange-123",
  "agent_id": "Tracking Graph Demo V2",
  "payload": {
    "choice_id": "reroute:PP-75015-1"
  }
}
```

This is used when a workflow or tool approval pauses on HITL.

## 2. Backend → Client

The backend emits typed events.

### 2.1 `session`

```json
{
  "type": "session",
  "session": {
    "id": "session-123",
    "title": "Lister mes fichiers",
    "agent_id": "Basic ReAct V2",
    "updated_at": "2026-02-28T09:36:35Z",
    "next_rank": 0
  }
}
```

### 2.2 `stream`

```json
{
  "type": "stream",
  "message": {
    "session_id": "session-123",
    "exchange_id": "exchange-123",
    "rank": 1,
    "role": "assistant",
    "channel": "tool_call",
    "parts": [
      {
        "type": "tool_call",
        "call_id": "call_1",
        "name": "list_files",
        "args": {
          "prefix": ""
        }
      }
    ],
    "metadata": {
      "agent_id": "Basic ReAct V2",
      "sources": [],
      "extras": {}
    }
  }
}
```

`stream.message` is always a `ChatMessage`.

Important channels:

- `final`
- `tool_call`
- `tool_result`

Important roles:

- `user`
- `assistant`
- `tool`

Partial assistant streaming uses:

- `channel = "final"`
- `metadata.extras.streaming_delta = true`

Each partial frame carries only the **new text fragment** since the previous frame (delta protocol).
The frontend accumulates deltas into the displayed message; it must not replace the full text on each frame.

The final non-partial frame (no `streaming_delta` flag) carries the complete authoritative text and
serves as a consistency checkpoint — the frontend replaces the accumulated buffer with this value.

### 2.3 `awaiting_human`

```json
{
  "type": "awaiting_human",
  "session_id": "session-123",
  "exchange_id": "exchange-123",
  "payload": {
    "stage": "tracking_resolution",
    "title": "Choisir une action",
    "question": "Veux-tu rerouter ce colis ?",
    "choices": [
      {
        "id": "reroute:PP-75015-1",
        "label": "PP-75015-1 - Paris Beaugrenelle",
        "default": true
      },
      {
        "id": "cancel",
        "label": "Ne rien faire"
      }
    ]
  }
}
```

This event is emitted when the runtime pauses for HITL.

The payload is not limited to multiple-choice decisions.
It may also represent a free-text clarification, for example:

```json
{
  "type": "awaiting_human",
  "session_id": "session-123",
  "exchange_id": "exchange-123",
  "payload": {
    "stage": "bid_intake_clarification",
    "title": "Preciser les informations manquantes",
    "question": "Merci de repondre en texte libre avec les informations que vous connaissez.",
    "free_text": true,
    "checkpoint_id": "ckpt-123"
  }
}
```

### 2.4 `final`

```json
{
  "type": "final",
  "session": {
    "id": "session-123",
    "title": "Lister mes fichiers",
    "updated_at": "2026-02-28T09:36:41Z",
    "next_rank": 4
  },
  "messages": [
    {
      "session_id": "session-123",
      "exchange_id": "exchange-123",
      "rank": 0,
      "role": "user",
      "channel": "final",
      "parts": [{ "type": "text", "text": "peux tu me lister mes fichiers ?" }],
      "metadata": {}
    }
  ]
}
```

This is the persisted snapshot of the whole exchange, not just the last assistant message.

### 2.5 `error`

```json
{
  "type": "error",
  "session_id": "session-123",
  "content": "Something went wrong while handling your message."
}
```

## 3. Message Model

The stable rendering unit is `ChatMessage`.

Important invariants:

- `rank` strictly increases inside one session
- one exchange has one final assistant answer
- tool calls and tool results are explicit messages, not buried in free text

Parts may include:

- `text`
- `tool_call`
- `tool_result`
- `link`
- `geo`
- other structured UI parts

## 4. Debugging

The admin debug drawer should be read as a transport transcript:

- `session`
- grouped `stream` messages by `exchange_id`
- final snapshot

It is intentionally sanitized:

- no raw access token
- no refresh token
- no broad user identity dump

## 5. Why This Matters For v2

This protocol already fits the v2 direction:

- ReAct runtimes emit tool calls and structured final messages
- Graph runtimes emit the same transport shapes
- HITL is explicit
- structured UI parts such as `GeoPart` and `LinkPart` travel without ad hoc parsing

# 💬 WebSocket Interface: Frontend ↔ Backend for Chatbot

This document describes the WebSocket message protocol used between the frontend (React) and the backend (FastAPI) for chatbot interaction.

---

## 📤 From Frontend → Backend

### Format

The frontend sends a chat message request in the following format:

```json
{
  "session_id": "abc-123" | null,
  "user_id": "user@example.com",
  "message": "Hello, who is Shakespeare?",
  "agent_name": "Georges"
}
```

This maps to the `ChatAskInput` schema in the backend.

---

## 📥 From Backend → Frontend

The backend responds through WebSocket messages using a **typed protocol** with a `"type"` field to help the frontend handle each message appropriately.

---

### ✅ 1. Streamed AI response chunks

These are intermediary partial messages sent while the agent is generating the response.

```json
{
  "type": "stream",
  "content": "partial text",
  "session_id": "abc-123"
}
```

- Sent progressively
- Useful for real-time UI updates (e.g. typing effect)

---

### ✅ 2. Final AI response

This is sent once the agent completes the response. It contains the final session and interaction data.

```json
{
  "type": "final",
  "session": {
    "id": "abc-123",
    "user_id": "user@example.com",
    "title": "Hello, who is Shakespeare?",
    "updated_at": "2025-04-21T14:40:15.589394"
  },
  "interaction": {
    "question": { "content": "Hello, who is Shakespeare?", "filters": {} },
    "answer": { "content": "William Shakespeare was an English playwright...", "filters": {} },
    "model": "gpt-4o-2024-08-06",
    "agent_name": "Georges",
    "token_usage": {
      "input_tokens": 0,
      "output_tokens": 0,
      "total_tokens": 0
    },
    "timestamp": "2025-04-21T14:40:15.589581"
  }
}
```

- Final payload to be displayed and optionally persisted
- Sent after all `"stream"` chunks

---

### ❌ 3. Error messages

Used when an error occurs during processing.

```json
{
  "type": "error",
  "session_id": "abc-123",
  "content": "Something went wrong while handling your message."
}
```

- Useful for displaying errors in the UI or logging
- `session_id` may be `null` if the session wasn't successfully created

---

## 🧠 Recommended Frontend Handling

A sample dispatcher logic in React:

```ts
websocket.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  switch (msg.type) {
    case "stream":
      appendToTranscript(msg.content); // partial update
      break;
    case "final":
      updateSession(msg.session);
      updateInteraction(msg.interaction);
      break;
    case "error":
      showErrorToast(msg.content);
      break;
    default:
      console.warn("Unknown message type:", msg);
  }
};
```

---

## ✅ Summary

- Use `"stream"` for real-time updates.
- Use `"final"` to persist interaction and session data.
- Use `"error"` to surface issues.
- All messages must include a top-level `"type"` field.

# Agent Pod HTTP/SSE Protocol

This document describes the current on-wire protocol exposed by `fred-runtime`
agent pods.

It is intentionally implementation-backed. The source of truth is the current
runtime code, primarily:

- `fred-runtime/fred_runtime/app/agent_app.py`
- `fred-sdk/fred_sdk/contracts/runtime.py`
- `fred-sdk/fred_sdk/graph/graph_runtime.py`
- `fred-runtime/fred_runtime/runtime_support/sql_checkpointer.py`

This page focuses on:

- HTTPS headers and authentication
- request/response shapes for `/agents/execute` and `/agents/execute/stream`
- SSE framing
- the identifiers used for conversation continuity and HITL resume
- the current checkpointing behavior and its limits

## 1. Endpoint Family

The pod mounts its routes under:

- `<base_url>/agents`

Example from the sample pod config:

- base URL: `/samples/agents/v1`
- execute endpoint: `/samples/agents/v1/agents/execute`
- streaming endpoint: `/samples/agents/v1/agents/execute/stream`

Related routes:

- `GET  <base_url>/agents`
- `POST <base_url>/agents/execute`
- `POST <base_url>/agents/execute/stream`
- `GET  <base_url>/agents/sessions/{session_id}/messages`

## 2. Authentication

### 2.1 Incoming request authentication

When pod security is enabled, the pod protects the routes with user
authentication and expects:

```http
Authorization: Bearer <user-jwt>
```

Current behavior:

- If security is enabled, the request goes through `get_current_user`.
- If security is disabled, the header is optional and may be absent.
- CORS currently allows:
  - `Content-Type`
  - `Authorization`

### 2.2 What the pod does with the token

The incoming Bearer token is:

- read from the HTTP `Authorization` header
- stripped to the raw access token
- stored in `RuntimeContext.access_token`

That token may then be reused by runtime adapters for outbound calls, notably:

- Knowledge Flow clients
- managed agent-instance resolution via control-plane
- MCP client auth helpers where configured

## 3. Request Model

The execution endpoints accept one JSON object with this logical shape:

```json
{
  "agent_id": "fred.samples.bank_transfer.graph",
  "message": "Transfer 200 EUR from ACC-001 to ACC-002",
  "context": {
    "session_id": "dev-session-32f2c7b1",
    "user_id": "alice",
    "team_id": "team-a",
    "correlation_id": "corr-123",
    "tenant": "default",
    "language": "en"
  }
}
```

Managed-instance execution uses `agent_instance_id` instead of `agent_id`:

```json
{
  "agent_instance_id": "instance-123",
  "message": "hello",
  "context": {
    "session_id": "session-1",
    "user_id": "alice"
  }
}
```

### 3.1 Required and exclusive fields

Exactly one of these must be present:

- `agent_id`
- `agent_instance_id`

Turn-shape rules:

- `message` is required for a normal turn
- `message` may be empty when `resume_payload` is present

### 3.2 `context` fields consumed today

`context` is an open JSON object, but the pod currently reads these keys:

| Field | Used for |
|---|---|
| `session_id` | Conversation identity and graph checkpoint thread id |
| `user_id` | Runtime/user identity |
| `team_id` | Team scoping for execution |
| `correlation_id` | Request correlation |
| `tenant` | Portable context tenant |
| `language` | Runtime language hint |

Fields not consumed by the current runtime are ignored.

## 4. Conversation Identity and Checkpoint Identity

There are two distinct identifiers in play.

### 4.1 Conversation/session identity

The primary conversation identifier is:

- `context.session_id`

Current runtime behavior:

- the pod copies `context.session_id` into `RuntimeContext.session_id`
- graph execution sets `ExecutionConfig.thread_id = context.session_id`
- the SQL checkpointer uses that `thread_id` as the durable conversation key

In practice:

- one `session_id` maps to one graph conversation thread
- killing and restarting the pod does not lose that thread, as long as the pod
  still points to the same SQL/SQLite store

### 4.2 Pending HITL checkpoint identity

During a HITL pause, the runtime also creates a checkpoint-specific identifier:

- `checkpoint_id`

This is emitted inside:

- `awaiting_human.request.checkpoint_id`

Purpose:

- identify the exact pending interrupt/checkpoint
- support stale-resume protection

Current important limitation:

- the runtime emits `checkpoint_id`
- the current HTTP execute request model does not expose a dedicated
  `checkpoint_id` input field
- therefore the HTTP protocol currently resumes by `session_id` plus the latest
  pending checkpoint for that session, not by an explicit checkpoint id sent by
  the caller

So today:

- `session_id` is the active resume selector over HTTP
- `checkpoint_id` is observable in events but not yet fully enforced
  end-to-end by the HTTP request contract

## 5. HITL Resume Payload

When the runtime pauses for human input, the client must call the same execute
endpoint again with:

- the same `session_id`
- a `resume_payload`

Choice-based HITL resumes now use this shape:

```json
{
  "agent_id": "fred.samples.bank_transfer.graph",
  "message": "",
  "context": {
    "session_id": "dev-session-32f2c7b1",
    "user_id": "alice"
  },
  "resume_payload": {
    "choice_id": "confirm"
  }
}
```

For free-text HITL, `resume_payload` may be another JSON-compatible value,
depending on the authoring helper used by the runtime.

Current compatibility note:

- `choice_step(...)` now accepts both:
  - `{"choice_id": "confirm"}`
  - `"confirm"`
- the intended protocol is the structured object form

## 6. `/agents/execute`

### 6.1 Request

```http
POST <base_url>/agents/execute
Content-Type: application/json
Authorization: Bearer <user-jwt>
```

Body:

```json
{
  "agent_id": "sentinel.react.v2",
  "message": "hello",
  "context": {
    "session_id": "demo",
    "user_id": "alice"
  }
}
```

### 6.2 Response

Content type:

- `application/json`

Response semantics:

- the endpoint internally runs the same runtime event stream as the SSE route
- it returns the terminal payload when a `final` event exists
- otherwise it returns the last emitted payload

Typical success response:

```json
{
  "kind": "final",
  "sequence": 0,
  "content": "Transfer completed."
}
```

Typical HITL pause response:

```json
{
  "kind": "awaiting_human",
  "sequence": 0,
  "request": {
    "stage": "transfer_confirmation",
    "title": "Confirm Transfer",
    "question": "Please confirm the following transfer...",
    "choices": [
      {"id": "confirm", "label": "Yes, confirm transfer", "description": null, "default": false},
      {"id": "cancel", "label": "No, cancel", "description": null, "default": false}
    ],
    "free_text": false,
    "metadata": {},
    "checkpoint_id": "1f1372b6-..."
  }
}
```

Typical runtime failure response:

```json
{
  "error": "Graph execution received a resume payload without a pending checkpoint."
}
```

## 7. `/agents/execute/stream`

### 7.1 Request

```http
POST <base_url>/agents/execute/stream
Content-Type: application/json
Authorization: Bearer <user-jwt>
Accept: text/event-stream
```

Body shape is the same as `/agents/execute`.

### 7.2 Response content type

- `text/event-stream`

### 7.3 SSE framing

The current implementation emits plain SSE `data:` frames only:

```text
data: {"kind":"status","sequence":0,"status":"analyze_intent","detail":"Understanding your request."}

data: {"kind":"tool_call","sequence":0,"tool_name":"get_account_details","call_id":"call-1","arguments":{"account_id":"ACC-001"}}

data: {"kind":"tool_result","sequence":0,"call_id":"call-1","tool_name":"get_account_details","content":"{\"ok\":true,...}","is_error":false,"sources":[],"ui_parts":[]}

data: {"kind":"awaiting_human","sequence":0,"request":{"stage":"transfer_confirmation","title":"Confirm Transfer","question":"Please confirm...","choices":[...],"free_text":false,"metadata":{},"checkpoint_id":"1f1372b6-..."}}

data: {"kind":"final","sequence":0,"content":"Transfer completed.","sources":[],"ui_parts":[],"model_name":null,"token_usage":null,"finish_reason":null}

```

Current SSE contract details:

- one JSON object per `data:` frame
- frames end with a blank line
- no custom `event:` name is used
- no SSE `id:` field is used
- no SSE `retry:` field is used

## 8. Runtime Event Types

The runtime currently emits these event kinds:

| `kind` | Meaning |
|---|---|
| `status` | Business/runtime status update |
| `tool_call` | Tool invocation started |
| `tool_result` | Tool invocation completed |
| `awaiting_human` | HITL pause |
| `assistant_delta` | Incremental text token/delta |
| `node_error` | Graph node failed and routed via `on_error` |
| `final` | Terminal answer |

### 8.1 `status`

```json
{
  "kind": "status",
  "sequence": 0,
  "status": "load_account",
  "detail": "Loading account details."
}
```

### 8.2 `tool_call`

```json
{
  "kind": "tool_call",
  "sequence": 0,
  "tool_name": "get_account_details",
  "call_id": "call-1",
  "arguments": {
    "account_id": "ACC-001"
  }
}
```

### 8.3 `tool_result`

```json
{
  "kind": "tool_result",
  "sequence": 0,
  "call_id": "call-1",
  "tool_name": "get_account_details",
  "content": "{\"ok\":true}",
  "is_error": false,
  "sources": [],
  "ui_parts": []
}
```

### 8.4 `awaiting_human`

```json
{
  "kind": "awaiting_human",
  "sequence": 0,
  "request": {
    "stage": "transfer_confirmation",
    "title": "Confirm Transfer",
    "question": "Please confirm the following transfer...",
    "choices": [
      {
        "id": "confirm",
        "label": "Yes, confirm transfer",
        "description": null,
        "default": false
      }
    ],
    "free_text": false,
    "metadata": {},
    "checkpoint_id": "1f1372b6-..."
  }
}
```

Fields of `request`:

| Field | Meaning |
|---|---|
| `stage` | Business stage id for the HITL gate |
| `title` | Short UI title |
| `question` | Main prompt shown to the user |
| `choices` | Structured options for a choice-based resume |
| `free_text` | Whether raw human text is expected |
| `metadata` | Additional small UI/business metadata |
| `checkpoint_id` | Pending HITL checkpoint identifier |

### 8.5 `assistant_delta`

```json
{
  "kind": "assistant_delta",
  "sequence": 0,
  "delta": "hello"
}
```

### 8.6 `node_error`

```json
{
  "kind": "node_error",
  "sequence": 0,
  "node_id": "load_account",
  "error_message": "tool timeout",
  "routed_to": "finalize"
}
```

### 8.7 `final`

```json
{
  "kind": "final",
  "sequence": 0,
  "content": "Transfer completed.",
  "sources": [],
  "ui_parts": [],
  "model_name": "gpt-4.1-mini",
  "token_usage": {
    "input_tokens": 10,
    "output_tokens": 4,
    "total_tokens": 14
  },
  "finish_reason": "stop"
}
```

## 9. Session History Endpoint

The pod also exposes:

```http
GET <base_url>/agents/sessions/{session_id}/messages
Authorization: Bearer <user-jwt>
```

Purpose:

- return the persisted message history for a session
- read directly from the SQL checkpointer

History lookup key:

- `thread_id = {session_id}`

If no checkpoint exists for that session, the route returns:

```json
[]
```

## 10. Managed Agent Instance Resolution

If the caller uses `agent_instance_id` instead of `agent_id`:

- the pod resolves that instance through control-plane
- the pod forwards the same Bearer token to control-plane
- the resolved template id selects the in-pod definition
- the resolved owner team id becomes the effective team scope

So for managed execution there are two agent identifiers:

| Identifier | Meaning |
|---|---|
| `template_agent_id` | The registered agent definition in the pod |
| `agent_instance_id` | The managed runtime identity resolved by control-plane |

## 11. Current Resume Semantics

Today the practical resume rules are:

1. Start a conversation with a stable `context.session_id`.
2. When an `awaiting_human` event is emitted, keep that same `session_id`.
3. Resume by calling `/agents/execute` or `/agents/execute/stream` again with:
   - the same `session_id`
   - `message: ""`
   - the chosen `resume_payload`
4. The graph runtime reloads the pending checkpoint from SQL for that session.

This means:

- pod restart is supported, as long as the same SQL/SQLite store is preserved
- MCP reconnection after restart is expected and not itself a protocol problem

Current limitation:

- `checkpoint_id` is emitted to clients but is not yet part of the public HTTP
  execute request contract
- stale/out-of-order resume protection is therefore not yet fully enforced at
  the HTTP layer

## 12. Minimal Reference Examples

### 12.1 Normal streaming turn

```http
POST /samples/agents/v1/agents/execute/stream
Authorization: Bearer <jwt>
Content-Type: application/json
Accept: text/event-stream
```

```json
{
  "agent_id": "fred.samples.bank_transfer.graph",
  "message": "Transfer 200 EUR from ACC-001 to ACC-002",
  "context": {
    "session_id": "dev-session-32f2c7b1",
    "user_id": "alice"
  }
}
```

### 12.2 HITL resume turn

```http
POST /samples/agents/v1/agents/execute/stream
Authorization: Bearer <jwt>
Content-Type: application/json
Accept: text/event-stream
```

```json
{
  "agent_id": "fred.samples.bank_transfer.graph",
  "message": "",
  "context": {
    "session_id": "dev-session-32f2c7b1",
    "user_id": "alice"
  },
  "resume_payload": {
    "choice_id": "confirm"
  }
}
```

## 13. Recommended Future Cleanup

This document uses the word "protocol" because that is the current working
name. A more precise future name would likely be one of:

- `AGENT_POD_HTTP_API.md`
- `AGENT_POD_RUNTIME_PROTOCOL.md`
- `SSE_RUNTIME_EVENT_PROTOCOL.md`


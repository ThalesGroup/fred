# EvalTrace — Implementation Plan

**Feature:** `POST /agents/evaluate` endpoint + `/mode eval` CLI mode  
**Scope:** `fred-sdk` (models) · `fred-runtime` (endpoint + CLI)  
**Status:** Ready to implement

---

## Context

External evaluation tools (DeepEval, Promptfoo) need a single synchronous HTTP response
that contains everything required to compute evaluation KPIs — no SSE parsing, no Langfuse
dependency. This plan adds one new endpoint and one CLI mode. The existing execute path is
unchanged.

Sample response shapes: `libs/fred-runtime/docs/eval-trace-examples.md`

---

## Dependency order

```
Step 1  fred-sdk/contracts/eval.py          (new models — no deps)
Step 2  fred-sdk/__init__.py                (export new models)
Step 3  fred-runtime/app/agent_app.py       (_TurnOutcome + refactor + endpoint)
Step 4  fred-runtime/cli/pod_client.py      (AgentPodClient.evaluate)
Step 5  fred-runtime/cli/repl_helpers.py    (ExecutionMode + parse_mode_command)
Step 6  fred-runtime/cli/history_display.py (run_eval_turn)
Step 7  fred-runtime/cli/repl.py            (current_mode + /mode eval dispatch)
Step 8  fred-runtime/cli/__init__.py        (export run_eval_turn)
Step 9  fred-runtime/client.py shim         (re-export run_eval_turn)
Step 10 Tests
Step 11 make code-quality + make test + make generate-openapi
```

---

## Step 1 — `fred-sdk/fred_sdk/contracts/eval.py` (NEW FILE)

```python
class EvalStep(FrozenModel):
    kind: str              # tool_call | tool_result | final | node_error | awaiting_human
    tool_name:     str | None = None
    call_id:       str | None = None
    arguments:     dict[str, object] | None = None
    content:       str | None = None
    is_error:      bool | None = None
    node_id:       str | None = None
    error_message: str | None = None


class EvalTrace(FrozenModel):
    session_id:    str
    agent_id:      str
    agent_tags: tuple[str, ...] = ()
    input:         str
    output:        str | None = None
    error:         str | None = None
    latency_ms:    int
    model_name:    str | None = None
    token_usage:   dict[str, int] | None = None   # keys: input_tokens, output_tokens
    finish_reason: str | None = None
    steps:             tuple[EvalStep, ...] = ()
    retrieval_context: tuple[str, ...]    = ()    # non-error tool_result contents, in order
    tools_called:      tuple[str, ...]    = ()    # tool names in call order
```
`agent_tags` exposes the semantic tags declared on the evaluated agent definition. It is intended for downstream evaluation clients that need to auto-resolve an evaluation profile such as RAG, SQL, or default.

Import only: `from fred_sdk.contracts.models import FrozenModel`

---

## Step 2 — `fred-sdk/fred_sdk/__init__.py`

Add one import and two `__all__` entries:

```python
from fred_sdk.contracts.eval import EvalStep, EvalTrace
```

---

## Step 3 — `fred-runtime/fred_runtime/app/agent_app.py`

Four changes, all co-located near `_emit_turn_completed` (≈ line 1380).

### 3a — `_TurnOutcome` dataclass + `_parse_turn_outcome` (new, ~30 lines)

Extracts all scalar values from the payloads list once.
Both `_emit_turn_completed` and `_build_eval_trace` call this — zero duplication.

```python
@dataclass(frozen=True)
class _TurnOutcome:
    model_name:    str | None
    finish_reason: str
    token_usage:   dict[str, Any] | None
    input_tokens:  int | None
    output_tokens: int | None
    tool_count:    int
    is_error:      bool
    total_ms:      int
    final_content: str | None


def _parse_turn_outcome(
    payloads: list[dict[str, Any]],
    turn_start: float,
) -> _TurnOutcome:
    total_ms    = int((time.monotonic() - turn_start) * 1000)
    tool_count  = sum(1 for p in payloads if p.get("kind") == "tool_call")
    final       = next((p for p in reversed(payloads) if p.get("kind") == "final"), None)
    is_error    = any(p.get("kind") == "execution_error" for p in payloads)
    token_usage = final.get("token_usage") if final else None
    return _TurnOutcome(
        model_name    = final.get("model_name") if final else None,
        finish_reason = "error" if is_error else ((final.get("finish_reason") or "") if final else ""),
        token_usage   = token_usage,
        input_tokens  = token_usage.get("input_tokens")  if token_usage else None,
        output_tokens = token_usage.get("output_tokens") if token_usage else None,
        tool_count    = tool_count,
        is_error      = is_error,
        total_ms      = total_ms,
        final_content = (final.get("content") or None) if final else None,
    )
```

### 3b — Refactor `_emit_turn_completed`

Replace the ~10 field-extraction lines with one call:

```python
outcome = _parse_turn_outcome(payloads, turn_start)
# then use outcome.model_name, outcome.total_ms, etc.
```

The `turn_start` parameter is already present — no signature change needed.

### 3c — `_build_eval_trace` (new, ~50 lines, pure function, no I/O)

```python
def _build_eval_trace(
    payloads:   list[dict[str, Any]],
    input_text: str,
    agent_id:   str,
    session_id: str,
    turn_start: float,
    agent_tags: tuple[str, ...] = (),
) -> EvalTrace:
    outcome = _parse_turn_outcome(payloads, turn_start)
    steps: list[EvalStep] = []
    retrieval_context: list[str] = []
    tools_called: list[str] = []
    error: str | None = None

    for p in payloads:
        kind = p.get("kind")
        if kind == "tool_call":
            steps.append(EvalStep(
                kind="tool_call", tool_name=p.get("tool_name"),
                call_id=p.get("call_id"), arguments=p.get("arguments") or {},
            ))
            if p.get("tool_name"):
                tools_called.append(p["tool_name"])

        elif kind == "tool_result":
            content  = p.get("content", "")
            is_error = p.get("is_error", False)
            steps.append(EvalStep(
                kind="tool_result", tool_name=p.get("tool_name"),
                call_id=p.get("call_id"), content=content, is_error=is_error,
            ))
            if not is_error:
                # Prefer structured sources (RAG hits); fall back to raw content string.
                # ⚠ Verify: does "sources" survive as a list of dicts in payloads?
                # If stripped during serialisation, remove the sources branch.
                sources = p.get("sources") or []
                if sources:
                    retrieval_context.extend(
                        s["content"] for s in sources if s.get("content")
                    )
                elif content:
                    retrieval_context.append(content)

        elif kind == "final":
            steps.append(EvalStep(kind="final", content=p.get("content")))

        elif kind == "node_error":
            steps.append(EvalStep(
                kind="node_error",
                node_id=p.get("node_id"), error_message=p.get("error_message"),
            ))

        elif kind == "awaiting_human":
            steps.append(EvalStep(kind="awaiting_human"))

        elif kind == "execution_error":
            error = p.get("message")

    return EvalTrace(
        session_id        = session_id,
        agent_id          = agent_id,
        agent_tags        = agent_tags,
        input             = input_text,
        output            = outcome.final_content,
        error             = error,
        latency_ms        = outcome.total_ms,
        model_name        = outcome.model_name,
        token_usage       = outcome.token_usage,
        finish_reason     = outcome.finish_reason or None,
        steps             = tuple(steps),
        retrieval_context = tuple(retrieval_context),
        tools_called      = tuple(tools_called),
    )
```

### 3d — `POST /agents/evaluate` route (new, ~40 lines)

Inside `_build_agent_router`. Copy `execute` handler verbatim; change only the return:

```python
@router.post("/evaluate")
async def evaluate(
    request: RuntimeExecuteRequest,
    http_request: Request,
    authenticated_user: KeycloakUser | None = Depends(_authenticated_user),
    container: PodApplicationContext = Depends(get_pod_container),
) -> EvalTrace:
    # ... identical to execute: grant validation, _resolve_agent_instance,
    #     _iterate_runtime_event_payloads, _emit_turn_completed, history write ...
    session_id = request.effective_session_id() or str(uuid4())
    return _build_eval_trace(
        payloads   = payloads,
        input_text = request.input or "",
        agent_id   = target.definition.agent_id,
        agent_tags = target.definition.tags,
        session_id = session_id,
        turn_start = turn_start,
    )
```

Auth deps, grant validation, history write: identical to `execute`.
No streaming. Response type: `EvalTrace` (FastAPI serialises via Pydantic).

---

## Step 4 — `fred-runtime/fred_runtime/cli/pod_client.py`

Add to `AgentPodClient`:

```python
def evaluate(
    self,
    *,
    agent_id:          str,
    message:           str,
    session_id:        str,
    user_id:           str,
    team_id:           str | None = None,
    agent_instance_id: str | None = None,
    checkpoint_id:     str | None = None,
) -> dict[str, Any]:
    runtime_context: dict[str, Any] = {"user_id": user_id}
    if team_id:
        runtime_context["team_id"] = team_id
    payload: dict[str, Any] = {
        "agent_id":         agent_id,
        "input":            message,
        "session_id":       session_id,
        "runtime_context":  runtime_context,
    }
    if agent_instance_id is not None:
        payload["agent_instance_id"] = agent_instance_id
    if checkpoint_id is not None:
        payload["checkpoint_id"] = checkpoint_id
    response = self.http_client.post(
        f"{self.base_url}/agents/evaluate",
        json=payload,
        headers=self._auth_headers(),
    )
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict):
        raise RuntimeError("Evaluate response must be a JSON object.")
    return result
```

No `resume_payload` — eval turns are always fresh invocations.

---

## Step 5 — `fred-runtime/fred_runtime/cli/repl_helpers.py`

Replace the `bool` mode type with a string literal:

```python
ExecutionMode = Literal["stream", "final", "eval"]

def execution_mode_label(mode: ExecutionMode) -> str:
    return mode  # already a human-readable label

def parse_mode_command(message: str) -> ExecutionMode | None:
    """None = show current mode. Raises ValueError on unknown input."""
    requested = message.strip().removeprefix("/mode").strip().lower()
    if not requested:
        return None
    if requested in ("stream", "final", "eval"):
        return requested
    raise ValueError(
        f"Unknown mode {requested!r}. Use `/mode stream`, `/mode final`, or `/mode eval`."
    )
```

**⚠ Breaking change to callers:** `repl.py` currently uses `current_stream: bool`.
Replace all references with `current_mode: ExecutionMode`.
ANSI colour: green for stream, yellow for final, cyan for eval.

---

## Step 6 — `fred-runtime/fred_runtime/cli/history_display.py`

Add after `run_single_turn`:

```python
def run_eval_turn(
    *,
    client:        AgentPodClient,
    agent_id:      str,
    message:       str,
    session_id:    str,
    user_id:       str,
    team_id:       str | None,
    color_enabled: bool,
) -> int:
    """Call /agents/evaluate and pretty-print the EvalTrace JSON."""
    result = client.evaluate(
        agent_id=agent_id,
        message=message,
        session_id=session_id,
        user_id=user_id,
        team_id=team_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("error") is None else 1
```

---

## Step 7 — `fred-runtime/fred_runtime/cli/repl.py`

1. Replace `stream: bool` parameter + `current_stream` local with `current_mode: ExecutionMode`.
2. Update `/mode` branch (≈ line 241) — use `parse_mode_command` new return type.
3. Update the turn dispatch (≈ line 1177):

```python
if current_mode == "eval":
    exit_code = run_eval_turn(
        client=client, agent_id=current_agent,
        message=message, session_id=current_session_id,
        user_id=user_id, team_id=current_team_id,
        color_enabled=color_enabled,
    )
else:
    exit_code, hitl = run_single_turn(
        ..., stream=(current_mode == "stream"), ...
    )
    while hitl is not None:
        ...  # unchanged
```

4. Update the prompt label colour: cyan for `"eval"`.
5. Update `run_interactive_chat` signature: `stream: bool` → `mode: ExecutionMode = "stream"`.

---

## Step 8 — `fred-runtime/fred_runtime/cli/__init__.py`

Add `run_eval_turn` to imports and `__all__`.

---

## Step 9 — `fred-runtime/fred_runtime/client.py` shim

Add `run_eval_turn` to the re-export list.

---

## Step 10 — Tests

### `fred-sdk/tests/contracts/test_eval.py` (new)

- `EvalStep` construction for each `kind` value
- `EvalTrace` with empty steps, with all step types, with `retrieval_context`
- Confirm `retrieval_context` and `tools_called` default to empty tuples
- Confirm `EvalTrace` is immutable (FrozenModel)

### `fred-runtime/tests/test_eval_trace.py` (new)

Test `_parse_turn_outcome`:

- Normal turn (tool_call + tool_result + final)
- Error turn (execution_error only)
- Empty payloads
- HITL turn (awaiting_human, no final)

Test `_build_eval_trace`:

- Success: `retrieval_context` populated from tool_result content
- Success: `retrieval_context` populated from `sources` when present
- Error turn: `error` field set, `steps` empty
- Node error: `node_error` step present, output still set
- HITL: `awaiting_human` step present, `output=None`, `error=None`
- `tools_called` order matches tool_call order in payloads

---

## Step 11 — Verification

```bash
cd libs/fred-sdk    && make code-quality && make test
cd libs/fred-runtime && make code-quality && make test && make generate-openapi
```

Confirm `openapi.json` includes:

- `EvalTrace` schema under `#/components/schemas`
- `POST /agents/evaluate` operation

---

## Known verification point before coding Step 3c

Check whether `sources` survives in raw dict payloads from `_iterate_runtime_event_payloads`.
In `ToolResultRuntimeEvent`, `sources: tuple[VectorSearchHit, ...]` is a typed field.
If the dict representation drops it or it arrives as `[]` always, remove the `sources` branch
in `_build_eval_trace` and use `content` only.

Quick check:

```python
# Add temporarily in _iterate_runtime_event_payloads or a test:
print([p.get("sources") for p in payloads if p.get("kind") == "tool_result"])
```

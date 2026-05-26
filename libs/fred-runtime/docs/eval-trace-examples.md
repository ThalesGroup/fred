# EvalTrace — Sample HTTP Responses

Reference examples for the `POST /agents/evaluate` endpoint.
These illustrate the full response shape so evaluation harnesses (DeepEval, Promptfoo, custom) can be designed before the endpoint ships.

---

## Case 1 — Successful RAG turn (two tool calls, structured sources)

The agent searches a knowledge base and produces a grounded answer.
`retrieval_context` is ready-made for DeepEval faithfulness / answer-relevancy metrics.

```json
{
  "session_id": "3f8a1c2d-9e47-4b60-a112-7d5c83ef0192",
  "agent_id": "sql-analyst",
  "input": "How many tabular datasets are available in the corpus?",
  "output": "There are currently 3 tabular datasets in the corpus: sales_q1, inventory_snapshot, and customer_churn.",
  "error": null,
  "latency_ms": 2134,
  "model_name": "mistral-medium-2508",
  "token_usage": {
    "input_tokens": 512,
    "output_tokens": 48
  },
  "finish_reason": "stop",
  "steps": [
    {
      "kind": "tool_call",
      "tool_name": "knowledge.tabular.list_tabular_datasets",
      "call_id": "call-a1b2c3",
      "arguments": {},
      "content": null,
      "is_error": null,
      "node_id": null,
      "error_message": null
    },
    {
      "kind": "tool_result",
      "tool_name": "knowledge.tabular.list_tabular_datasets",
      "call_id": "call-a1b2c3",
      "arguments": null,
      "content": "sales_q1 | 14 200 rows | uploaded 2026-04-01\ninventory_snapshot | 8 900 rows | uploaded 2026-04-15\ncustomer_churn | 22 400 rows | uploaded 2026-05-01",
      "is_error": false,
      "node_id": null,
      "error_message": null
    },
    {
      "kind": "tool_call",
      "tool_name": "knowledge.text.search",
      "call_id": "call-d4e5f6",
      "arguments": { "query": "tabular dataset count corpus", "top_k": 3 },
      "content": null,
      "is_error": null,
      "node_id": null,
      "error_message": null
    },
    {
      "kind": "tool_result",
      "tool_name": "knowledge.text.search",
      "call_id": "call-d4e5f6",
      "arguments": null,
      "content": "The corpus currently holds 3 registered tabular datasets.",
      "is_error": false,
      "node_id": null,
      "error_message": null
    },
    {
      "kind": "final",
      "tool_name": null,
      "call_id": null,
      "arguments": null,
      "content": "There are currently 3 tabular datasets in the corpus: sales_q1, inventory_snapshot, and customer_churn.",
      "is_error": null,
      "node_id": null,
      "error_message": null
    }
  ],
  "retrieval_context": [
    "sales_q1 | 14 200 rows | uploaded 2026-04-01\ninventory_snapshot | 8 900 rows | uploaded 2026-04-15\ncustomer_churn | 22 400 rows | uploaded 2026-05-01",
    "The corpus currently holds 3 registered tabular datasets."
  ],
  "tools_called": [
    "knowledge.tabular.list_tabular_datasets",
    "knowledge.text.search"
  ]
}
```

### DeepEval mapping

```python
from deepeval.test_case import LLMTestCase

test_case = LLMTestCase(
    input=trace["input"],
    actual_output=trace["output"],
    retrieval_context=trace["retrieval_context"],  # direct — no scraping
    # expected_output comes from your test harness (golden answer)
    # expected_tools comes from your test harness
)
```

---

## Case 2 — Agent error (execution_error, no output)

The agent raised an unhandled exception. `output` is null, `error` is populated, `steps` may be partial.

```json
{
  "session_id": "a9f03b1e-2c88-4d77-b563-1e4a72dc8f30",
  "agent_id": "sql-analyst",
  "input": "Run a full export of the production database.",
  "output": null,
  "error": "Agent 'sql-analyst' raised: ConnectionError: Knowledge Flow backend unreachable at http://localhost:8111",
  "latency_ms": 387,
  "model_name": null,
  "token_usage": null,
  "finish_reason": null,
  "steps": [],
  "retrieval_context": [],
  "tools_called": []
}
```

### DeepEval mapping

```python
# Your harness should detect error turns and skip LLM metrics,
# but can still record latency and flag the turn as failed.
if trace["error"]:
    mark_as_failed(trace["error"])
```

---

## Case 3 — Node error with recovery (on_error routing, partial steps)

A tool call failed mid-graph. The runtime routed via `on_error` and still produced a final answer.
`steps` contains the `node_error` so the evaluator can detect degraded paths.

```json
{
  "session_id": "c72e9d4a-5f11-4a83-8b20-3c6d1f0ae741",
  "agent_id": "general-assistant",
  "input": "Show me the Prometheus metrics for the last 24 hours.",
  "output": "I was unable to retrieve live Prometheus metrics (the monitoring endpoint is currently unavailable). Based on the last known snapshot from 2026-05-03, p95 LLM latency was 1 840 ms.",
  "error": null,
  "latency_ms": 1820,
  "model_name": "mistral-medium-2508",
  "token_usage": {
    "input_tokens": 388,
    "output_tokens": 61
  },
  "finish_reason": "stop",
  "steps": [
    {
      "kind": "tool_call",
      "tool_name": "knowledge.prometheus.query_range",
      "call_id": "call-g7h8i9",
      "arguments": { "query": "llm_call_latency_ms", "range": "24h" },
      "content": null,
      "is_error": null,
      "node_id": null,
      "error_message": null
    },
    {
      "kind": "tool_result",
      "tool_name": "knowledge.prometheus.query_range",
      "call_id": "call-g7h8i9",
      "arguments": null,
      "content": "",
      "is_error": true,
      "node_id": null,
      "error_message": null
    },
    {
      "kind": "node_error",
      "tool_name": null,
      "call_id": null,
      "arguments": null,
      "content": null,
      "is_error": null,
      "node_id": "fetch_metrics",
      "error_message": "TimeoutError: prometheus endpoint did not respond within 5 s"
    },
    {
      "kind": "final",
      "tool_name": null,
      "call_id": null,
      "arguments": null,
      "content": "I was unable to retrieve live Prometheus metrics (the monitoring endpoint is currently unavailable). Based on the last known snapshot from 2026-05-03, p95 LLM latency was 1 840 ms.",
      "is_error": null,
      "node_id": null,
      "error_message": null
    }
  ],
  "retrieval_context": [],
  "tools_called": ["knowledge.prometheus.query_range"]
}
```

### DeepEval note

`retrieval_context` is empty here (the tool error returned no content).
The evaluator should detect `node_error` steps and apply a **degraded-path** label
so faithfulness metrics are not penalised for a monitoring outage.

---

## Case 4 — HITL-blocked turn (agent paused awaiting human input)

The agent hit a `choice_step` gate and is waiting. `output` is null, `error` is null.
This is a valid terminal state for evaluation — the evaluator should record it as **incomplete**
and not compute answer-quality metrics.

```json
{
  "session_id": "e14b7f92-8a33-4c01-9d55-6f2b0c3d8e47",
  "agent_id": "bank-transfer-agent",
  "input": "Transfer 5 000 € from account FR76 to account FR29.",
  "output": null,
  "error": null,
  "latency_ms": 943,
  "model_name": "mistral-medium-2508",
  "token_usage": {
    "input_tokens": 271,
    "output_tokens": 0
  },
  "finish_reason": null,
  "steps": [
    {
      "kind": "tool_call",
      "tool_name": "bank.risk_guard.score_transfer",
      "call_id": "call-j1k2l3",
      "arguments": {
        "from_account": "FR76",
        "to_account": "FR29",
        "amount_eur": 5000
      },
      "content": null,
      "is_error": null,
      "node_id": null,
      "error_message": null
    },
    {
      "kind": "tool_result",
      "tool_name": "bank.risk_guard.score_transfer",
      "call_id": "call-j1k2l3",
      "arguments": null,
      "content": "risk_score=0.72 | flag=HIGH | reason=unusual_destination_country",
      "is_error": false,
      "node_id": null,
      "error_message": null
    },
    {
      "kind": "awaiting_human",
      "tool_name": null,
      "call_id": null,
      "arguments": null,
      "content": null,
      "is_error": null,
      "node_id": null,
      "error_message": null
    }
  ],
  "retrieval_context": [
    "risk_score=0.72 | flag=HIGH | reason=unusual_destination_country"
  ],
  "tools_called": ["bank.risk_guard.score_transfer"]
}
```

### DeepEval note

Detect HITL turns with:

```python
is_hitl = any(s["kind"] == "awaiting_human" for s in trace["steps"])
```

Skip answer-quality metrics. You can still evaluate **tool correctness**
(was `risk_guard.score_transfer` called?) and **latency**.

---

## Field reference

| Field               | Type          | Always present | Notes                                                            |
| ------------------- | ------------- | -------------- | ---------------------------------------------------------------- |
| `session_id`        | string        | yes            | UUID; correlates with history/checkpoint                         |
| `agent_id`          | string        | yes            | Template agent id                                                |
| `input`             | string        | yes            | User message sent                                                |
| `output`            | string\|null  | —              | null on error or HITL                                            |
| `error`             | string\|null  | —              | null on success or HITL                                          |
| `latency_ms`        | int           | yes            | Wall-clock ms, first event → final                               |
| `model_name`        | string\|null  | —              | null if agent errored before LLM call                            |
| `token_usage`       | object\|null  | —              | keys: `input_tokens`, `output_tokens`                            |
| `finish_reason`     | string\|null  | —              | `"stop"`, `"length"`, `"tool_calls"`, null on error              |
| `steps`             | array         | yes            | Ordered execution trace; may be empty                            |
| `retrieval_context` | array[string] | yes            | Non-error tool_result contents; empty if no tools or all errored |
| `tools_called`      | array[string] | yes            | Tool names in call order; empty if no tools invoked              |

## Detecting turn outcome

```python
def classify_turn(trace: dict) -> str:
    if trace["error"]:
        return "execution_error"
    if any(s["kind"] == "awaiting_human" for s in trace["steps"]):
        return "hitl_blocked"
    if any(s["kind"] == "node_error" for s in trace["steps"]):
        return "degraded"   # completed but with a node failure on the path
    if trace["output"]:
        return "success"
    return "unknown"
```

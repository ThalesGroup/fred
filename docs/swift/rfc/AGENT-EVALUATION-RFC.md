# RFC — Fred Agent Evaluation Strategy

## Status

Draft

## Authors

Dimitri Tombroff

## Version

v1

---

## 1. Context and Motivation

Fred agents are becoming increasingly complex:

- Tool usage (MCP, Knowledge Flow, custom toolsets)
- Multi-step reasoning (LangGraph, ReAct)
- Security and access control (document permissions, team scoping)
- Multi-turn sessions with state

The current evaluation approach (`BaseEvaluator` / `SqlAgentEvaluator` in
`agentic-backend`) has three structural defects that prevent it from scaling:

1. **In-process bootstrap**: evaluators instantiate `ApplicationContext` and
   the agent directly — they do not exercise the HTTP path, ignore security
   middleware, and couple evaluation logic to `agentic-backend` internals.

2. **One class per agent**: the `BaseEvaluator → SqlAgentEvaluator` pattern
   produces one maintenance burden per agent. Variability must live in
   datasets, not in code.

3. **deepeval as a core dependency**: deepeval pulls ~50 transitive dependencies
   (openai, rich, portalocker, etc.). `fred-runtime` is a published pip library
   with a minimal dependency graph; this cannot be accepted even as an optional
   extra.

This RFC defines an evaluation architecture that is robust, industrializable,
and maintainable as the number of agents grows.

---

## 2. Design Principles

**PROMPT-01 — Execution belongs to Fred. Scoring does not.**

Fred knows how to talk to its agents, navigate Keycloak auth, and interpret SSE
events. Fred should not own LLM-as-judge calibration, HTML report generation,
or baseline regression tracking — these are solved problems in external tooling.

**P2 — Always evaluate through HTTP.**

Evaluation must call the same HTTP path that production uses. In-process
bootstrapping is not evaluation; it is unit testing of internals. Any test that
bypasses the HTTP layer does not prove the agent works as deployed.

**P3 — Variability lives in datasets, not in code.**

The evaluation runner is agent-agnostic. Agent-specific knowledge lives in
Q&A dataset files (YAML/JSON) checked into version control. Adding a new agent
to the evaluation suite means adding a dataset file, not a new class.

**P4 — Zero new dependencies in fred-runtime.**

`fred-runtime` contributes one thing to evaluation: an `EvalTraceCollector`
that aggregates SSE events into a structured trace dict. This is
protocol-knowledge about Fred's SSE format, not evaluation logic. It adds zero
dependencies.

---

## 3. Problem: Final Answer Is Not Enough

Evaluating only the final text output of an agent is insufficient for agentic
systems. Consider:

- An agent that halluccinates an answer without calling any tool scores
  identically to one that correctly used the MCP tool — if only `output` is
  inspected.
- A RAG agent that retrieves the wrong documents but produces a plausible
  answer is invisible to output-only scoring.
- A multi-step graph agent that reaches the right answer via the wrong reasoning
  path cannot be detected without the execution trace.

**The evaluation unit for a Fred agent is the execution trace, not the answer.**

---

## 4. The Evaluation Trace Contract

Fred already produces this information in its SSE stream. The missing piece is a
collector that aggregates it into a stable, structured format consumable by
external evaluation tools.

### 4.1 EvalTrace format

```json
{
  "session_id": "eval-sql-001",
  "agent_id": "sql-analyst",
  "input": "How many tabular datasets are available?",
  "output": "There are 3 tabular datasets available.",
  "error": null,
  "latency_ms": 1847,
  "model": "gpt-4o-mini",
  "usage": {
    "prompt_tokens": 412,
    "completion_tokens": 67
  },
  "steps": [
    {
      "kind": "tool_call",
      "name": "knowledge.tabular.list_tabular_datasets",
      "input": {}
    },
    {
      "kind": "tool_result",
      "name": "knowledge.tabular.list_tabular_datasets",
      "output": "[dataset_a, dataset_b, dataset_c]"
    },
    {
      "kind": "final",
      "content": "There are 3 tabular datasets available."
    }
  ]
}
```

### 4.2 What this enables

| Evaluation type                          | Fields required                                            |
| ---------------------------------------- | ---------------------------------------------------------- |
| Output quality (LLM-as-judge, substring) | `output`                                                   |
| Tool usage correctness                   | `steps[kind=tool_call].name`, `.input`                     |
| Tool result faithfulness                 | `steps[kind=tool_result].output`                           |
| RAG source grounding                     | `steps[kind=tool_result]` where name matches `knowledge.*` |
| Error robustness                         | `error` non-null                                           |
| Latency / cost SLO                       | `latency_ms`, `usage`                                      |
| Regression detection                     | any field, compared against baseline                       |

### 4.3 Derivation

All fields in `EvalTrace` are derivable from the existing SSE event stream
(`kind: tool_call`, `kind: tool_result`, `kind: final`, `kind: node_error`,
`kind: assistant_delta`). No new server endpoint is required. The collector is
a pure aggregation function over the list returned by
`AgentPodClient.stream_events()`.

---

## 5. Architecture

### 5.1 Layers

```
┌─────────────────────────────────────────────────────┐
│  developer_tools/eval/                              │  ← evaluation harness
│    fred_provider.py      (Promptfoo custom provider)│
│    datasets/*.json       (agent-specific Q&A)       │
│    tests/*.yaml          (Promptfoo config per agent)│
│    Makefile                                          │
└────────────────────┬────────────────────────────────┘
                     │ AgentPodClient.stream_events()
                     ▼
┌─────────────────────────────────────────────────────┐
│  libs/fred-runtime/fred_runtime/eval/               │  ← protocol layer
│    collector.py   collect_eval_trace(events) → dict │
└────────────────────┬────────────────────────────────┘
                     │ HTTP SSE  POST /agents/execute/stream
                     ▼
┌─────────────────────────────────────────────────────┐
│  Agent Pod (agentic-backend / fred-runtime app)     │  ← unchanged
└─────────────────────────────────────────────────────┘
```

### 5.2 fred-runtime contribution (minimal)

A single new file: `fred_runtime/eval/collector.py`

```python
def collect_eval_trace(
    events: list[dict],
    *,
    agent_id: str,
    input: str,
    session_id: str,
    started_at: float,
) -> dict:
    """
    Aggregate a list of SSE event dicts into a structured EvalTrace.
    Pure function. Zero new dependencies.
    """
```

This is the entirety of fred-runtime's evaluation surface. It encodes
knowledge of Fred's SSE event format (`kind` vocabulary) and nothing else.

### 5.3 developer_tools/eval/ layout

```
developer_tools/eval/
  pyproject.toml          # standalone project, deps: fred-runtime, promptfoo
  fred_provider.py        # Promptfoo Python provider — ~60 lines
  datasets/
    sql_analyst_qa.json
    sentinel_qa.json
    ...
  tests/
    sql_analyst.yaml      # Promptfoo eval config for SQL Analyst
    sentinel.yaml
    ...
  Makefile
  README.md
```

`developer_tools/eval/` is a **standalone project**. It depends on `fred-runtime`
(for `AgentPodClient` and `collect_eval_trace`) and on `promptfoo` (Node.js CLI,
installed separately). It does not depend on `agentic-backend`.

### 5.4 fred_provider.py responsibilities

```python
# Called by Promptfoo for each test case
def call_api(prompt: str, options: dict, context: dict) -> dict:
    client = AgentPodClient(
        base_url=os.environ["FRED_BASE_URL"],
        token=os.environ["FRED_TOKEN"],
    )
    agent_id = context["vars"]["agent_id"]
    session_id = f"eval-{uuid.uuid4().hex[:8]}"

    events = client.stream_events(
        agent_id=agent_id,
        message=prompt,
        session_id=session_id,
        user_id="eval-user",
        team_id=os.environ.get("FRED_TEAM_ID"),
    )
    trace = collect_eval_trace(events, agent_id=agent_id, input=prompt, session_id=session_id)

    return {
        "output": trace["output"],
        "tokenUsage": trace.get("usage", {}),
        "metadata": trace,         # full trace available to scorers
    }
```

### 5.5 Dataset format

```json
[
  {
    "id": "sql-001",
    "question": "How many tabular datasets are available?",
    "expected_output": "3",
    "tags": ["smoke", "tool_use"],
    "assert": [
      { "type": "contains", "value": "3" },
      {
        "type": "llm-rubric",
        "value": "The answer directly states how many datasets exist."
      }
    ]
  }
]
```

### 5.6 Promptfoo config (per agent)

```yaml
# tests/sql_analyst.yaml
description: "SQL Analyst agent evaluation"

providers:
  - id: "python:../fred_provider.py"
    config:
      agent_id: "sql-analyst"

defaultTest:
  options:
    provider: openai:gpt-4o-mini # LLM-as-judge

tests:
  - file: ../datasets/sql_analyst_qa.json
```

### 5.7 CI/CD integration

```yaml
# .github/workflows/eval.yml
- name: Evaluate SQL Analyst
  run: |
    cd developer_tools/eval
    npx promptfoo eval --config tests/sql_analyst.yaml --ci --output results/sql_analyst.xml
  env:
    FRED_BASE_URL: ${{ secrets.EVAL_POD_URL }}
    FRED_TOKEN: ${{ secrets.EVAL_TOKEN }}
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Promptfoo exits with a non-zero code when any assertion fails, integrating
cleanly with standard CI pipelines. The `--output` flag produces JUnit XML
readable by GitHub Actions, GitLab CI, and Jenkins.

---

## 6. Comparison: Fred-native vs External Tools

| Dimension           | Fred-native runner                         | External (Promptfoo)                         |
| ------------------- | ------------------------------------------ | -------------------------------------------- |
| Coupling            | Metrics coupled to Fred internals          | Fred exposes a contract; tool is agnostic    |
| Metric quality      | httpx-based LLM judge, manually calibrated | 30+ calibrated metrics, community-maintained |
| Reports             | Text output                                | HTML interactive + JUnit XML                 |
| Parallelism         | Manual implementation required             | Native, configurable                         |
| Regression baseline | Must be built                              | `promptfoo eval --baseline`                  |
| CI integration      | Custom exit codes                          | Standard, GitHub Actions native              |
| Maintenance         | Every metric evolution = fred-runtime PR   | Metrics evolve upstream                      |
| Initial cost        | 3–6 weeks to reach parity                  | ~1 week (provider + datasets + CI)           |

---

## 7. What Is Removed

Once this architecture is in place, the following can be deleted from
`agentic-backend`:

- `agentic_backend/tests/agents/base_deepeval_test.py`
- `agentic_backend/tests/agents/sql/sql_analyst_evaluation.py`
- `deepeval` from `agentic-backend` dependencies (if not used elsewhere)

---

## 8. Pitfalls to Avoid

**P-1 — Evaluation logic in fred-runtime.**
`fred-runtime` is a published pip library. Any eval dependency (deepeval,
sentence-transformers, even as an optional extra) contaminates the dependency
graph for all users of the library. The hard line: fred-runtime contributes only
`collect_eval_trace`. Everything else is in `developer_tools/eval/`.

**P-2 — In-process agent bootstrap.**
Tests that skip the HTTP layer do not prove the agent works as deployed. They
test internal wiring, not the production execution path. All evaluation must go
through `AgentPodClient` → HTTP.

**P-3 — Substring matching as the primary regression metric.**
Substring checks are useful for smoke tests. As a regression signal, they are
unreliable: prompt changes can improve quality while breaking dozens of substring
assertions. A calibrated LLM-as-judge (e.g. Promptfoo's `llm-rubric`) should be
the primary regression metric from the start.

**P-4 — No execution trace.**
An agent that halluccinates without using any tool is indistinguishable from a
correct agent if only `output` is evaluated. The `steps` field in `EvalTrace`
is what makes tool-use evaluation possible. Never discard it.

**P-5 — No baseline.**
Without a snapshotted reference score per agent version, regressions go
undetected. Run `promptfoo eval --baseline` after every significant prompt or
agent change and commit the baseline file to version control.

**P-6 — Keycloak auth required in CI.**
If evaluation requires an interactive PKCE flow, it will never run in CI.
Evaluation must support a static `FRED_TOKEN` environment variable (service
account or long-lived eval token) from day one.

**P-7 — Sequential evaluation.**
Evaluating 50 Q&A pairs sequentially against a remote pod is slow. Promptfoo
parallelizes by default. Do not serialize unless the agent has hard session-
ordering constraints.

---

## 9. Open Questions

| #    | Question                                                                                          | Impact                                                                                                                                                                                  |
| ---- | ------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| OQ-1 | Should `EvalTrace` be a typed Pydantic model in `fred-sdk`, or an untyped dict in `fred-runtime`? | Typing the contract in fred-sdk makes it easier to evolve; adding it to fred-sdk adds a contract obligation.                                                                            |
| OQ-2 | Should the eval pod use a dedicated team/user identity, or reuse developer credentials?           | Security hygiene in shared environments.                                                                                                                                                |
| OQ-3 | Promptfoo vs Inspect AI — final choice?                                                           | Promptfoo is recommended (broader adoption, YAML-first, CI-native). Inspect AI is better suited to structured benchmark tasks (MMLU-style). Both are compatible with this architecture. |
| OQ-4 | Should baseline files be committed to the repo or stored externally?                              | Committing baselines enables PR-level regression detection. External storage (RUNTIME-01, artifact store) scales better across many agents.                                             |

---

## 10. Implementation Sequence

1. **fred-runtime**: add `fred_runtime/eval/collector.py` — `collect_eval_trace()`
2. **developer_tools/eval/**: create the standalone project with `fred_provider.py`
3. **Datasets**: migrate existing `sql_analyst_evaluation.py` dataset to `datasets/sql_analyst_qa.json`
4. **Promptfoo config**: write `tests/sql_analyst.yaml` with the existing Q&A cases
5. **CI**: add the eval workflow, validate on the eval pod
6. **Cleanup**: remove `BaseEvaluator`, `SqlAgentEvaluator`, and deepeval from `agentic-backend`

Steps 1–5 can land without touching the production runtime.
Step 6 follows once the new flow is validated end-to-end.

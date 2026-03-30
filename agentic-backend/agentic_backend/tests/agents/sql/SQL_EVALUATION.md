# SQL Agent Evaluation

Evaluation script for the **V2 SQL analyst graph agent** using [DeepEval](https://deepeval.com/).

## Key difference from the RAG evaluator

| | RAG evaluator | SQL evaluator |
|---|---|---|
| Agent invocation | Internal (`agent.ainvoke()`) | Real WebSocket stack |
| Tests HTTP/auth | No | Yes |
| Tests MCP tool calls | No | Yes (get_context, read_query) |
| Agent version | V1 | V2 graph |
| Metrics | Faithfulness, Relevancy, Contextual* | AnswerRelevancy, SQL Correctness |

The SQL evaluator exercises the same path as a real user: WebSocket connection,
session lifecycle, graph execution, and MCP calls to the Knowledge Flow tabular API.

## Prerequisites

- A running **Fred agentic backend** (`make run` or deployed environment)
- A running **Knowledge Flow** with tabular data loaded
- A valid bearer token (`AGENTIC_TOKEN` env var or `--token` flag)
- `configuration.yaml` configured with the judge model (Ollama or OpenAI)

## Metrics

### AnswerRelevancyMetric
LLM-as-judge: does the answer actually address the user's question?
Catches responses that dodge the question or go off-topic.

### SQL Correctness (GEval)
LLM-as-judge: does the answer contain or convey the expected fact/value?
Uses the `expect` field from the scenario file as a hint to the judge model.
This is a soft check — the judge can score a paraphrased correct answer as passing.

## Dataset format

Compatible with `developer_tools/sql_scenario.json`:

```json
[
  {
    "question": "How many ports are in the database?",
    "expect": "8"
  },
  {
    "question": "List the military ports.",
    "expect": "Toulon"
  }
]
```

`expect` is used for both:
- An **informational substring check** logged to the console (mirrors Go probe)
- A **hint for the GEval judge** passed as `expected_output`

Questions without `expect` are still evaluated for relevancy.

## Usage

```bash
cd agentic-backend

python agentic_backend/tests/agents/sql/sql_analyst_evaluation.py \
  --chat_model      "gpt-4o" \
  --embedding_model "text-embedding-3-small" \
  --dataset_path    "../../developer_tools/sql_scenario.json" \
  --url             "ws://localhost:8000/agentic/v1/chatbot/query/ws" \
  --token           "$AGENTIC_TOKEN" \
  --agent_id        "candidate.sql_agent.graph.v2"
```

Or with a custom configuration file:

```bash
python agentic_backend/tests/agents/sql/sql_analyst_evaluation.py \
  --chat_model      "llama3.1:70b" \
  --embedding_model "nomic-embed-text" \
  --dataset_path    "../../developer_tools/sql_scenario.json" \
  --configuration_file "configuration-local.yaml"
```

### Arguments

| Argument | Required | Description |
|---|---|---|
| `--chat_model` | Yes | Model name for LLM-as-judge (must match provider in config) |
| `--embedding_model` | Yes | Embedding model name (kept for CLI consistency, unused here) |
| `--dataset_path` | Yes | Path to JSON scenario file |
| `--url` | No | WebSocket URL (default: `ws://localhost:8000/…/ws`, or `AGENTIC_WS_URL` env) |
| `--token` | No | Bearer token (default: `AGENTIC_TOKEN` env var) |
| `--agent_id` | No | Agent ID (default: `candidate.sql_agent.graph.v2`) |
| `--timeout` | No | Per-question timeout in seconds (default: 60) |
| `--configuration_file` | No | Config filename (default: `configuration.yaml`) |

## Output

```
📝  8 question(s) from sql_scenario.json
🔗  Session created: abc123
🔄  Evaluation in progress...
➡️   [1/8] Quelles sont les colonnes de la table des radars ?
✓   Answer (142 chars)
    [SUBSTRING PASS] expected 'radar_id' found in answer
➡️   [2/8] Combien y a-t-il de ports dans la base ?
✓   Answer (38 chars)
    [SUBSTRING PASS] expected '8' found in answer
...

======================================================================
AVERAGES PER METRIC
======================================================================

Answer Relevancy
──────────────────────────────────────────────────────────────────────
  Average:           0.9125 (91.25%)

SQL Correctness
──────────────────────────────────────────────────────────────────────
  Average:           0.8750 (87.50%)

======================================================================
OVERALL AVERAGE
======================================================================
  Overall average:   0.8938 (89.38%)
```

## Architecture notes

- One session is created for the full run (matches Go probe behaviour).
  Questions within a run share conversational context.
- Partial/streaming WebSocket events (`type: "stream"`) are skipped.
  Only the committed `type: "final"` snapshot is used for evaluation.
- On timeout or agent error, the answer is recorded as empty — both metrics
  will score 0 for that question, surfacing the failure clearly.

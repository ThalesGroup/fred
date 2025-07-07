# 📊 Fred Monitoring System

A flexible, JSONL-based metric logging and querying framework for LangGraph nodes and LangChain tools.

- Lightweight local storage (JSONL).
- In-memory caching for fast reads.
- Flexible time-window queries.
- Dynamic aggregation with groupby.
- Pluggable with your existing LangGraph or LangChain code.

## Overview
Fred Monitoring lets you **record and analyze** the performance and usage of your system.

**Key ideas:**

- **Instrumentation:** Add decorators to log metrics automatically.
- **Persistence:** All events saved to JSONL, with optional fields.
- **Query:** Expose REST endpoints to filter, aggregate, and analyze metrics.
- **Flexibility:** Dynamic groupby and aggregation in queries.

## Quick Example: How to use the decorators

### 1️⃣ For LangGraph nodes

```python

from app.monitoring.node_monitoring.monitor_node import monitor_node

def get_graph(self):
        """
        Simple graph
        """
        builder = StateGraph(MessagesState)
        builder.add_node("myNode", monitor_node(self.myNode))
        builder.add_edge(START, "myNode")
        builder.add_edge("myNode", END)
        return builder
```
What it does:

- Records latency.

- Captures user_id / session_id / agent_name from context.

- Saves a NodeMetric entry.

### 2️⃣ For LangChain tools

```python

from langchain_core.tools import BaseToolkit
from app.monitoring.tool_monitoring.monitor_tool import monitor_tool

class MyToolkit(BaseToolkit):
    """
    Simple Toolkit
    """

    def __init__(self, tools):
        super().__init__()
        self.tools = [monitor_tool(tool) for tool in tools]

    @override
    def get_tools(self) -> list[BaseTool]:
        """Get the tools in the toolkit."""
        return self.tools

```
What it does:

- Wraps _run/_arun to time executions.

- Captures user/session context.

- Saves a ToolMetric entry.

## How it Works

- At runtime, the decorators log metrics including:

  - Timestamp

  - Latency

  - User and session identifiers

  - Tool/Node name

  - Custom metadata

- Metrics are stored in JSONL files on disk (append-only).

- A FastAPI server exposes endpoints to read and analyze them.

## 📚 REST API Endpoints

Your FastAPI app registers endpoints under:

✅ /metrics/nodes/...
✅ /metrics/tools/...

**Each has the same set of 3 main endpoints:**

### 1️⃣ /all

  Returns raw, unaggregated metrics in a time range.

**Example request:**
```bash
http://localhost:8000/fred/metrics/nodes/all?start=2025-06-10T12:30:00&end=2025-07-10T23:00:00
```

**Example response:**
```bash
[
  {
    "timestamp": 1751286058.90173,
    "node_name": "reasoner",
    "latency": 1.30374222599858,
    "user_id": "admin@mail.com",
    "session_id": "b7G9wfuDpmw",
    "agent_name": "MonitoringExpert",
    "model_name": "gpt-4o-2024-11-20",
    "input_tokens": 1008,
    "output_tokens": 14,
    "total_tokens": 1022,
    "result_summary": "Hello! How can I assist you with Kubernetes monitoring today?",
    "metadata": {
      "messages": [
        {
          "content": "Hello! How can I assist you with Kubernetes monitoring today?",
          "additional_kwargs": {
            "refusal": null
          },
          "response_metadata": {
            "token_usage": {
              "completion_tokens": 14,
              "prompt_tokens": 1008,
              "total_tokens": 1022,
              "completion_tokens_details": {
                "accepted_prediction_tokens": 0,
                "audio_tokens": 0,
                "reasoning_tokens": 0,
                "rejected_prediction_tokens": 0
              },
              "prompt_tokens_details": {
                "audio_tokens": 0,
                "cached_tokens": 0
              }
            },
            "model_name": "gpt-4o-2024-11-20",
            "system_fingerprint": "fp_ee1d74bde0",
            "id": "chatcmpl-Bo7nGwuh1qt0Npf7jxJzNHyfEzUlD",
            "service_tier": null,
            "prompt_filter_results": [
              {
                "prompt_index": 0,
                "content_filter_results": {
                  "hate": {
                    "filtered": false,
                    "severity": "safe"
                  },
                  "jailbreak": {
                    "filtered": false,
                    "detected": false
                  },
                  "self_harm": {
                    "filtered": false,
                    "severity": "safe"
                  },
                  "sexual": {
                    "filtered": false,
                    "severity": "safe"
                  },
                  "violence": {
                    "filtered": false,
                    "severity": "safe"
                  }
                }
              }
            ],
            "finish_reason": "stop",
            "logprobs": null,
            "content_filter_results": {
              "hate": {
                "filtered": false,
                "severity": "safe"
              },
              "protected_material_code": {
                "filtered": false,
                "detected": false
              },
              "protected_material_text": {
                "filtered": false,
                "detected": false
              },
              "self_harm": {
                "filtered": false,
                "severity": "safe"
              },
              "sexual": {
                "filtered": false,
                "severity": "safe"
              },
              "violence": {
                "filtered": false,
                "severity": "safe"
              }
            }
          },
          "type": "ai",
          "name": null,
          "id": "run--cd867984-bc42-48fa-8efa-000356028781-0",
          "example": false,
          "tool_calls": [],
          "invalid_tool_calls": [],
          "usage_metadata": {
            "input_tokens": 1008,
            "output_tokens": 14,
            "total_tokens": 1022,
            "input_token_details": {
              "audio": 0,
              "cache_read": 0
            },
            "output_token_details": {
              "audio": 0,
              "reasoning": 0
            }
          }
        }
      ]
    }
  },
  ...
]
```

### 2️⃣ /numerical

  Returns aggregated numerical metrics with flexible groupby and aggregation.

**Example request:**
```bash
http://localhost:8000/fred/metrics/nodes/numerical?start=2025-06-10T12:30:00&end=2025-07-10T23:00:00&agg=latency:avg&agg=total_tokens:sum&precision=hour&groupby=agent_name
```

**Example response:**
```bash
[
  {
    "time_bucket": "2025-06-30 14:00",
    "values": {
      "latency--avg": 2.5242,
      "total_tokens--sum": 12628
    },
    "agent_name": "MonitoringExpert"
  },
  {
    "time_bucket": "2025-06-30 15:00",
    "values": {
      "latency--avg": 1.2262,
      "total_tokens--sum": 256
    },
    "agent_name": "GeneralistExpert"
  },
  {
    "time_bucket": "2025-06-30 15:00",
    "values": {
      "latency--avg": 1.4275,
      "total_tokens--sum": 1022
    },
    "agent_name": "MonitoringExpert"
  },
  ...
]
```

✅ Features:

  - Dynamic groupby fields (e.g., agent_name, model_name, user_id).

  - Flexible aggregation (avg, sum, min, max).

  - Time bucketing with precision (sec, min, hour, day).

### 3️⃣ /categorical

  Returns reduced records with only categorical fields.

**Example request:**
```bash
http://localhost:8000/fred/metrics/nodes/categorical?start=2025-06-10T12:30:00&end=2025-07-10T23:00:00
```

**Example response:**
```bash
[
  {
    "timestamp": 1751286058.90173,
    "user_id": "admin@mail.com",
    "session_id": "b7G9wfuDpmw",
    "agent_name": "MonitoringExpert",
    "model_name": "gpt-4o-2024-11-20",
    "model_type": null,
    "finish_reason": null,
    "id": null,
    "system_fingerprint": null,
    "service_tier": null
  },
  ...
]
```

✅ Use it to:

- List distinct users/sessions.

- Analyze model usage patterns.

- Filter and join with external data.


## Storage Format

  - JSONL file per store (nodes, tools).

  - Each line = 1 event.

  - Append-only.

  - Easily human-readable and debuggable.


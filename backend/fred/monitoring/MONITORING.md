
# 📊 LLM Monitoring Interface (MonitoringWrapper + API)

This module provides a **monitoring interface for LLM interactions**, exposing a FastAPI server to query stored metrics collected by the `MonitoringWrapper`. The system is designed to support observability, debugging, and performance analytics in LLM-based applications using LangChain.

---

## 🚀 FastAPI Monitoring Server

The `monitoring_api.py` module exposes 3 GET endpoints for querying metrics:

### ⚠️ Required for all endpoints:
All endpoints accept `start` and `end` parameters as **ISO 8601** strings (e.g., `2025-06-09T00:00:00`).

---

## 📂 Endpoints

### 1. `/metrics/all`
> Return all raw metrics without filtering or aggregation.

- 🧾 Full logs: latency, user ID, model info, token usage, etc.
- 📌 No precision, just a date range.

---

### 2. `/metrics/numerical`
> Return only numerical metrics aggregated by time precision.

- 📈 Aggregates latency, token counts, etc.
- 🕒 Precision options:
  - `second`, `minute` (default), `hour`, `day`

```http
GET fred/metrics/numerical?start=2025-06-09T00:00:00&end=2025-06-09T23:59:00&precision=minute
```

---

### 3. `/metrics/categorical`
> Return distinct categorical values per time slice.

- Includes fields like:
  - `user_id`, `model_type`, `model_name`, `session_id`, `finish_reason`
- Aggregates over fixed time intervals (1-minute chunks by default)

---

### 🔎 Docs available at:

- Swagger UI: [http://localhost:8000/fred/docs](http://localhost:8000/fred/docs)
- ReDoc: [http://localhost:8000/fred/redoc](http://localhost:8000/fred/redoc)

---

## 🧪 Example Queries and outputs

```bash
# Input :
curl "http://localhost:8000/fred/metrics/all?start=2025-06-09T00:00:00&end=2025-06-09T23:00:00"
# Output:
[
  {
    "token_usage": {
      "completion_tokens": 524,
      "prompt_tokens": 189,
      "total_tokens": 713,
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
    "id": "chatcmpl-BgY2gMh9OOieTpGRubOcF9HYjo0qV",
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
            "detected": false,
            "filtered": false
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
        "detected": false,
        "filtered": false
      },
      "protected_material_text": {
        "detected": false,
        "filtered": false
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
    },
    "user_id": "admin@mail.com",
    "session_id": "cMSuP_t7ODk",
    "latency": 6.666,
    "timestamp": 1749480339.95463,
    "model_type": "GeneralistExpert"
  },...
]
```
```bash
# Input :
curl "http://localhost:8000/fred/metrics/numerical?start=2025-06-09T00:00:00&end=2025-06-09T23:00:00&precision=hour"
# Output:
[
  {
    "timestamp": "2025-06-09T14:45:00",
    "latency": 6.666,
    "token_usage.completion_tokens": 524,
    "token_usage.prompt_tokens": 189,
    "token_usage.total_tokens": 713,
    "token_usage.completion_tokens_details.accepted_prediction_tokens": 0,
    "token_usage.completion_tokens_details.audio_tokens": 0,
    "token_usage.completion_tokens_details.reasoning_tokens": 0,
    "token_usage.completion_tokens_details.rejected_prediction_tokens": 0,
    "token_usage.prompt_tokens_details.audio_tokens": 0,
    "token_usage.prompt_tokens_details.cached_tokens": 0
  },...
]
```
```bash
# Input :
curl "http://localhost:8000/fred/metrics/categorical?start=2025-06-09T00:00:00&end=2025-06-09T23:00:00"
# Output:
[
  {
    "timestamp": "2025-06-09T14:45:39.954630613",
    "user_id": [
      "admin@mail.com"
    ],
    "model_type": [
      "GeneralistExpert"
    ],
    "model_name": [
      "gpt-4o-2024-11-20"
    ],
    "finish_reason": [
      "stop"
    ],
    "session_id": [
      "cMSuP_t7ODk"
    ]
  },...
]
```

---

## 🧠 Components Overview

### 🔹 `MonitoringWrapper`

This is a universal wrapper for any `BaseLanguageModel` (LangChain-compatible) that automatically logs:

- Execution latency
- Model metadata (name/type)
- Token usage (if available)
- User/session context (via `LoggingContext`)

It transparently wraps sync/async methods like `invoke()`, `predict()`, `generate_prompt()`, etc. and logs structured data into a `MetricStore`.

> ✅ Safe to use inside LangChain agents, LangGraph flows, or app logic.

---

### 🔹 `MetricStore`

A lightweight **in-memory + JSONL-persisted** metric log store that supports:

- Adding metrics at runtime
- Saving to / loading from file (`.jsonl`)
- Date range filtering
- Aggregating by time precision (e.g., minute, hour)
- Exporting metrics for dashboards or inspection

Metrical data is collected in-memory during runtime and optionally saved to:
```
fred/monitoring/logs/monitoring_logs.jsonl
```

---

### 🔹 `LoggingContext`

A tiny utility using `contextvars` to inject `user_id` and `session_id` across async tasks. This avoids passing identifiers explicitly through every function.

**Usage:**
```python
set_logging_context(user_id="alice@example.com", session_id="xyz123")
ctx = get_logging_context()
print(ctx["user_id"])  # alice@example.com
```

This is automatically used by the `MonitoringWrapper` to enrich every log.

---

## 🧱 Folder Structure

```text
fred/
├── monitoring/
│   ├── metric_store.py          # MetricStore logic (in-memory + file)
│   ├── logging_context.py       # Context-local user/session management
│   ├── MonitoringWrapper.py    # Wrapper for LangChain models
│   └── logs/
│       └── monitoring_logs.jsonl  # Persistent log file (JSONL)
├── services/
│   ├── monitoring/
│       ├── monitoring_controller.py            # FastAPI service exposing metrics initialize in fred/main.py
```

---
## 🔜 Possible Improvements

- Add filtering by `user_id`, `model_type`, or `session_id`
- Add a `/metrics/summary` for global stats (avg latency, token total, etc.)
- Export as CSV or Excel
- Add authentication for production use

---

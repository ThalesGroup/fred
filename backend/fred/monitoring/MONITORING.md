
# 📊 LLM Monitoring Interface (MonitoredLanguageModel + API)

This module provides a **monitoring interface for LLM interactions**, exposing a FastAPI server to query stored metrics collected by the `MonitoredLanguageModel`. The system is designed to support observability, debugging, and performance analytics in LLM-based applications using LangChain.

---

## 🚀 FastAPI Monitoring Server

The `metric_store_controller.py` module exposes 3 GET endpoints for querying metrics:

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

- 📈 Aggregation option:
  - `avg` (default), `min`, `max`, `sum`,
- 🕒 Precision options:
  - `sec`, `min`, `hour` (default), `day`

```http
GET fred/metrics/numerical?start=2025-06-11T10:30:00&end=2025-06-11T18:00:00&precision=min&agg=sum
```

---

### 3. `/metrics/categorical`
> Return all distinct categorical values in the range.

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
curl "http://localhost:8000/fred/metrics/all?start=2025-06-11T10:30:00&end=2025-06-11T18:00:00"
# Output:
[
  {
    "token_usage": {
      "completion_tokens": 7,
      "prompt_tokens": 32,
      "total_tokens": 39,
      "completion_tokens_details": {
        "accepted_prediction_tokens": 0,
        "rejected_prediction_tokens": 0,
        "reasoning_tokens": 0,
        "audio_tokens": 0,
        "cached_tokens": 0
      },
      "prompt_tokens_details": {
        "accepted_prediction_tokens": 0,
        "rejected_prediction_tokens": 0,
        "reasoning_tokens": 0,
        "audio_tokens": 0,
        "cached_tokens": 0
      }
    },
    "model_name": "gpt-4o-2024-11-20",
    "system_fingerprint": "fp_ee1d74bde0",
    "id": "chatcmpl-BhBlcfKmlNxKR5ltZvfUnDKr9DcTM",
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
    },
    "user_id": "unknown-user",
    "session_id": "unknown-session",
    "latency": 1.171,
    "timestamp": 1749633036.61935,
    "model_type": "DefaultModel"
  },...
]
```
```bash
# Input :
curl "http://localhost:8000/fred/metrics/numerical?start=2025-06-11T10:30:00&end=2025-06-11T18:00:00&precision=sec&agg=sum"
# Output:
[
  {
    "bucket": "2025-06-11 11:10:36",
    "latency": 1.171,
    "token_usage.total_tokens": 39,
    "token_usage.prompt_tokens": 32,
    "token_usage.completion_tokens": 7,
    "token_usage.completion_tokens_details.accepted_prediction_tokens": 0,
    "token_usage.completion_tokens_details.audio_tokens": 0,
    "token_usage.completion_tokens_details.reasoning_tokens": 0,
    "token_usage.completion_tokens_details.rejected_prediction_tokens": 0,
    "token_usage.prompt_tokens_details.audio_tokens": 0,
    "token_usage.prompt_tokens_details.cached_tokens": 0
  },
  {
    "bucket": "2025-06-11 11:10:38",
    "latency": 1.171,
    "token_usage.total_tokens": 39,
    "token_usage.prompt_tokens": 28,
    "token_usage.completion_tokens": 11,
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
curl "http://localhost:8000/fred/metrics/categorical?start=2025-06-11T10:30:00&end=2025-06-11T18:00:00"
# Output:
[
  {
    "timestamp": 1749633036.61935,
    "user_id": "unknown-user",
    "session_id": "unknown-session",
    "model_name": "gpt-4o-2024-11-20",
    "model_type": "DefaultModel",
    "finish_reason": "stop",
    "id": "chatcmpl-BhBlcfKmlNxKR5ltZvfUnDKr9DcTM",
    "system_fingerprint": "fp_ee1d74bde0",
    "service_tier": null
  },
  {
    "timestamp": 1749633038.06572,
    "user_id": "admin@mail.com",
    "session_id": "xltYsdRK5uY",
    "model_name": "gpt-4o-2024-11-20",
    "model_type": "DocumentsExpert",
    "finish_reason": "stop",
    "id": "chatcmpl-BhBlduskisak8wKTCPZBf3DrV01Fu",
    "system_fingerprint": "fp_ee1d74bde0",
    "service_tier": null
  },...
]
```

---

## 🧠 Components Overview

### 🔹 `MonitoredLanguageModel`

This is a universal wrapper for any `BaseLanguageModel` (LangChain-compatible) that automatically logs:

- Execution latency
- Model metadata (name/type)
- Token usage (if available)
- User/session context (via `LoggingContext`)

It transparently wraps sync/async methods like `invoke()`, `predict()`, `generate_prompt()`, etc. and logs structured data into a `MetricStore`.

> ✅ Safe to use inside LangChain agents, LangGraph flows, or app logic.

---

### 🔹 `MetricStore`

A lightweight **in-memory** metric store that supports:

- Adding metrics at runtime

---

### 🔹 `MetricStoreController`

That provides API endpoints to get the data from the current MetricStore
- Date range filtering
- Aggregating by time precision (e.g., minute, hour)
- Exporting metrics for dashboards or inspection

### 🔹 `LoggingContext`

A tiny utility using `contextvars` to inject `user_id` and `session_id` across async tasks. This avoids passing identifiers explicitly through every function.

**Usage:**
```python
set_logging_context(user_id="alice@example.com", session_id="xyz123")
ctx = get_logging_context()
print(ctx["user_id"])  # alice@example.com
```

This is automatically used by the `MonitoredLanguageModel` to enrich every log.

---

## 🧱 Folder Structure

```text
fred/
├── monitoring/
│   ├── logging_context.py       # Context-local user/session management
│   ├── metadata                 # Generic class to send and receive data
│   ├── metric_store.py          # MetricStore logic (in-memory + file)
│   ├── metric_store_controller.py            # FastAPI service exposing metrics initialize in fred/main.py
│   ├── monitored_language_model.py    # Wrapper for LangChain models

```

---
## 🔜 Possible Improvements

- Add filtering by `user_id`, `model_type`, or `session_id`
- Add a `/metrics/summary` for global stats (avg latency, token total, etc.)
- Export as CSV or Excel
- Add authentication for production use

---

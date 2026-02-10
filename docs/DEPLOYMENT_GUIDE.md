# Fred Deployment Guide

This guide provides a **single entry point** for teams deploying Fred beyond a local developer setup.

It is intended for:

- **DevOps / Platform engineers** in charge of provisioning infrastructure (Kubernetes, databases, OpenSearch, object storage, etc.).
- **Technical leads / architects** who need to understand the main moving parts and dependencies.

For day-to-day **developer onboarding**, refer to the main [`README.md`](../README.md).

---

# 1. Scope

This document focuses on **production-like deployments** where:

- Multiple users access Fred simultaneously.
- Data and documents must be persisted and backed up.
- External services (LLM providers, OpenSearch, object stores, IdP, etc.) are managed by a DevOps team.

It does **not** prescribe a specific orchestrator (Kubernetes, VMs, Docker Compose), but highlights the requirements that must be satisfied.

---

# 2. Fred Components to Deploy

Fred is composed of three main runtime components:

1. **Frontend UI** (`./frontend`)  
   - React single-page application (Vite dev server in dev, static assets in prod).
   - Talks to the agentic backend via HTTP(S) and WebSocket.

2. **Agentic backend** (`./agentic-backend`)  
   - FastAPI application.  
   - Hosts the multi-agent runtime (LangGraph + LangChain).  
   - Integrates with:
     - LLM providers (OpenAI, Azure OpenAI, Ollama, etc.).
     - Storage: **SQLite (dev/laptop default)** or **PostgreSQL (prod)**; OpenSearch is optional.

3. **Knowledge Flow backend** (`./knowledge-flow-backend`)  
   - FastAPI application focused on:
     - Document ingestion (PDF, DOCX, PPTX, CSV, etc.).
     - Chunking and vectorization.
     - Document search / retrieval APIs.
   - Integrates with:
     - LLM/embedding providers.
     - **Either** SQLite + ChromaDB (dev default) **or** PostgreSQL + pgvector (prod); OpenSearch is optional.
     - Optional object store (e.g., MinIO, S3) for raw documents.

In local dev, these run with **no external data services** (SQLite + ChromaDB embedded).  
In production, you typically deploy:

- Frontend as static assets served by a reverse proxy (NGINX, ingress, etc.).
- `agentic-backend` and `knowledge-flow-backend` as separate services (Kubernetes deployments, ECS services, etc.).
- A shared persistence stack: PostgreSQL/pgvector or OpenSearch, plus an object store if you need externalized files.

---

# 3. Environment Configuration

Each backend has two configuration layers:

1. **`.env` files**  
   - Secrets and environment-specific credentials:
     - API keys for OpenAI / Azure / Ollama.
     - Database credentials (PostgreSQL and/or OpenSearch).
     - Object store keys.
   - Never committed to Git.

2. **`configuration.yaml` files**  
   - Functional / structural configuration:
     - Model providers, model names, temperature, timeouts.
     - Feature flags (frontend behavior, optional agents).
     - Backend integration options (SQLite vs PostgreSQL, OpenSearch optional).

Files of interest:

- `agentic-backend/config/.env`
- `agentic-backend/config/configuration.yaml`
- `knowledge-flow-backend/config/.env`
- `knowledge-flow-backend/config/configuration.yaml`
- Password mapping to remember:
  - **Core Postgres (metadata/tags/vector, etc.)** → `storage.postgres` → `FRED_POSTGRES_PASSWORD` (or `password:` in YAML).
  - **Tabular Postgres (CSV ingestion/statistic)** → `storage.tabular_stores` → `TABULAR_POSTGRES_PASSWORD` (or `password:` in YAML; legacy fallback `SQL_PASSWORD`).
  - These two stores are independent; keep separate DB/users in production for least privilege.

For concrete examples of model configuration, see the main [`README.md`](../README.md#model-configuration).

---

# 4. External Dependencies Overview

In a production-like setup you will typically manage:

1. **LLM & Embedding Providers**
   - OpenAI / Azure OpenAI.
   - Ollama (self-hosted models).
   - Azure APIM fronting Azure OpenAI.
   - Requirements: stable network access, quotas, and API keys / credentials.

2. **Vector + metadata storage**
   - Dev default: **SQLite + ChromaDB** (embedded, zero external services).
   - Production: choose one:
     - **PostgreSQL + pgvector** (recommended, no OpenSearch dependency).
     - **OpenSearch** (only if your platform standardizes on OS/Lucene).  
       **Strict mapping and version requirements are enforced.** See [`DEPLOYMENT_GUIDE_OPENSEARCH.md`](./DEPLOYMENT_GUIDE_OPENSEARCH.md).
   - Both store document metadata and vectors; pick based on platform standards.

3. **Object Storage (optional but recommended)**
   - MinIO, S3, or equivalent.
   - Holds raw ingested documents (PDF, DOCX, PPTX, CSV…).
   - Knowledge Flow stores metadata and vectors in your chosen backend (PostgreSQL/pgvector or OpenSearch), and content in the object store.

4. **Identity Provider (optional)**
   - Keycloak or another OIDC provider.
   - Used to harden authentication and authorization in multi-user environments.
   - See `docs/KEYCLOAK.md` for details when enabled.

---

# 5. Production Settings

## 5.1 HTTP Clients for LLM Providers

This chapter explains how Fred configures **HTTP clients used to communicate with LLM and embedding providers** (OpenAI, Azure OpenAI, Azure APIM, Ollama), and how these settings should be tuned in **production environments**.

The goal is to ensure:

- Predictable latency and failure modes.
- Safe behavior under load (no hidden hangs).
- Efficient connection reuse.
- Consistent behavior across all model connectors.

---

### 5.1.1 OpenAIDesign Principles

Fred applies the following principles for HTTP communication with LLM providers:

1. **Single shared connection pool per backend process**
   - Each backend (`agentic-backend`, `knowledge-flow-backend`) creates **one shared HTTP client stack**.
   - All chat, embedding, and vision models reuse this pool.
   - This makes concurrency, resource usage, and failures observable and controllable.

2. **Explicit timeouts for all phases**
   - No implicit or library-default timeouts.
   - Separate budgets for:
     - Connection establishment
     - Reading responses
     - Writing requests
     - Waiting for a free connection from the pool

3. **YAML-driven configuration**
   - Operators configure networking behavior in `configuration.yaml`.
   - Secrets (API keys, tokens) remain in `.env` / Kubernetes Secrets.
   - No code changes are required to adjust networking behavior.

4. **Provider-agnostic behavior**
   - The same timeout and pooling concepts apply to:
     - OpenAI
     - Azure OpenAI
     - Azure APIM
     - Ollama (self-hosted)
   - Differences between providers are handled internally by Fred.

---

### 5.1.2 Where HTTP Client Configuration Lives

HTTP client settings are defined **per model** in `configuration.yaml`, under the `settings` section.

Example (OpenAI chat model):

```yaml
default_chat_model:
  provider: openai
  name: gpt-4o-mini
  settings:
    temperature: 0.0
    max_retries: 1
    timeout:
      connect: 10.0
      read: 120.0
      write: 30.0
      pool: 5.0
    http_client_limits:
      max_connections: 200
      max_keepalive_connections: 50
      keepalive_expiry_seconds: 10
```

Although the settings are declared per model, **the first model initialized defines the shared HTTP client pool** for the entire backend process.

Subsequent models reuse the same pool.

---

### 5.1.3 Timeout Configuration (Critical)

#### Why explicit timeouts matter

Without explicit timeouts, production systems can:
- Hang indefinitely on network issues.
- Exhaust worker threads under load.
- Become impossible to diagnose.

Fred uses **four distinct timeout phases**, mapped directly to the underlying HTTP client:

| Timeout key | Meaning |
|------------|--------|
| `connect` | Maximum time to establish a TCP/TLS connection |
| `read` | Maximum time waiting for response data |
| `write` | Maximum time to send the request |
| `pool` | Maximum time waiting for a free connection from the pool |

#### Recommended production defaults

```yaml
timeout:
  connect: 10.0
  read: 120.0
  write: 30.0
  pool: 5.0
```

## 5.2 KPIs and Metrics

- **Scraping endpoint:** Prometheus-format metrics are exposed by default on `http://<pod-ip>:9000/metrics` (override via `app.metrics_address` / `app.metrics_port` in YAML). Point Prometheus or `curl` there to scrape.
- **Key KPI names (agentic backend):**


- **Bench-mode logging (local tests):** For local load tests with `ws_bench`, enable verbose KPI summaries and process metrics via config, e.g.:
  ```yaml
  app:
    kpi_log_summary_interval_sec: 5    # >0 to enable; 0 to disable (default prod)
    kpi_log_summary_top_n: 20          # 0 to log all
    kpi_process_metrics_interval_sec: 10
  ```
  Keep these at 0 in production to avoid extra log volume; Kubernetes scraping covers runtime metrics.


##### Rationale
- **connect (10s)**: Handles cold DNS/TLS paths without blocking indefinitely.
- **read (120s)**: Allows long generations, tool calls, and large RAG responses.
- **write (30s)**: Prevents stalled uploads.
- **pool (5s)**: Ensures overload fails fast instead of silently queueing forever.

⚠️ Avoid using a single flat timeout like `request_timeout: 30` in production.  
It hides the root cause of failures and behaves poorly under concurrency.

---

### 5.1.4 Connection Pool Limits

Fred uses a **shared HTTP connection pool** to control concurrency and resource usage.

Configuration example:

```yaml
http_client_limits:
  max_connections: 200
  max_keepalive_connections: 50
  keepalive_expiry_seconds: 10
```

#### Meaning of each parameter

| Parameter | Description |
|---------|-------------|
| `max_connections` | Maximum concurrent HTTP connections |
| `max_keepalive_connections` | Maximum idle keep-alive connections |
| `keepalive_expiry_seconds` | Time before idle connections are closed |

#### Recommended values

| Scenario | max_connections | keepalive_connections |
|--------|-----------------|----------------------|
| Small deployment (1–2 replicas) | 50–100 | 10–20 |
| Medium deployment | 100–300 | 20–50 |
| High concurrency | 300–500 | 50–100 |

#### Notes

- **Keep-alives should generally be enabled** in production.
- Set `max_keepalive_connections: 0` **only** if you have a known issue with:
  - Reverse proxies
  - Azure APIM connection reuse
  - Load balancers that mishandle keep-alives

If you disable keep-alives, expect higher latency and CPU usage.

---

### 5.1.5 Retries and Failure Semantics

Fred supports `max_retries` at the model level:

```yaml
settings:
  max_retries: 0
```

#### Production recommendation

- **Default: `max_retries: 1`**
- Avoid high retry counts:
  - They amplify load during incidents.
  - They increase tail latency.
- Prefer **fast failure + retry at higher layers** (agent logic, UI retry).

Retries apply only to **transient network or provider errors**, not semantic failures.

---

### 5.1.6 Ollama (Self-Hosted Models)

For Ollama, Fred does **not** inject a shared HTTP client instance.  
Instead, it passes **timeout and limit values** directly to the Ollama client.

Example:

```yaml
chat_model:
  provider: ollama
  name: qwen2.5:3b-instruct
  settings:
    base_url: http://ollama:11434
    temperature: 0.0
    timeout:
      connect: 5.0
      read: 300.0
      write: 30.0
      pool: 5.0
```

#### Notes
- Ollama calls may require **longer read timeouts**, especially for larger local models.
- Connection limits are less critical for Ollama but still enforced for safety.

---

### 5.1.7 Operational Recommendations

- **Tune per environment**:
  - Dev: lower limits, shorter timeouts.
  - Prod: higher limits, explicit pool timeout.
- **Align with replica count**:
  - More replicas → lower `max_connections` per pod.
- **Monitor failures**:
  - Timeouts are expected failure modes; observe and tune, don’t eliminate them.
- **Document deviations**:
  - If you disable keep-alives or increase timeouts significantly, document why.

---

## 5.2 KPIs and Metrics

### 5.2.1 Overview

Fred is well equiped in KPIs and provides tools for developers and devops to stress and tune it on local laptop
as well as on deployed integration or production platforms. 

- **Scraping endpoint:** Prometheus-format metrics are exposed by default on `http://<pod-ip>:9000/metrics` (override via `app.metrics_address` / `app.metrics_port` in the YAML). Point Prometheus or `curl` there to scrape.
- **Key KPI names you’ll see:** `chat.exchange_latency_ms`, `chat.phase_latency_ms` (with `agent_step` dims such as `session_get_create`, `agent_init`, `history_restore`, `stream`, `persist`, `total`), `chat.user_message_total`, `agent.cache_*`, plus process gauges like `process.cpu.percent`, `process.memory.rss_mb`, `process.open_fds`.
- **Bench-mode logging:** For local load tests with `ws_bench`, you can enable verbose KPI summaries and process metrics via config, e.g.:
  ```yaml
  app:
    kpi_log_summary_interval_sec: 5    # >0 to enable; 0 to disable (default prod)
    kpi_log_summary_top_n: 20          # 0 to log all
    kpi_process_metrics_interval_sec: 10
  ```

  In production keep these at 0 to avoid extra log volume; Kubernetes scraping covers runtime metrics.

### 5.2.2 Agentic KPIs

| Metric name                     | Type     | Important dimensions                         | Meaning / usage                                                      |
|---------------------------------|----------|----------------------------------------------|----------------------------------------------------------------------|
| `chat.user_message_total`       | counter  | `actor_type`, `user_id`, `agent_id`          | Count of user messages ingested                                      |
| `chat.phase_latency_ms`         | gauge    | `agent_step`, `status`                       | Per-phase latency (steps like `session_get_create`, `agent_init`, `history_restore`, `stream`, `persist`, `total`) |
| `chat.exchange_latency_ms`      | timer    | `status`, `agent_id`, `session_id`           | End-to-end latency per exchange                                      |
| `chat.exchange_total`           | counter  | `status`, `agent_id`, `session_id`           | Count of exchanges                                                   |
| `agent.cache_lookup_total`      | counter  | `result` (hit/miss)                          | Cache lookups                                                        |
| `agent.cache_entries`           | gauge    | —                                            | Entries in agent cache                                               |
| `agent.cache_inflight_total`    | gauge    | —                                            | In-flight cache ops                                                  |
| `agent.cache_evictions_total`   | gauge    | —                                            | Cache evictions                                                      |
| `agent.cache_blocked_evictions_total` | gauge | —                                           | Blocked evictions                                                    |
| `process.cpu.percent`           | gauge    | `actor_type=system`                          | Process CPU percent                                                  |
| `process.memory.rss_mb`         | gauge    | `actor_type=system`                          | Resident memory in MB                                                |
| `process.memory.vms_mb`         | gauge    | `actor_type=system`                          | Virtual memory in MB                                                 |
| `process.memory.rss_percent`    | gauge    | `actor_type=system`                          | RSS as fraction of container limit                                   |
| `process.memory.limit_mb`       | gauge    | `actor_type=system`                          | Memory limit seen by process                                         |
| `process.open_fds`              | gauge    | `actor_type=system`                          | Open file descriptors                                                |


### 5.2.3 Knowledge-Flow KPIs

- **Scraping endpoint:** `http://<pod-ip>:9111/metrics` by default (see `app.metrics_port` in the knowledge-flow config).
- **Key KPI names (knowledge-flow backend):**

| Metric name                        | Type    | Important dimensions                      | Meaning / usage                                                   |
|------------------------------------|---------|-------------------------------------------|-------------------------------------------------------------------|
| `api.request_latency_ms`           | timer   | `route`, `method`, `status`               | API latency for ingestion endpoints                               |
| `ingestion.document_duration_ms`   | timer   | `file_type`, `status`, `source`           | Per-document end-to-end ingestion time                            |
| `rag.search_latency_ms`            | timer   | `index`, `user_id`, `agent_id` (dims vary)| Latency of RAG search                                             |
| `rag.search_total`                 | counter | `status` (implicit via dims)              | Count of RAG searches                                             |
| `rag.search_hits_total`            | counter | —                                         | Documents returned across searches                                |
| `rag.search_hit_ratio`             | gauge   | —                                         | Hit ratio for searches                                            |
| `rag.search_empty_total`           | counter | —                                         | Searches with no results                                          |
| `rag.search_error_total`           | counter | —                                         | Failed searches                                                   |
| `rag.search_top_k_total`           | counter | —                                         | Top-K docs retrieved                                              |
| `rag.rerank_latency_ms`            | timer   | —                                         | Latency of reranking step                                         |
| `rag.rerank_total`                 | counter | —                                         | Rerank operations                                                 |
| `rag.rerank_docs_total`            | counter | —                                         | Docs evaluated in rerank                                          |
| `rag.rerank_top_r_total`           | counter | —                                         | Docs selected after rerank                                        |

Bench-mode summary logging can also be enabled for knowledge-flow via the same `app` settings as above (use non-zero values in a bench YAML; keep 0 in production).


---

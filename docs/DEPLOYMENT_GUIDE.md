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
     - Optional OpenSearch cluster for metrics, logs, and future features.

3. **Knowledge Flow backend** (`./knowledge-flow-backend`)  
   - FastAPI application focused on:
     - Document ingestion (PDF, DOCX, PPTX, CSV, etc.).
     - Chunking and vectorization.
     - Document search / retrieval APIs.
   - Integrates with:
     - LLM/embedding providers.
     - **OpenSearch** for vector storage (recommended in production).
     - Optional object store (e.g., MinIO, S3) for raw documents.

In local dev, these can run with minimal external dependencies.  
In production, you typically deploy:

- Frontend as static assets served by a reverse proxy (NGINX, ingress, etc.).
- `agentic-backend` and `knowledge-flow-backend` as separate services (Kubernetes deployments, ECS services, etc.).
- A shared OpenSearch cluster and object store.

---

# 3. Environment Configuration

Each backend has two configuration layers:

1. **`.env` files**  
   - Secrets and environment-specific credentials:
     - API keys for OpenAI / Azure / Ollama.
     - OpenSearch credentials.
     - Object store keys.
   - Never committed to Git.

2. **`configuration.yaml` files**  
   - Functional / structural configuration:
     - Model providers, model names, temperature, timeouts.
     - Feature flags (frontend behavior, optional agents).
     - Backend integration options.

Files of interest:

- `agentic-backend/config/.env`
- `agentic-backend/config/configuration.yaml`
- `knowledge-flow-backend/config/.env`
- `knowledge-flow-backend/config/configuration.yaml`

For concrete examples of model configuration, see the main [`README.md`](../README.md#model-configuration).

---

# 4. External Dependencies Overview

In a production-like setup you will typically manage:

1. **LLM & Embedding Providers**
   - OpenAI / Azure OpenAI.
   - Ollama (self-hosted models).
   - Azure APIM fronting Azure OpenAI.
   - Requirements: stable network access, quotas, and API keys / credentials.

2. **OpenSearch (recommended for production vector storage)**
   - Used by the **Knowledge Flow backend** for:
     - Vector search (KNN) on document chunks.
     - Filtering by libraries/tags and other metadata.
   - **Strict mapping and version requirements are enforced by Fred.**  
     See: [`DEPLOYMENT_GUIDE_OPENSEARCH.md`](./DEPLOYMENT_GUIDE_OPENSEARCH.md).

3. **Object Storage (optional but recommended)**
   - MinIO, S3, or equivalent.
   - Holds raw ingested documents (PDF, DOCX, PPTX, CSV…).
   - Knowledge Flow stores metadata and vectors in OpenSearch, and content in the object store.

4. **Identity Provider (optional)**
   - Keycloak or another OIDC provider.
   - Used to harden authentication and authorization in multi-user environments.
   - See `docs/KEYCLOAK.md` for details when enabled.

---


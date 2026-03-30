# FEATURES

A quick, skimmable overview of what Fred offers — with links to deeper docs.

> **Who is this for?**  
> Engineers, data scientists, architects, and evaluators deciding whether Fred fits their use case.

---

## At a Glance

| Area | Highlights | Learn more                                                                                                                                                                                                                                                              |
|---|---|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Retrieval** | Hybrid (AI + keywords), Semantic (AI only), Strict (precision-first) | [Retrievers Quick Guide](../knowledge-flow-backend/docs/RETRIEVERS.md) · [Hybrid](../knowledge-flow-backend/docs/HYBRID_RETRIEVER.md) · [Semantic](../knowledge-flow-backend/docs/SEMANTIC_RETRIEVER.md) · [Strict](../knowledge-flow-backend/docs/STRICT_RETRIEVER.md) |
| **Agentic backend** | Multi-agent orchestration (FastAPI + LangGraph), tool use, policies | [Agentic design](../agentic-backend/docs/AGENTS.md)                                                                                                                                                                                                                     |
| **Knowledge flow** | Ingestion, chunking, embeddings, vector search | [Knowledge Flow README](../knowledge-flow-backend/README.md)                                                                                                                                                                                                            |
| **Auth & Security** | Keycloak/OIDC-ready, scoped search (by libraries/tags), safe defaults | [Keycloak](./docs/KEYCLOAK.md) · [Security](./docs/SECURITY.md)                                                                                                                                                                                                         |
| **Storage options** | Local FS + **SQLite + ChromaDB** by default; production: PostgreSQL/pgvector; optional OpenSearch + object store | [Design](./docs/DESIGN.md)                                                                                                                                                                                                                                              |
| **Licensing** | Apache 2.0; optional integrations configured externally | [License](./docs/LICENSE.md)                                                                                                                                                                                                                                            |
| **Roadmap** | What’s next & priorities | [ROADMAP](./docs/ROADMAP.md)                                                                                                                                                                                                                                            |

---

## Retrieval Modes (UI & API)

- **Hybrid (default)** — Best everyday choice. Balances **semantic understanding** with **exact tokens** (IDs, error codes). Gracefully falls back to Semantic if the backend lacks keyword/phrase indexing.  
  → Details: [Hybrid Retriever](../knowledge-flow-backend/docs/HYBRID_RETRIEVER.md)

- **Semantic** — AI-only; fastest; great for concept exploration and paraphrased questions.  
  → Details: [Semantic Retriever](../knowledge-flow-backend/docs/SEMANTIC_RETRIEVER.md)

- **Strict** — Precision-first. Requires both semantic and keyword agreement (optional exact phrase). May return zero results by design.  
  → Details: [Strict Retriever](../knowledge-flow-backend/docs/STRICT_RETRIEVER.md)

> Tip: Start with **Hybrid**. Need speed? Pick **Semantic**. Need high confidence with exact terms? Use **Strict**.

---

## Architecture Highlights

- **Modular by design** — swap vector stores, embedders, and text splitters without touching calling code.
- **Zero-infra defaults** — local filesystem + embedded vector store (Chroma) for quick starts.
- **Production-ready** — clear auth model, document scoping, and predictable APIs.
- **DX first** — local dev, dev-container, and VS Code workspace included.

See the big picture: [Design](./docs/DESIGN.md)

---

## Security & Identity

- OIDC/Keycloak integration out of the box.  
- Scoped retrieval (libraries/tags → document IDs) to prevent cross-library leakage.  
- Deployment-time hardening guidance.

Learn more: [Keycloak](./docs/KEYCLOAK.md) · [Security](./docs/SECURITY.md)

---

## Developer Experience

- **Local mode:** no external services required.  
- **Dev-Container:** one-click full stack (OpenSearch/MinIO optional).  
- **VS Code workspace:** per-folder interpreters; linting and IntelliSense ready.

Start here: [Getting started (README)](./README.md#getting-started) · [Developer Guide](../knowledge-flow-backend/docs/DEVELOPER_GUIDE.md)

---

## Roadmap & Contributing

- What’s next: [ROADMAP](./docs/ROADMAP.md)  
- How to help: [CONTRIBUTING](./docs/CONTRIBUTING.md) · [CODE OF CONDUCT](./docs/CODE_OF_CONDUCT.md)

---

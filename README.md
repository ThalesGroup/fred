# Fred

**Fred** is a multi-agent AI assistant that helps you manage and understand your Kubernetes applications.

It consists of:
- a **Python agentic backend** (FastAPI + LangGraph)
- a **React-based chatbot UI**
- an optional **Knowledge Flow backend** for document ingestion and vector search

Fred is not a framework, but a complete lab platform that demonstrates how to build practical multi-agent applications with LangChain and LangGraph. It turns specialized agents into a cooperative expert team, capable of answering technical, context-aware questions.

➡️ Learn more at **[fredk8.dev](https://fredk8.dev)**

---

## Local Developer Setup (recommended starting point)

Fred runs out of the box with **only one secret**: your OpenAI API key.

By default:

* 🚫 Keycloak is bypassed (a mock `admin/admin` user is injected)
* 💾 All data (metrics, conversations, uploads) is stored on the **local filesystem**
* 🧪 No external services required — perfect for hacking and learning

You can later plug in authentication, databases, and vector search using advanced configuration or the **[deployment repo](https://github.com/ThalesGroup/fred-deployment-factory)**.

---

### 1 · Prerequisites

| Tool   | Version  | Install hint                |
|--------|----------|-----------------------------|
| Python | 3.12.8   | `pyenv install 3.12.8`      |
| Node   | 22.13.0  | `nvm install 22.13.0`       |
| Make   | (any)    | Use your system package mgr |

---

### 2 · Clone & Build

```bash
git clone https://github.com/ThalesGroup/fred.git
cd fred
```

#### Backend (Python)

```bash
cd backend
make build        # uv handles the virtualenv
```

#### Frontend (React)

```bash
cd ../frontend
make build
```

---

### 3 · Provide your OpenAI key

```bash
echo "OPENAI_API_KEY=sk-..." > config/.env
```

---

### 4 · Run

```bash
# Terminal 1 – backend
export OPENAI_API_KEY=sk-...
cd backend && make run
```

```bash
# Terminal 2 – frontend
cd frontend && make run
```

Browse to <http://localhost:5173> and start chatting!

---

## Supported Model Providers

Fred can talk to several LLM providers out of the box:

| Provider      | How to enable                                    |
|---------------|--------------------------------------------------|
| **OpenAI** (default) | Set `OPENAI_API_KEY` in `config/.env` |
| **Azure OpenAI**     | Set `AZURE_OPENAI_API_KEY` and endpoint vars <br>Adjust `provider_settings` in **`backend/config/configuration.yaml`** |
| **Ollama** (local models) | Point `OLLAMA_BASE_URL` at your Ollama server and set the model in **`backend/config/configuration.yaml`** |

Open **`backend/config/configuration.yaml`** and scroll to the `ai:` section for concrete examples of each provider block.

---

## Configuration Philosophy

| File                        | Purpose                                                  |
|-----------------------------|----------------------------------------------------------|
| `config/.env`               | 🔐 Secrets only (API keys, passwords). Not committed.    |
| `config/configuration.yaml` | ⚙️ Functional settings (providers, agents, features). In Git. |

> `.env` is already in `.gitignore` — never commit credentials.

---

## System Architecture

| Component             | Location                         | Role                              |
|-----------------------|----------------------------------|-----------------------------------|
| **Frontend UI**       | [`/frontend`](./frontend)        | React chatbot interface           |
| **Agentic backend**   | [`/backend`](./backend)          | Multi-agent API server            |
| **Knowledge backend** | [`knowledge-flow`](https://github.com/ThalesGroup/knowledge-flow) | Optional: document ingestion & RAG |

The Knowledge Flow backend is **optional** until you need advanced retrieval-augmented generation.

---

## Advanced Integrations

After the local “hello-world” works, you can:

* **Activate Keycloak or any OIDC provider** for real auth
* **Store metrics and files in OpenSearch + MinIO**
* **Plug in the Knowledge Flow backend** for vector search and RAG

The **[fred-deployment-factory](https://github.com/ThalesGroup/fred-deployment-factory)** repo ships a ready-made Docker Compose that deploys Keycloak, OpenSearch, Postgres, and MinIO for you.

---

## 📚 Documentation

* [Official docs](https://fredk8.dev/docs)
* [Backend README](./backend/README.md)
* [Frontend README](./frontend/README.md)
* [Knowledge Flow backend](https://github.com/ThalesGroup/knowledge-flow)
* [Deployment repo](https://github.com/ThalesGroup/fred-deployment-factory)

---

## 🤝 Contributing

We welcome PRs and issues — see the [Contributing guide](./CONTRIBUTING.md).

---

## ⚖️ License

Apache 2.0 — see [LICENSE](./LICENSE).

---

## 📬 Contacts

- alban.capitant@thalesgroup.com  
- fabien.le-solliec@thalesgroup.com  
- florian.mueller@thalesgroup.com  
- simon.cariou@thalesgroup.com  
- dimitri.tombroff@thalesgroup.com

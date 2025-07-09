# Fred

Fred is both:
- An innovation lab — to help developers rapidly explore agentic patterns, domain-specific logic, and custom tools.
- A production-ready platform — already integrated with real enterprise constraints: auth, security, document lifecycle, and deployment best practices.

It is composed of:

* a **Python agentic backend** (FastAPI + LangGraph)  
* a **Python knowledge flow backend** (FastAPI) for document ingestion and vector search
* a **React frontend**  

Fred is not a framework, but a full reference implementation that shows how to build practical multi-agent applications with LangChain and LangGraph. Agents cooperate to answer technical, context-aware questions.

See the project site: <https://fredk8.dev>

---

## Local Developer Setup (recommended)

Fred works out of the box when you provide **one secret**—your OpenAI API key.  
Defaults:

* Keycloak is bypassed by a mock `admin/admin` user  
* All data (metrics, conversations, uploads) is stored on the local filesystem  
* No external services are required

Production services and databases can be added later or via the **deployment factory** repository.

### 1 · Prerequisites

| Tool   | Version | Install hint            |
|--------|---------|-------------------------|
| Python | 3.12.8  | `pyenv install 3.12.8`  |
| Node   | 22.13.0 | `nvm install 22.13.0`   |
| Make   | any     | install from your OS    |

### 2 · Clone & Build

```bash
git clone https://github.com/ThalesGroup/fred.git
cd fred
```

#### Agentic Backend

```bash
cd agentic_backend
make run            # uses uv for the virtualenv
```

#### Knowledge Flow Backend

```bash
cd knowledge_flow_backend
make run            # uses uv for the virtualenv
```

#### Frontend

```bash
cd ../frontend
make build
```

### 3 · Add your OpenAI key

```bash
echo "OPENAI_API_KEY=sk-..." > {agentic_backend,knowledge_flow_backend}/config/.env
```

### 4 · Run the services

```bash
# Terminal 1 – agentic backend
cd agentic_backend && make run
```

```bash
# Terminal 1 – knowledge flow backend
cd knowledge_flow_backend && make run
```

```bash
# Terminal 2 – frontend
cd frontend && make run
```

Open <http://localhost:5173> in your browser.

---

## Optional VS Code Dev-Container

If you prefer a fully containerised IDE with all dependencies running:

1. Install Docker, VS Code, and the *Dev Containers* extension.  
2. Create `~/.fred/openai-api-key.env` containing `OPENAI_API_KEY=sk-…`.  
3. In VS Code, press <kbd>F1</kbd> → **Dev Containers: Reopen in Container**.

The Dev Container starts the `devcontainer` service plus Postgres, OpenSearch, and MinIO. Ports 8000 (backend) and 5173 (frontend) are forwarded automatically.

Inside the container, start the servers:

```bash
# integrated terminal
cd backend && make run     # API
# new terminal
cd frontend && make run    # UI
```

---

## Supported Model Providers

| Provider               | How to enable                                                          |
|------------------------|------------------------------------------------------------------------|
| OpenAI (default)       | Add `OPENAI_API_KEY` to `config/.env`                                  |
| Azure OpenAI           | Add `AZURE_OPENAI_API_KEY` and endpoint variables; adjust `configuration.yaml` |
| Ollama (local models)  | Set `OLLAMA_BASE_URL` and model name in `configuration.yaml`           |

See `backend/config/configuration.yaml` (section `ai:`) for concrete examples.

---

## Configuration Files

| File                        | Purpose                                                    |
|-----------------------------|------------------------------------------------------------|
| `config/.env`               | Secrets (API keys, passwords). Not committed to Git.       |
| `config/configuration.yaml` | Functional settings (providers, agents, feature flags).    |

---

## System Architecture

| Component          | Location                           | Role                                |
|--------------------|------------------------------------|-------------------------------------|
| Frontend UI        | `./frontend`                       | React-based chatbot                 |
| Agentic backend    | `./backend`                        | Multi-agent API server              |
| Knowledge backend  | <https://github.com/ThalesGroup/knowledge-flow> | Optional document ingestion & RAG |

---

## Advanced Integrations

* Enable Keycloak or another OIDC provider for authentication  
* Persist metrics and files in OpenSearch and MinIO  
* Use the Knowledge Flow backend for retrieval-augmented generation  

See the **deployment factory**: <https://github.com/ThalesGroup/fred-deployment-factory>

---

## Documentation

* Web site: <https://fredk8.dev/docs>  
* [Backend README](./backend/README.md)  
* [Frontend README](./frontend/README.md)  
* [Developer Guide](docs/DEVELOPER_GUIDE.md)
* [Python Coding Guidelines](docs/PYTHON_CODING_GUIDELINES.md)
* [License](docs/LICENSE.md)
* [Security](docs/SECURITY.md)

---

## Contributing

We welcome pull requests and issues. Start with the [Contributing guide](./CONTRIBUTING.md).

---

## License

Apache 2.0 — see [LICENSE](./LICENSE)

---

## Contacts

- alban.capitant@thalesgroup.com
- fabien.le-solliec@thalesgroup.com
- florian.mueller@thalesgroup.com
- simon.cariou@thalesgroup.com 
- dimitri.tombroff@thalesgroup.com

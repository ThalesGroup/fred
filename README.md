# Fred

- [Fred](#fred)
  - [Core Architecture and Licensing Clarity](#core-architecture-and-licensing-clarity)
    - [Licensing Note](#licensing-note)
  - [Getting started](#getting-started)
    - [Local (Native) Mode](#local-native-mode)
      - [1 · Prerequisites](#1--prerequisites)
        - [Required](#required)
        - [Optional](#optional)
      - [2 · Clone](#2--clone)
      - [3 · Add your OpenAI key](#3--add-your-openai-key)
      - [4 · Run the services](#4--run-the-services)
      - [Advanced developer tips](#advanced-developer-tips)
        - [Prerequisites](#prerequisites)
    - [Dev-Container mode](#dev-container-mode)
  - [Advanced configuration](#advanced-configuration)
    - [Supported Model Providers](#supported-model-providers)
    - [Configuration Files](#configuration-files)
    - [System Architecture](#system-architecture)
    - [Advanced Integrations](#advanced-integrations)
  - [Documentation](#documentation)
  - [Contributing](#contributing)
  - [License](#license)
  - [Contacts](#contacts)


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

## Core Architecture and Licensing Clarity

The three components just described form the *entirety of the Fred platform*. They are self-contained and do not 
require any external dependencies such as MinIO, OpenSearch, or Weaviate.

Instead, Fred is designed with a modular architecture that allows optional integration with these technologies. By default, a minimal Fred deployment can use just the local filesystem for all storage needs.

### Licensing Note

Fred is released under the **Apache License 2.0**. It does *not embed or depend on any LGPLv3 or copyleft-licensed components. Optional integrations (like OpenSearch or Weaviate) are configured externally and do not contaminate Fred's licensing. 
This ensures maximum freedom and clarity for commercial and internal use.

In short: Fred is 100% Apache 2.0, and you stay in full control of any additional components.

---

## Getting started

Fred works out of the box when you provide **one secret** — your OpenAI API key.  
Defaults:

* Keycloak is bypassed by a mock `admin/admin` user  
* All data (metrics, conversations, uploads) is stored on the local filesystem  
* No external services are required

Production services and databases can be added later or via the **deployment factory** repository.

### Local (Native) Mode

#### 1 · Prerequisites

##### Required 

| Tool   | Version | Install hint                                                                                      |
| ------ | ------- | ------------------------------------------------------------------------------------------------- |
| Pyenv  | any     | [Pyenv installation instructions](https://github.com/pyenv/pyenv?tab=readme-ov-file#installation) |
| Python | 3.12.8  | `pyenv install 3.12.8`                                                                            |
| Node   | 22.13.0 | `nvm install 22.13.0`                                                                             |
| Make   | any     | install from your OS                                                                              |

##### Optional

| Tool   | Version | Install hint                                                           | Comment                     |
| ------ | ------- | ---------------------------------------------------------------------- | --------------------------- |
| Pandoc | 2.9.2.1 | [Pandoc installation instructions](https://pandoc.org/installing.html) | For docx document ingestion |

#### 2 · Clone

```bash
git clone https://github.com/ThalesGroup/fred.git
cd fred
```

#### 3 · Add your OpenAI key

```bash
echo "OPENAI_API_KEY=sk-..." > {agentic_backend,knowledge_flow_backend}/config/.env
```

#### 4 · Run the services

```bash
# Terminal 1 – agentic backend
cd agentic_backend && make run
```

```bash
# Terminal 2 – knowledge flow backend
cd knowledge_flow_backend && make run
```

```bash
# Terminal 3 – frontend
cd frontend && make run
```

Open <http://localhost:5173> in your browser.

#### Advanced developer tips

To get full VS Code Python support (linting, IntelliSense, debugging, etc.) across our repo, we provide:

1. A VS Code workspace file `fred.code-workspace` that loads all sub‑projects.
2. Per‑folder `.vscode/settings.json` files in each Python backend to pin the interpreter.

##### Prerequisites

- [Visual Studio Code](https://code.visualstudio.com/)  
- VS Code extensions:
  - **Python** (ms-python.python)  
  - **Pylance** (ms-python.vscode-pylance)  

1. Open the workspace

  After cloning the repo, you can open Fred's VS Code workspace with `code fred.code-workspace`

  When you open Fred's VS Code workspace, VS Code will load four folders:

  - ``fred`` – for any repo‑wide files, scripts, etc
  - ``agentic_backend`` – first Python backend
  - ``knowledge_flow_backend`` – second Python backend
  - ``fred-core`` - a common python library for both python backends
  - ``frontend`` – UI

2. Per‑folder Python interpreters

    Each backend ships its own virtual environment under .venv. We’ve added a per‑folder VS Code setting (see for instance ``agentic_backend/.vscode/settings.json``) to automatically pick it:

    This ensures that as soon as you open a Python file under agentic_backend/ (or knowledge_flow_backend/), VS Code will:
    
    - Activate that folder’s virtual environment
    - Provide linting, IntelliSense, formatting, and debugging using the correct Python

---

### Dev-Container mode

If you prefer a fully containerised IDE with all dependencies running:

1. Install Docker, VS Code (or an equivalent IDE that supports Dev Containers), and the *Dev Containers* extension.  
2. Create `~/.fred/openai-api-key.env` containing `OPENAI_API_KEY=sk-…`.  
3. In VS Code, press <kbd>F1</kbd> → **Dev Containers: Reopen in Container**.

The Dev Container starts the `devcontainer` service plus Postgres, OpenSearch, and MinIO. Ports 8000 (backend) and 5173 (frontend) are forwarded automatically.

Inside the container, start the servers:

```bash
# Terminal 1 – agentic backend
cd agentic_backend && make run
```

```bash
# Terminal 2 – knowledge flow backend
cd knowledge_flow_backend && make run
```

```bash
# Terminal 3 – frontend
cd frontend && make run
```

---

## Advanced configuration

### Supported Model Providers

| Provider              | How to enable                                                                  |
| --------------------- | ------------------------------------------------------------------------------ |
| OpenAI (default)      | Add `OPENAI_API_KEY` to `config/.env`                                          |
| Azure OpenAI          | Add `AZURE_OPENAI_API_KEY` and endpoint variables; adjust `configuration.yaml` |
| Ollama (local models) | Set `OLLAMA_BASE_URL` and model name in `configuration.yaml`                   |

See `agentic_backend/config/configuration.yaml` (section `ai:`) for concrete examples.

---

### Configuration Files

| File                                               | Purpose                                                 | Tip                                                                 |
| -------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------- |
| `agentic_backend/config/.env`                      | Secrets (API keys, passwords). Not committed to Git.    | Copy `.env.template` to `.env` and then fill in any missing values. |
| `knowledge_flow_backend/config/.env`               | Same as above                                           | Same as above                                                       |
| `agentic_backend/config/configuration.yaml`        | Functional settings (providers, agents, feature flags). | -                                                                   |
| `knowledge_flow_backend/config/configuration.yaml` | Same as above                                           | -                                                                   |

---

### System Architecture

| Component              | Location                   | Role                                                                  |
| ---------------------- | -------------------------- | --------------------------------------------------------------------- |
| Frontend UI            | `./frontend`               | React-based chatbot                                                   |
| Agentic backend        | `./agentic_backend`        | Multi-agent API server                                                |
| Knowledge Flow backend | `./knowledge_flow_backend` | **Optional** knowledge management component (document ingestion & Co) |

---

### Advanced Integrations

* Enable Keycloak or another OIDC provider for authentication  
* Persist metrics and files in OpenSearch and MinIO  

---

## Documentation

* Main docs: <https://fredk8.dev/docs>  
* [Agentic backend README](./agentic_backend/README.md)  
* [Agentic backend agentic design](./agentic_backend/docs/AGENTS.md)  
* [MCP](./agentic_backend/docs/MCP.md)
* [Frontend README](./frontend/README.md)  
* [Knowledge Flow backend README](./knowledge_flow_backend/README.md)
* [Keycloak](./docs/KEYCLOAK.md)
* [Developer Tools](./developer_tools/README.md)    
* [Code of Conduct](./docs/CODE_OF_CONDUCT.md) 
* [License](./docs/LICENSE.md)  
* [Security](./docs/SECURITY.md)  
* [Python Coding Guide](./docs/PYTHON_CODING_GUIDELINES.md)
* [Contributing](./docs/CONTRIBUTING.md)   

---

## Contributing

We welcome pull requests and issues. Start with the [Contributing guide](./CONTRIBUTING.md).

---

## License

Apache 2.0 — see [LICENSE](./LICENSE)

---
## Contacts

- alban.capitant@thalesgroup.com
- fabien.le-solliec@thalesgroup.com
- florian.muller@thalesgroup.com
- simon.cariou@thalesgroup.com
- dimitri.tombroff@thalesgroup.com

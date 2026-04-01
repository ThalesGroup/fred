# Fred

Before you even know what fred is about, there are two key references to know: 
- [Who does what](https://github.com/orgs/ThalesGroup/projects/8/views/4)
- [Fred deployment factory](https://github.com/fred-agent/fred-deployment-factory)


Fred is a production-ready platform for building and operating multi-agent AI applications. It is designed around two complementary goals:

- **A complete runtime platform** — auth, session management, document ingestion, team access control, observability, and Kubernetes-ready deployment, all integrated and ready to use.
- **A structured agent authoring SDK** — a constrained, typed authoring model (v2 SDK) that lets domain engineers write reliable agents without having to design a distributed runtime from scratch.

Fred is composed of four components:

- a **Python agentic backend** (`agentic-backend`) — multi-agent runtime, session orchestration, streaming, MCP tool integration
- a **Python knowledge flow backend** (`knowledge-flow-backend`) — document ingestion, vectorization, and retrieval
- a **Python control plane backend** (`control-plane-backend`) — team and user management, access policy, agent registry
- a **React frontend** (`frontend`) — chat interface and agent management UI

The repository also includes an [academy](./academy/README.md) with sample MCP servers and agents to get started quickly.

See the project site: <https://fredk8.dev>

Contents:

- [Getting started](#getting-started)
  - [Development environment setup](#development-environment-setup)
    - [Option 1 (recommended): Let the Dev Container do it for you!](#option-1-recommended-let-the-dev-container-do-it-for-you)
    - [Option 2: Native mode i.e. install everything locally](#option-2-native-mode-ie-install-everything-locally)
    - [Advanced developer tips](#advanced-developer-tips)
  - [Model configuration](#model-configuration)
  - [Start Fred components](#start-fred-components)
  - [Head for the Fred UI!](#head-for-the-fred-ui)
- [k3d Local Deployment](#k3d-local-deployment)
- [Production mode](#production-mode)
- [Agent authoring (v2 SDK)](#agent-authoring-v2-sdk)
- [Agent coding academy](#agent-coding-academy)
- [Advanced configuration](#advanced-configuration)
- [Core Architecture and Licensing Clarity](#core-architecture-and-licensing-clarity)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [Community](#community)
- [Contacts](#contacts)

## Getting started

To ensure a smooth first-time experience, Fred’s maintainers designed Dev Container/Native startup to require no additional external components (except, of course, to LLM APIs).

By default, using either Dev Container or native startup:

- Fred stores all data locally using **SQLite** for SQL/metadata and **ChromaDB** for vectors/embeddings. (DuckDB has been deprecated.) Data includes metrics, chat conversations, document uploads, and embeddings.
- Authentication and authorization are mocked.

> **Note:**  
> Accross all setup modes, a common requirement is to have access to Large Language Model (LLM) APIs via a model provider. Supported options include:
>
> - **Public OpenAI APIs:** Connect using your OpenAI API key.
> - **Private Ollama Server:** Host open-source models such as Mistral, Qwen, Gemma, and Phi locally or on a shared server.
> - **Private Azure AI Endpoints:** Connect using your Azure OpenAI key.
>
> Detailed instructions for configuring your chosen model provider are provided [below](#model-configuration).

### Development environment setup

Choose how you want to prepare Fred's development environment:

#### Option 1 (recommended): Let the Dev Container do it for you!

<details>
  <summary>Details</summary>

Prefer an isolated environment with everything pre-installed?

The Dev Container setup takes care of all dependencies related to agentic backend, knowledge-flow backend, and frontend components.

##### Prerequisites

| Tool                                                                | Purpose                             |
| ------------------------------------------------------------------- | ----------------------------------- |
| **Docker** / Docker Desktop                                         | Runs the container                  |
| **VS Code**                                                         | Primary IDE                         |
| **Dev Containers extension** (`ms-vscode-remote.remote-containers`) | Opens the repo inside the container |

##### Open the container

1. Clone (or open) the repository in VS Code.
2. Press <kbd>F1</kbd> → **Dev Containers: Reopen in Container**.

When the terminal prompt appears, the workspace is ready but you still need to run the different services with `make run` as specified in the [next section](#start-fred-components). Ports `8000` (Agentic backend), `8111` (Knowledge Flow backend), and `5173` (Frontend (vite)) are automatically forwarded to the host.

##### Rebuilds & troubleshooting

- Rebuild the container: <kbd>F1</kbd> → _Dev Containers: Rebuild Container_
- Dependencies feel stale? Delete the relevant `.venv` or `frontend/node_modules` inside the container, then rerun the associated `make` target.
- Need to change API keys or models? Update the backend `.env` files inside the container and restart the relevant service. See [Model configuration](#model-configuration) for more details.

</details>

#### Option 2: Native mode i.e. install everything locally

<details>
  <summary>Details</summary>

> Note: Note that this native mode only applies to Unix-based OS (e.g., Mac or Linux-related OS).

##### Prerequisites

<details>
  <summary>First, make sure you have all the requirements installed</summary>

| Tool         | Type                       | Version                                                                                             | Install hint                                                                                |
| ------------ | -------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Pyenv        | Python installer           | latest                                                                                              | [Pyenv installation instructions](https://github.com/pyenv/pyenv#installation)              |
| Python       | Programming language       | 3.12.8                                                                                              | Use `pyenv install 3.12.8`                                                                  |
| python3-venv | Python venv module/package | matching                                                                                            | Bundled with Python 3 on most systems; otherwise `apt install python3-venv` (Debian/Ubuntu) |
| nvm          | Node installer             | latest                                                                                              | [nvm installation instructions](https://github.com/nvm-sh/nvm#installing-and-updating)      |
| Node.js      | Programming language       | 22.13.0                                                                                             | Use `nvm install 22.13.0`                                                                   |
| Make         | Utility                    | system                                                                                              | Install via system package manager (e.g., `apt install make`, `brew install make`)          |
| yq           | Utility                    | system                                                                                              | Install via system package manager                                                          |
| SQLite       | Local RDBMS engine         | ≥ 3.35.0                                                                                            | Install via system package manager                                                          |
| Pandoc       | 2.9.2.1                    | [Pandoc installation instructions](https://pandoc.org/installing.html)                              | For DOCX document ingestion                                                                 |
| LibreOffice  | Headless doc converter     | [LibreOffice installation instructions](https://www.libreoffice.org/download/download-libreoffice/) | Required for PPTX vision enrichment (`pptx -> pdf`) via the `soffice` command                                                                |
| libmagic     | Identifies file types by content | Install via system package manager (e.g., `apt install libmagic1`, `brew install libmagic`)         | To check file type                                                                          |

  <details>
    <summary>Dependency details</summary>

```mermaid
graph TD
    subgraph FredComponents["Fred Components"]
      style FredComponents fill:#b0e57c,stroke:#333,stroke-width:2px  %% Green Color
        Agentic["agentic-backend"]
        Knowledge["knowledge-flow-backend"]
        Frontend["frontend"]
    end

    subgraph ExternalDependencies["External Dependencies"]
      style ExternalDependencies fill:#74a3d9,stroke:#333,stroke-width:2px  %% Blue Color
        Venv["python3-venv"]
        Python["Python 3.12.8"]
        SQLite["SQLite"]
        Pandoc["Pandoc"]
        libmagic["libmagic"]
        Pyenv["Pyenv (Python installer)"]
        Node["Node 22.13.0"]
        NVM["nvm (Node installer)"]
    end

    subgraph Utilities["Utilities"]
      style Utilities fill:#f9d5e5,stroke:#333,stroke-width:2px  %% Pink Color
        Make["Make utility"]
        Yq["yq (YAML processor)"]
    end

    Agentic -->|depends on| Python
    Agentic -->|depends on| Knowledge
    Agentic -->|depends on| Venv

    Knowledge -->|depends on| Python
    Knowledge -->|depends on| Venv
    Knowledge -->|depends on| Pandoc
    Knowledge -->|depends on| SQLite
    Knowledge -->|depends on| libmagic

    Frontend -->|depends on| Node

    Python -->|depends on| Pyenv

    Node -->|depends on| NVM

```

  </details>

</details>

##### Clone the repo

```bash
git clone https://github.com/ThalesGroup/fred.git
cd fred
```
> Note: the PPTX vision enrichment path in `knowledge-flow-backend` requires LibreOffice to be installed locally and the `soffice` command to be available in `PATH`. On Debian/Ubuntu, this can be installed with `apt install libreoffice`.

</details>

#### Advanced developer tips

> Prerequisites:
>
> - [Visual Studio Code](https://code.visualstudio.com/)
> - VS Code extensions:
>   - **Python** (ms-python.python)
>   - **Pylance** (ms-python.vscode-pylance)

To get full VS Code Python support (linting, IntelliSense, debugging, etc.) across our repo, we provide:

<details>
  <summary>1. A VS Code workspace file `fred.code-workspace` that loads all sub‑projects.</summary>

After cloning the repo, you can open Fred's VS Code workspace with `code .vscode/fred.code-workspace`

When you open Fred's VS Code workspace, VS Code will load four folders:

- `fred` – for any repo‑wide files, scripts, etc
- `agentic-backend` – first Python backend
- `knowledge-flow-backend` – second Python backend
- `fred-core` - a common python library for both python backends
- `frontend` – UI
</details>

<details>
  <summary>2. Per‑folder `.vscode/settings.json` files in each Python backend to pin the interpreter.</summary>

Each backend ships its own virtual environment under .venv. We’ve added a per‑folder VS Code setting (see for instance `agentic_backend/.vscode/settings.json`) to automatically pick it:

This ensures that as soon as you open a Python file under agentic_backend/ (or knowledge_flow_backend/), VS Code will:

- Activate that folder’s virtual environment
- Provide linting, IntelliSense, formatting, and debugging using the correct Python
</details>

### Model configuration

#### Model configuration (Agentic Backend)

Model configuration for the agentic backend lives in **`agentic-backend/config/models_catalog.yaml`**. This file is separate from `configuration.yaml` and owns the full model setup: named profiles, provider settings, shared HTTP client limits, and routing rules.

**Profiles** are named model configurations. Each profile declares a provider, a model name, and optional settings (temperature, timeouts, retries). Profiles are referenced by `profile_id`.

**Defaults** declare which profile to use per capability when no rule matches:

```yaml
default_profile_by_capability:
  chat: default.chat.openai.prod
  language: default.language.openai.prod
```

**Routing rules** allow policy-based model selection based on team, agent, or operation context. Rules are evaluated in order; the first match wins:

```yaml
rules:
  - rule_id: team-a-uses-ollama
    capability: chat
    team_id: team-a
    operation: routing
    target_profile_id: chat.ollama.mistral

  - rule_id: graph-g1-json-validation
    capability: chat
    agent_id: internal.graph.g1
    operation: json_validation_fc
    target_profile_id: chat.azure_apim.gpt4o
```

This makes it possible to route different teams, agents, or operation types to different models — including mixing providers — without changing any agent code.

For details on all supported match criteria (`team_id`, `agent_id`, `user_id`, `operation`, `purpose`) see [`docs/platform/LLM_ROUTING_FRED.md`](./docs/platform/LLM_ROUTING_FRED.md).

#### Set it up according to your development environment

No matter which development environment you choose, both backends rely on `.env` files for secrets and `configuration.yaml` / `models_catalog.yaml` for settings:

- Agentic backend: `agentic-backend/config/.env`, `configuration.yaml`, and `models_catalog.yaml`
- Knowledge Flow backend: `knowledge-flow-backend/config/.env` and `configuration.yaml`

1. **Copy the templates (skip if they already exist).**

   ```bash
   cp agentic-backend/config/.env.template agentic-backend/config/.env
   cp knowledge-flow-backend/config/.env.template knowledge-flow-backend/config/.env
   ```

2. **Edit the `.env` files** to set the API keys, base URLs, and deployment names that match your model provider.

3. **Update each backend’s `configuration.yaml`** so the `provider`, `name`, and optional settings align with the same provider. Use the recipes below as a starting point.

<details>
  <summary>OpenAI</summary>

> **Note:** Out of the box, Fred is configured to use OpenAI public APIs with the following models:
>
> - agentic backend: chat model `gpt-4o`
> - knowledge flow backend: chat model `gpt-4o-mini` and embedding model `text-embedding-3-large`
>
> If you plan to use Fred with these OpenAI models, you don't have to perform the `yq` commands below—just make sure the `.env` files contain your key.

- agentic backend configuration

  - Chat model

    ```bash
    yq eval '.ai.default_chat_model.provider = "openai"' -i agentic-backend/config/configuration.yaml
    yq eval '.ai.default_chat_model.name = "<your-openai-model-name>"' -i agentic-backend/config/configuration.yaml
    yq eval 'del(.ai.default_chat_model.settings)' -i agentic-backend/config/configuration.yaml
    ```

- knowledge flow backend configuration

  - Chat model

    ```bash
    yq eval '.chat_model.provider = "openai"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.chat_model.name = "<your-openai-model-name>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval 'del(.chat_model.settings)' -i knowledge-flow-backend/config/configuration.yaml
    ```

  - Embedding model

    ```bash
    yq eval '.embedding_model.provider = "openai"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.embedding_model.name = "<your-openai-model-name>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval 'del(.embedding_model.settings)' -i knowledge-flow-backend/config/configuration.yaml
    ```

- Copy-paste your `OPENAI_API_KEY` value in both `.env` files.

  > ⚠️ An `OPENAI_API_KEY` from a free OpenAI account unfortunately does not work.

</details>

<details>
  <summary>Azure OpenAI</summary>

- agentic backend configuration

  - Chat model

    ```bash
    yq eval '.ai.default_chat_model.provider = "azure-openai"' -i agentic-backend/config/configuration.yaml
    yq eval '.ai.default_chat_model.name = "<your-azure-openai-deployment-name>"' -i agentic-backend/config/configuration.yaml
    yq eval 'del(.ai.default_chat_model.settings)' -i agentic-backend/config/configuration.yaml
    yq eval '.ai.default_chat_model.settings.azure_endpoint = "<your-azure-openai-endpoint>"' -i agentic-backend/config/configuration.yaml
    yq eval '.ai.default_chat_model.settings.azure_openai_api_version = "<your-azure-openai-api-version>"' -i agentic-backend/config/configuration.yaml
    ```

- knowledge flow backend configuration

  - Chat model

    ```bash
    yq eval '.chat_model.provider = "azure-openai"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.chat_model.name = "<your-azure-openai-deployment-name>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval 'del(.chat_model.settings)' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.chat_model.settings.azure_endpoint = "<your-azure-openai-endpoint>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.chat_model.settings.azure_openai_api_version = "<your-azure-openai-api-version>"' -i knowledge-flow-backend/config/configuration.yaml
    ```

  - Embedding model

    ```bash
    yq eval '.embedding_model.provider = "azure-openai"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.embedding_model.name = "<your-azure-openai-deployment-name>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval 'del(.embedding_model.settings)' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.embedding_model.settings.azure_endpoint = "<your-azure-openai-endpoint>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.embedding_model.settings.azure_openai_api_version = "<your-azure-openai-api-version>"' -i knowledge-flow-backend/config/configuration.yaml
    ```

  - Vision model

    ```bash
    yq eval '.vision_model.provider = "azure-openai"' -i knowledge_flow_backend/config/configuration.yaml
    yq eval '.vision_model.name = "<your-azure-openai-deployment-name>"' -i knowledge_flow_backend/config/configuration.yaml
    yq eval 'del(.vision_model.settings)' -i knowledge_flow_backend/config/configuration.yaml
    yq eval '.vision_model.settings.azure_endpoint = "<your-azure-openai-endpoint>"' -i knowledge_flow_backend/config/configuration.yaml
    yq eval '.vision_model.settings.azure_openai_api_version = "<your-azure-openai-api-version>"' -i knowledge_flow_backend/config/configuration.yaml
    ```

- Copy-paste your `AZURE_OPENAI_API_KEY` value in both `.env` files.

</details>

<details>
  <summary>Ollama</summary>

- agentic backend configuration

  - Chat model

    ```bash
    yq eval '.ai.default_chat_model.provider = "ollama"' -i agentic-backend/config/configuration.yaml
    yq eval '.ai.default_chat_model.name = "<your-ollama-model-name>"' -i agentic-backend/config/configuration.yaml
    yq eval 'del(.ai.default_chat_model.settings)' -i agentic-backend/config/configuration.yaml
    yq eval '.ai.default_chat_model.settings.base_url = "<your-ollama-endpoint>"' -i agentic-backend/config/configuration.yaml
    ```

- knowledge flow backend configuration

  - Chat model

    ```bash
    yq eval '.chat_model.provider = "ollama"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.chat_model.name = "<your-ollama-model-name>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval 'del(.chat_model.settings)' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.chat_model.settings.base_url = "<your-ollama-endpoint>"' -i knowledge-flow-backend/config/configuration.yaml
    ```

  - Embedding model

    ```bash
    yq eval '.embedding_model.provider = "ollama"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.embedding_model.name = "<your-ollama-model-name>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval 'del(.embedding_model.settings)' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.embedding_model.settings.base_url = "<your-ollama-endpoint>"' -i knowledge-flow-backend/config/configuration.yaml
    ```

</details>

<details>
  <summary>Azure OpenAI via Azure APIM</summary>

- agentic backend configuration

  - Chat model

    ```bash
    yq eval '.ai.default_chat_model.provider = "azure-apim"' -i agentic-backend/config/configuration.yaml
    yq eval '.ai.default_chat_model.name = "<your-azure-openai-deployment-name>"' -i agentic-backend/config/configuration.yaml
    yq eval 'del(.ai.default_chat_model.settings)' -i agentic-backend/config/configuration.yaml
    yq eval '.ai.default_chat_model.settings.azure_ad_client_id = "<your-azure-apim-client-id>"' -i agentic-backend/config/configuration.yaml
    yq eval '.ai.default_chat_model.settings.azure_ad_client_scope = "<your-azure-apim-client-scope>"' -i agentic-backend/config/configuration.yaml
    yq eval '.ai.default_chat_model.settings.azure_apim_base_url = "<your-azure-apim-endpoint>"' -i agentic-backend/config/configuration.yaml
    yq eval '.ai.default_chat_model.settings.azure_apim_resource_path = "<your-azure-apim-resource-path>"' -i agentic-backend/config/configuration.yaml
    yq eval '.ai.default_chat_model.settings.azure_openai_api_version = "<your-azure-openai-api-version>"' -i agentic-backend/config/configuration.yaml
    yq eval '.ai.default_chat_model.settings.azure_tenant_id = "<your-azure-tenant-id>"' -i agentic-backend/config/configuration.yaml
    ```

- knowledge flow backend configuration

  - Chat model

    ```bash
    yq eval '.chat_model.provider = "azure-apim"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.chat_model.name = "<your-azure-openai-deployment-name>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval 'del(.chat_model.settings)' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.chat_model.settings.azure_ad_client_id = "<your-azure-apim-client-id>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.chat_model.settings.azure_ad_client_scope = "<your-azure-apim-client-scope>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.chat_model.settings.azure_apim_base_url = "<your-azure-apim-endpoint>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.chat_model.settings.azure_apim_resource_path = "<your-azure-apim-resource-path>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.chat_model.settings.azure_openai_api_version = "<your-azure-openai-api-version>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.chat_model.settings.azure_tenant_id = "<your-azure-tenant-id>"' -i knowledge-flow-backend/config/configuration.yaml
    ```

  - Embedding model

    ```bash
    yq eval '.embedding_model.provider = "azure-apim"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.embedding_model.name = "<your-azure-openai-deployment-name>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval 'del(.embedding_model.settings)' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.embedding_model.settings.azure_ad_client_id = "<your-azure-apim-client-id>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.embedding_model.settings.azure_ad_client_scope = "<your-azure-apim-client-scope>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.embedding_model.settings.azure_apim_base_url = "<your-azure-apim-endpoint>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.embedding_model.settings.azure_apim_resource_path = "<your-azure-apim-resource-path>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.embedding_model.settings.azure_openai_api_version = "<your-azure-openai-api-version>"' -i knowledge-flow-backend/config/configuration.yaml
    yq eval '.embedding_model.settings.azure_tenant_id = "<your-azure-tenant-id>"' -i knowledge-flow-backend/config/configuration.yaml
    ```

- Copy-paste your `AZURE_AD_CLIENT_SECRET` and `AZURE_APIM_SUBSCRIPTION_KEY` values in both `.env` files.

</details>

### Start Fred components

```bash
# standalone mode (single-process backend: control-plane + agentic + knowledge-flow)
make run-app
```

```bash
# split APIs mode (agentic:8000, knowledge-flow:8111, control-plane:8222)
make run-multi
```

```bash
# default command (alias of `run-app`)
make run
```

```bash
# backward-compatible alias
make run-app-multi
```

```bash
# split APIs mode + all Temporal workers (requires Temporal running)
make run-multi-workers
```

Run a single backend API from repository root:

```bash
make run-control-plane
make run-agentic
make run-knowledge-flow
```

Or run each component from its own folder:

```bash
# knowledge-flow backend
cd knowledge-flow-backend && make run
```

```bash
# agentic backend
cd agentic-backend && make run
```

```bash
# control-plane backend
cd control-plane-backend && make run
```

```bash
# frontend
cd frontend && make run
```

### Head for the Fred UI!

Open <http://localhost:5173> in your browser.

## k3d Local Deployment

Fred can be deployed locally into a [k3d](https://k3d.io) Kubernetes cluster using Helm. This mode mirrors a production-like setup while keeping everything on your machine.

### Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| **Docker** | Container runtime | [docs](https://docs.docker.com/get-docker/) |
| **k3d** | Local Kubernetes clusters | `curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh \| bash` |
| **Helm** | Kubernetes package manager | [docs](https://helm.sh/docs/intro/install/) |
| **kubectl** | Kubernetes CLI | [docs](https://kubernetes.io/docs/tasks/tools/) |

You also need the infrastructure stack deployed via the [fred-deployment-factory](https://github.com/ThalesGroup/fred-deployment-factory) repository. Follow its README to run `make k3d-up`.

### Host Configuration

> [!IMPORTANT]
> You **must** add `keycloak` to your `/etc/hosts` file so your browser can reach the Keycloak server running inside k3d:
>
> ```
> 127.0.0.1 localhost keycloak
> ```
>
> Without this entry, authentication will not work because the browser cannot resolve the `keycloak` hostname.

### Deploying

```bash
# 1. Set your OpenAI API key in the values file
#    Edit deploy/local/k3d/values-local.yaml and fill OPENAI_API_KEY

# 2. Build, import images into k3d, and deploy via Helm (all-in-one)
make k3d-deploy
```

### Makefile Targets

| Target | Description |
|--------|-------------|
| `make k3d-build` | Build Docker images for all services (agentic-backend, knowledge-flow-backend, frontend) |
| `make k3d-import` | Import built images into the k3d cluster |
| `make k3d-deploy` | All-in-one: build + import + deploy |
| `make k3d-deploy-only` | Deploy/upgrade the Helm chart only (images must already be imported) |
| `make k3d-undeploy` | Uninstall the Helm release |
| `make k3d-status` | Show pod and service status in the `fred` namespace |
| `make k3d-logs-agentic` | Tail logs for the agentic-backend |
| `make k3d-logs-kf` | Tail logs for the knowledge-flow-backend |
| `make k3d-logs-frontend` | Tail logs for the frontend |

### Accessing the Application

Once deployed, open <http://localhost:8088> in your browser. The Traefik Ingress routes all traffic through a single port:

| Path | Service |
|------|---------|
| `/` | Frontend |
| `/agentic/*` | Agentic backend |
| `/knowledge-flow/*` | Knowledge Flow backend |
| `/realms/*` | Keycloak (authentication) |

Other infrastructure services remain accessible on their usual ports:

| Service | URL |
|---------|-----|
| Keycloak | <http://keycloak:8080> |
| Temporal UI | <http://localhost:8233> |
| MinIO Console | <http://localhost:9001> |
| OpenSearch Dashboards | <http://localhost:5601> |

## Production mode

> [!IMPORTANT]
> **Access-control reminder (shared environments):**
> Keycloak app roles and team ReBAC rights are different controls.
> For the Fred access model and deployment bootstrap rules, see [`docs/platform/REBAC.md`](./docs/platform/REBAC.md).

For production deployments (Kubernetes, VMs, on-prem or cloud), refer to:

- [`docs/platform/DEPLOYMENT_GUIDE.md`](./docs/platform/DEPLOYMENT_GUIDE.md) – high-level deployment guide (components, configuration, external dependencies).
- [`docs/platform/DEPLOYMENT_GUIDE_OPENSEARCH.md`](./docs/platform/DEPLOYMENT_GUIDE_OPENSEARCH.md) – OpenSearch-specific requirements. Use this only if you choose OpenSearch over the new PostgreSQL/pgvector option.
- [`docs/platform/REBAC.md`](./docs/platform/REBAC.md) – high-level access model (RBAC/ReBAC/organization/bootstrap).

The rest of this `README.md` focuses on local developer setup and model configuration.

## Agent authoring (v2 SDK)

Fred includes a structured agent authoring SDK designed for domain engineers and platform teams who need to write reliable, testable agents without re-implementing execution infrastructure.

The v2 SDK provides two authoring styles:

- **ReAct / profile agents** — for focused, tool-driven agents with a small state surface. Declare a role, a tool set, and a few instructions. The SDK owns the execution loop.
- **Graph agents** — for multi-step business workflows with explicit state, conditional routing, and human-in-the-loop confirmation gates. The business flow is expressed as a typed graph; the SDK handles streaming, checkpointing, and HITL interrupts.

Both styles support MCP tool integration and run on the same runtime.

Start with the [agent authoring guide (v2)](./docs/authoring/AGENTS.md). For the design philosophy behind the SDK, see [SDK V2 positioning](./docs/authoring/SDK-V2-POSITIONING.md).

## Agent coding academy

The [academy](./academy/README.md) contains sample MCP servers and standalone applications to experiment with agent development outside the main platform. The [academy agents](./agentic-backend/agentic_backend/academy/ACADEMY.md) provide ready-to-run agent examples inside the agentic backend.

## Advanced configuration

### System Architecture

| Component              | Location                    | Role                                                                 |
| ---------------------- | --------------------------- | -------------------------------------------------------------------- |
| Frontend UI            | `./frontend`                | React chat interface and agent management UI                         |
| Agentic backend        | `./agentic-backend`         | Multi-agent runtime, session orchestration, streaming, MCP tools     |
| Knowledge Flow backend | `./knowledge-flow-backend`  | Document ingestion, vectorization, and retrieval                     |
| Control Plane backend  | `./control-plane-backend`   | Team and user management, access policy, agent registry              |

### Configuration Files

| File                                                | Purpose                                                 | Tip                                                                 |
| --------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------- |
| `agentic-backend/config/.env`                       | Secrets (API keys, passwords). Not committed to Git.    | Copy `.env.template` to `.env` and fill in any missing values.      |
| `knowledge-flow-backend/config/.env`                | Same as above                                           | Same as above                                                       |
| `control-plane-backend/config/.env`                 | Same as above                                           | Same as above                                                       |
| `agentic-backend/config/configuration.yaml`         | Functional settings (providers, agents, feature flags). | -                                                                   |
| `knowledge-flow-backend/config/configuration.yaml`  | Same as above                                           | -                                                                   |
| `control-plane-backend/config/configuration.yaml`   | Team/user policy settings.                              | -                                                                   |

### Supported Model Providers

| Provider                    | How to enable                                                                                                |
| --------------------------- | ------------------------------------------------------------------------------------------------------------ |
| OpenAI (default)            | Add `OPENAI_API_KEY` to `config/.env`; Adjust `configuration.yaml`                                           |
| Azure OpenAI                | Add `AZURE_OPENAI_API_KEY` to `config/.env`; Adjust `configuration.yaml`                                     |
| Azure OpenAI via Azure APIM | Add `AZURE_APIM_SUBSCRIPTION_KEY` and `AZURE_AD_CLIENT_SECRET` to `config/.env`; Adjust `configuration.yaml` |
| Ollama (local models)       | Adjust `configuration.yaml`                                                                                  |

See `agentic-backend/config/configuration.yaml` (section `ai:`) and `knowledge-flow-backend/config/configuration.yaml` (sections `chat_model:` and `embedding_model:`) for concrete examples.

### Advanced Integrations

- Enable Keycloak or another OIDC provider for authentication
- Persistence options:
  - **Laptop / dev (default):** SQLite for metadata + ChromaDB for vectors (embedded, no external services)
  - **Production:** PostgreSQL + pgvector for metadata/vectors, and optionally MinIO/S3 + OpenSearch if you prefer that stack

## Core Architecture and Licensing Clarity

The four components described above form the _entirety of the Fred platform_. By default they run self-contained on a laptop using **SQLite + ChromaDB** (no external services).

Fred is modular: you can optionally add Keycloak/OpenFGA, MinIO/S3, OpenSearch, and PostgreSQL/pgvector for production-grade persistence.

Persistence options:

- **Dev/laptop (default):** SQLite for all SQL stores, ChromaDB for vectors, local filesystem for blobs.
- **Production (recommended):** PostgreSQL + pgvector for SQL + vectors; optionally pair with MinIO/S3 + OpenSearch if you prefer that stack.

## Documentation

- Generic information

  - [Main docs](https://fredk8.dev/docs)
  - [Features overview](./docs/platform/FEATURES.md)

- Agentic backend

  - [Agentic backend README](./agentic-backend/README.md)
  - [Agentic Architecture](./agentic-backend/docs/RUNTIME_ARCHITECTURE.md)
  - [Agentic backend agentic design](./agentic-backend/docs/AGENTS.md)
  - [MCP capabilities for agent](./agentic-backend/docs/MCP.md)

- Agent authoring (v2 SDK)

  - [Agent authoring guide (v2)](./docs/authoring/AGENTS.md)
  - [SDK V2 positioning — design philosophy](./docs/authoring/SDK-V2-POSITIONING.md)
  - [V2 agent creation — React vs Graph](./docs/platform/V2_AGENT_CREATION.md)

- Architecture RFCs

  - [SDK V2 for industrial-grade agents](./docs/rfc/SDK-V2-RFC.md)
  - [Distributed agent architecture](./docs/rfc/DISTRIBUTED-AGENT-ARCHITECTURE-RFC.md)

- Knowledge Flow backend

  - [Knowledge Flow backend README](./knowledge_flow_backend/README.md)

- Frontend

  - [Frontend README](./frontend/README.md)

- Security-related topics

  - [Security overview](./docs/platform/SECURITY.md)
  - [Keycloak](./docs/platform/KEYCLOAK.md)

- Developer and contributors guides

  - [Developer Contract (humans + AI)](./docs/platform/DEVELOPER_CONTRACT.md)
  - [Platform Runtime Map (API apps + Temporal apps)](./docs/platform/PLATFORM_RUNTIME_MAP.md)
  - [Developer Tools](./developer_tools/README.md)
  - [Code of Conduct](./docs/CODE_OF_CONDUCT.md)
  - [Python Coding Guide](./docs/platform/PYTHON_CODING_GUIDELINES.md)
  - [Contributing](./docs/CONTRIBUTING.md)

### Licensing Note

Fred is released under the **Apache License 2.0**. It does \*not embed or depend on any LGPLv3 or copyleft-licensed components. Optional integrations (like OpenSearch or Weaviate) are configured externally and do not contaminate Fred's licensing.
This ensures maximum freedom and clarity for commercial and internal use.

In short: Fred is 100% Apache 2.0, and you stay in full control of any additional components.

See the [LICENSE](LICENSE.md) for more details.

## Contributing

We welcome pull requests and issues. Start with the [Contributing guide](./CONTRIBUTING.md).

## Community

Join the discussion on our [Discord server](https://discord.gg/F6qh4Bnk)!

[![Join our Discord](https://img.shields.io/badge/chat-on%20Discord-7289da?logo=discord&logoColor=white)](https://discord.gg/F6qh4Bnk)

## Contacts

- <alban.capitant@thalesgroup.com>
- <fabien.le-solliec@thalesgroup.com>
- <florian.muller@thalesgroup.com>
- <simon.cariou@thalesgroup.com>
- <dimitri.tombroff@thalesgroup.com>

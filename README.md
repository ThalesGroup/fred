# Fred

Fred is both:

- An innovation lab — to help developers rapidly explore agentic patterns, domain-specific logic, and custom tools.
- A production-ready platform — already integrated with real enterprise constraints: auth, security, document lifecycle, and deployment best practices.

It is composed of:

- a **Python agentic backend** (FastAPI + LangGraph)  
- a **Python knowledge flow backend** (FastAPI) for document ingestion and vector search
- a **React frontend**  

Fred is not a framework, but a full reference implementation that shows how to build practical multi-agent applications with LangChain and LangGraph. Agents cooperate to answer technical, context-aware questions.

See the project site: <https://fredk8.dev>

Contents: 

  - [Getting started](#getting-started)
    - [Local (Native) Mode](#local-native-mode)
    - [Dev-Container mode](#dev-container-mode)
    - [Production mode](#production-mode)
  - [Advanced configuration](#advanced-configuration)
  - [Documentation](#documentation)
  - [Core Architecture and Licensing Clarity](#core-architecture-and-licensing-clarity)
  - [Contributing](#contributing)
  - [Community](#community)
  - [Contacts](#contacts)


## Getting started

In order to ensure a smooth and simple first good experience for newcomers, Fred's maintainers make sure that no external services are necessary to begin. 

This means, that by default, Fred stores all data on the local filesystem or through local-first tools like DuckDB for SQL-like data and ChromaDB for local embeddings. Data here means for instance metrics, chat conversations, document uploads, and embeddings.

> **Note:**   
> The only external requirement to utilize Fred's capabilities is access to Large Language Model (LLM) APIs via a model provider. Here are available options:
> 
> - **Public OpenAI APIs:** Connect using your OpenAI API key.
> - **Private Ollama Server:** Host open-source models such as Mistral, Qwen, Gemma, and Phi on your own or a shared server.
> - **Private Azure AI Endpoints:** Connect using your Azure OpenAI key.
> 
> Detailed instructions for configuring your selected model provider will be provided in the following sections.

### Local (Native) Mode

<details>
  <summary>First, make sure you have all these dependencies in place before moving on</summary> 

- Required 

  | Tool         | Type                       | Version  | Install hint                                                                                   |
  | ------------ | -------------------------- | -------- | ---------------------------------------------------------------------------------------------- |
  | Pyenv        | Python installer           | latest   | [Pyenv installation instructions](https://github.com/pyenv/pyenv#installation)                 |
  | Python       | Programming Language       | 3.12.8   | Use `pyenv install 3.12.8`                                                                     |
  | python3-venv | Python venv module/package | matching | Already bundled with Python 3 on most systems; else `apt install python3-venv` (Debian/Ubuntu) |
  | nvm          | Node installer             | latest   | [nvm installation instructions](https://github.com/nvm-sh/nvm#installing-and-updating)         |
  | Node.js      | Programming Language       | 22.13.0  | Use `nvm install 22.13.0`                                                                      |
  | Make         | Utility                    | system   | Install via system package manager (e.g. `apt install make`, `brew install make`)              |
  | yq           | Utility                    | system   | Install via system package manager                                                             |

  <details>
    <summary>Dependency details</summary>

    Here are some details about the dependencies' relationships:

    ```mermaid
    graph TD
        subgraph FredComponents["Fred Components"]
          style FredComponents fill:#b0e57c,stroke:#333,stroke-width:2px  %% Green Color
            Agentic["agentic_backend"]
            Knowledge["knowledge_flow_backend"]
            Frontend["frontend"]
        end

        subgraph ExternalDependencies["External Dependencies"]
          style ExternalDependencies fill:#74a3d9,stroke:#333,stroke-width:2px  %% Blue Color
            Python["Python 3.12.8"]
            Venv["python3-venv"]
            Node["Node 22.13.0"]
            Pyenv["Pyenv (Python installer)"]
            NVM["nvm (Node installer)"]
            OS["Operating System"]
        end

        subgraph Utilities["Utilities"]
          style Utilities fill:#f9d5e5,stroke:#333,stroke-width:2px  %% Pink Color
            Make["Make utility"]
            Yq["yq (YAML processor)"]
        end

        Agentic -->|depends on| Python
        Agentic -->|depends on| Venv

        Knowledge -->|depends on| Python
        Knowledge -->|depends on| Venv

        Frontend -->|depends on| Node

        Python -->|depends on| Pyenv
        Venv -->|depends on| OS

        Node -->|depends on| NVM

        Pyenv -->|depends on| OS
        NVM -->|depends on| OS
        Make -->|depends on| OS
        
        Yq -->|depends on| OS

    ```
  </details>

- Optional

  | Tool   | Version | Install hint                                                           | Comment                     |
  | ------ | ------- | ---------------------------------------------------------------------- | --------------------------- |
  | Pandoc | 2.9.2.1 | [Pandoc installation instructions](https://pandoc.org/installing.html) | For docx document ingestion |

</details>

#### Clone

```bash
git clone https://github.com/ThalesGroup/fred.git
cd fred
```

#### Setup your model provider

First, copy the 2 dotenv files templates:

```bash
# Copy the 2 environment files templates
cp agentic_backend/config/.env.template agentic_backend/config/.env
cp knowledge_flow_backend/config/.env.template knowledge_flow_backend/config/.env
```

Then, depending on your model provider, actions may differ. 

<details>
  <summary>OpenAI</summary>

  - Set the model provider in the configuration files.
    
    ```bash
    yq eval '.ai.default_chat_model.provider = "openai"' -i agentic_backend/config/configuration.yaml
    yq eval '.chat_model.provider = "openai"' -i knowledge_flow_backend/config/configuration.yaml
    yq eval '.embedding_model.provider = "openai"' -i knowledge_flow_backend/config/configuration.yaml
    ```

  - Copy-paste your `OPENAI_API_KEY` value in the 2 files:

    - `agentic_backend/config/.env`
    - `knowledge_flow_backend/config/.env`

    > Warning: ⚠️ An `OPENAI_API_KEY` from a free OpenAI account unfortunately does not work.

</details>

<details>
  <summary>Azure OpenAI</summary>

  - Set your model provider in the configuration files.
    
    ```bash
    yq eval '.ai.default_chat_model.provider = "azure-openai"' -i agentic_backend/config/configuration.yaml
    yq eval '.chat_model.provider = "azure-openai"' -i knowledge_flow_backend/config/configuration.yaml
    yq eval '.embedding_model.provider = "azure-openai"' -i knowledge_flow_backend/config/configuration.yaml

  - Copy-paste your `AZURE_OPENAI_API_KEY` value in the 2 files:

    - `agentic_backend/config/.env`
    - `knowledge_flow_backend/config/.env`

</details>

#### Run the services

```bash
# Terminal 1 – knowledge flow backend
cd knowledge_flow_backend && make run
```

```bash
# Terminal 2 – agentic backend
cd agentic_backend && make run
```

```bash
# Terminal 3 – frontend
cd frontend && make run
```

Open <http://localhost:5173> in your browser.

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

  After cloning the repo, you can open Fred's VS Code workspace with `code fred.code-workspace`

  When you open Fred's VS Code workspace, VS Code will load four folders:

  - ``fred`` – for any repo‑wide files, scripts, etc
  - ``agentic_backend`` – first Python backend
  - ``knowledge_flow_backend`` – second Python backend
  - ``fred-core`` - a common python library for both python backends
  - ``frontend`` – UI
</details>

<details>
  <summary>2. Per‑folder `.vscode/settings.json` files in each Python backend to pin the interpreter.</summary>

  Each backend ships its own virtual environment under .venv. We’ve added a per‑folder VS Code setting (see for instance ``agentic_backend/.vscode/settings.json``) to automatically pick it:

  This ensures that as soon as you open a Python file under agentic_backend/ (or knowledge_flow_backend/), VS Code will:

  - Activate that folder’s virtual environment
  - Provide linting, IntelliSense, formatting, and debugging using the correct Python
</details>

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

### Production mode

For production mode, please reach out to your DevOps team so that they tune Fred configuration to match your needs. See [this section](#advanced-configuration) on advanced configuration.

## Advanced configuration

### Supported Model Providers

| Provider              | How to enable                                                                  |
| --------------------- | ------------------------------------------------------------------------------ |
| OpenAI (default)      | Add `OPENAI_API_KEY` to `config/.env`                                          |
| Azure OpenAI          | Add `AZURE_OPENAI_API_KEY` and endpoint variables; adjust `configuration.yaml` |
| Ollama (local models) | Set `OLLAMA_BASE_URL` and model name in `configuration.yaml`                   |

See `agentic_backend/config/configuration.yaml` (section `ai:`) for concrete examples.

### Configuration Files

| File                                               | Purpose                                                 | Tip                                                                 |
| -------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------- |
| `agentic_backend/config/.env`                      | Secrets (API keys, passwords). Not committed to Git.    | Copy `.env.template` to `.env` and then fill in any missing values. |
| `knowledge_flow_backend/config/.env`               | Same as above                                           | Same as above                                                       |
| `agentic_backend/config/configuration.yaml`        | Functional settings (providers, agents, feature flags). | -                                                                   |
| `knowledge_flow_backend/config/configuration.yaml` | Same as above                                           | -                                                                   |

### System Architecture

| Component              | Location                   | Role                                                                  |
| ---------------------- | -------------------------- | --------------------------------------------------------------------- |
| Frontend UI            | `./frontend`               | React-based chatbot                                                   |
| Agentic backend        | `./agentic_backend`        | Multi-agent API server                                                |
| Knowledge Flow backend | `./knowledge_flow_backend` | **Optional** knowledge management component (document ingestion & Co) |

### Advanced Integrations

- Enable Keycloak or another OIDC provider for authentication  
- Persist metrics and files in OpenSearch and MinIO  

## Documentation

- Main docs: <https://fredk8.dev/docs>  
- [Features overview](./docs/FEATURES.md)  ← start here if you’re evaluating Fred
- [Agentic backend README](./agentic_backend/README.md)  
- [Agentic backend agentic design](./agentic_backend/docs/AGENTS.md)  
- [MCP](./agentic_backend/docs/MCP.md)
- [Frontend README](./frontend/README.md)  
- [Knowledge Flow backend README](./knowledge_flow_backend/README.md)
- [Keycloak](./docs/KEYCLOAK.md)
- [Developer Tools](./developer_tools/README.md)
- [Code of Conduct](./docs/CODE_OF_CONDUCT.md)
- [Security](./docs/SECURITY.md)  
- [Python Coding Guide](./docs/PYTHON_CODING_GUIDELINES.md)
- [Contributing](./docs/CONTRIBUTING.md)


## Core Architecture and Licensing Clarity

The three components just described form the *entirety of the Fred platform*. They are self-contained and do not
require any external dependencies such as MinIO, OpenSearch, or Weaviate.

Instead, Fred is designed with a modular architecture that allows optional integration with these technologies. By default, a minimal Fred deployment can use just the local filesystem for all storage needs.

### Licensing Note

Fred is released under the **Apache License 2.0**. It does *not embed or depend on any LGPLv3 or copyleft-licensed components. Optional integrations (like OpenSearch or Weaviate) are configured externally and do not contaminate Fred's licensing.
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

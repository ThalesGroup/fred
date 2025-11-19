# Fred Agentic Backend

Fred is a flexible agentic backend that makes it easy to build, compose, and operate expert agents — including multi-agent systems with a planning **leader** agent.

It provides:

- ⚙️ A powerful runtime to orchestrate **domain-specific experts** and **leaders**
- 🧠 Built-in support for OpenAI, Azure, Ollama, and other LLM providers
- 🧪 Local development defaults for quick experimentation
- 🔌 Optional integration with external backends (MCP servers, OpenSearch, MinIO, etc.)

---

## 🚀 Getting Started

You can spin up the backend in seconds:

```bash
make run
```

This will:
- Start the API server (FastAPI)
- Use default in-memory and local storage components
- Let you interact with agents right away — no external dependencies required

---

## Configure Your LLM Provider (Required)

To use Fred, you must configure an LLM provider in `configuration.yaml` and `.env`. The logic is simple: 
in '.env' file you provide only sensitive access keys and tokens. ALl the rest is in the yaml file. 

Fred supports:

- ✅ **OpenAI**
- ✅ **Azure OpenAI**
- ✅ **Azure via API Management (APIM)**
- ✅ **Ollama** (for local models like `llama2`, `mistral`, etc.)

See [LLM Configuration](#configuring-freds-ai-model-provider) below for details.

---

## Optional External Backends

Fred is modular — it can integrate with:

- 🟤 **MCP servers** (for code execution, monitoring, document search, etc.)
- 🔍 **OpenSearch** (for persistent vector storage)
- 🪣 **MinIO** (for storing feedbacks, files)
- ☁️ **Cloud storage** (via the `context_storage` and `dao` configs)

These are optional. By default, Fred uses local file-based cache.

You can plug in real backends incrementally, agent by agent.

---

## 🎓 Fred Academy (Agent Examples)

If you want to learn how to build agents in Fred, start with the **Academy** samples:

- [`agentic_backend/academy/ACADEMY.md`](agentic_backend/academy/ACADEMY.md) – overview of all training steps
- Each step has its own folder and (for most) a local README:
  - `agentic_backend/academy/00-echo/README.md` – minimal echo agent
  - `agentic_backend/academy/01-llm-responder/README.md` – simple LLM responder
  - `agentic_backend/academy/02-dual-model-responder/README.md` – router/generator pattern
  - `agentic_backend/academy/03_asset_responder/README.md` – agents working with assets
  - `agentic_backend/academy/04_slide_maker/README.md` – slide/outline generator
  - `agentic_backend/academy/05_gps_agent/README.md` – basic geo/GPS agent
  - `agentic_backend/academy/06_simple_leader/README.md` – simple leader/orchestrator
  - `agentic_backend/academy/07_travel_agent/README.md` – OpenStreetMap travel agent
  - `agentic_backend/academy/08_ecoadviser/README.md` – eco‑advisor using open data

On GitHub, these links are clickable and let readers drill down from the top‑level README to any sample.

---

## Configuring Fred's AI Model Provider

Fred supports multiple AI model providers through a flexible YAML configuration and environment-based secret management.

You can choose between:

- ✅ **OpenAI** (e.g., `gpt-4o`, `gpt-3.5-turbo`)
- ✅ **Azure OpenAI** (with your own Azure deployment)
- ✅ **Azure via API Management (APIM)** (for enterprise environments using gateways)

### 📁 Step 1: Edit `configuration.yaml`

Inside the `ai.default_model` section, choose your provider.

#### 🔹 Option 1: OpenAI
```yaml
ai:
  default_model:
    provider: "openai"
    name: "gpt-4o"
    settings:
      temperature: 0.0
      max_retries: 2
      request_timeout: 30
```

#### 🔹 Option 2: Azure OpenAI
```yaml
ai:
  default_model:
    provider: "azure-openai"
    name: "fred-gpt-4o"  # your Azure deployment name
    settings:
      api_version: "2024-05-01-preview"
      temperature: 0.0
      request_timeout: 30
      max_retries: 2
```

#### 🔹 Option 3: Azure OpenAI via APIM
```yaml
ai:
  default_model:
    provider: "azure-openai"
    name: "fred-gpt-4o"
    settings:
      api_version: "2024-05-01-preview"
      temperature: 0.0
      request_timeout: 30
      max_retries: 2
      azure_endpoint: "https://your-company-api.azure-api.net"
```

### 🔐 Step 2: Set Required Environment Variables in `.env`

#### ✅ For OpenAI:
```env
OPENAI_API_KEY=sk-...
```

#### ✅ For Azure OpenAI:
```env
AZURE_OPENAI_API_KEY=...
```

Optional for Azure AD authentication:
```env
AZURE_TENANT_ID=...
AZURE_AD_CLIENT_ID=...
AZURE_AD_CLIENT_SECRET=...
```

#### ✅ For Azure APIM (if used):
```env
AZURE_APIM_SUBSCRIPTION_KEY=your-subscription-key
```

---

## Developer Tips

- Agents can be enabled/disabled in `configuration.yaml` under `ai.agents`
- Each agent can specify its own model and MCP server config
- The leader agent coordinates other experts when enabled
- Logs are verbose by default to help with debugging

---

## Local Setup Only?

Yes — everything works out of the box on a developer laptop. You can later plug in production storage or APIs.

---

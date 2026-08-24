# Model Configuration Summary

This document is the central summary for model configuration across:

- `apps/fred-agents` (and any third-party agent pod built with `fred-runtime`)
- `knowledge-flow-backend`

## Source Of Truth

The two surfaces configure models differently.

- **Agent pods** (`apps/fred-agents`, or your own pod)
  - Model routing comes from `apps/fred-agents/config/models_catalog.yaml`
  - The catalog can be overridden with the `FRED_MODELS_CATALOG_FILE` environment variable
  - The production routing surface currently publishes `chat` profiles only

- **Knowledge Flow backend**
  - Models are configured directly in `knowledge-flow-backend/config/configuration*.yaml`
  - Main keys:
    - `chat_model`
    - `embedding_model`
    - `vision_model`

Detailed examples are centralized in:

- `apps/fred-agents/config/models_catalog.yaml`
- `apps/fred-agents/config/configuration_prod.yaml`
- `knowledge-flow-backend/config/configuration_prod.yaml`

## Agent Pod Model Catalog

### Catalog Shape

Agent pods use a catalog-first model routing file (`models_catalog.yaml`) with this structure:

- `version`
- `common_model_settings`
- `common_model_settings_by_capability`
- `default_profile_by_capability`
- `profiles`
- `agent_profile_overrides`

The strict loader lives in:

- `libs/fred-runtime/fred_runtime/model_routing/catalog.py`

Important behavior:

- `default_profile_by_capability.chat` selects the pod's chat fallback
- each `profile` contains one `ModelConfiguration`
- `common_model_settings` are merged into profile settings
- `agent_profile_overrides` optionally maps an `agent_id` to a chat profile
- team policy is configured in control-plane, not in this file

### Minimal Catalog Example

```yaml
version: v1

common_model_settings:
  max_retries: 0
  temperature: 0.0

default_profile_by_capability:
  chat: default.chat.mistral

profiles:
  - profile_id: default.chat.mistral
    capability: chat
    model:
      provider: openai
      name: mistral-medium-latest
      settings:
        base_url: https://api.mistral.ai/v1

agent_profile_overrides:
  my.expensive.agent: default.chat.mistral
```

Profile ids are opaque identifiers: use readable names, but do not rely on a
`chat.` prefix for behavior. The declared `capability: chat` is authoritative.
Do not duplicate chat profiles as `language` profiles; `language` has no active
first-party routing consumer.

## Knowledge Flow Backend

### Where To Configure

Knowledge Flow still configures models directly in `configuration*.yaml`:

```yaml
chat_model:
  provider: openai
  name: gpt-4o-mini
  settings:
    temperature: 0
    max_retries: 0

embedding_model:
  provider: vertex-ai-model-garden
  name: publishers/baai/models/bge-m3
  settings:
    project: your-gcp-project-id
    location: europe-west1

vision_model:
  provider: vertex-ai
  name: gemini-2.5-flash
  settings:
    project: your-gcp-project-id
    location: europe-west1
```

## Minimal Examples

### Agent Pod Profiles (`models_catalog.yaml`)

OpenAI chat profile:

```yaml
- profile_id: chat.openai.gpt5
  capability: chat
  model:
    provider: openai
    name: gpt-5
    settings: {}
```

OpenAI-compatible Mistral profile:

```yaml
- profile_id: chat.mistral.medium
  capability: chat
  model:
    provider: openai
    name: mistral-medium-latest
    settings:
      base_url: https://api.mistral.ai/v1
```

Azure APIM chat profile:

```yaml
- profile_id: chat.azure-apim.gpt4o
  capability: chat
  model:
    provider: azure-apim
    name: gpt-4o
    settings:
      azure_apim_base_url: https://trustnest.azure-api.net
      azure_apim_resource_path: /genai-aoai-inference/v2
      azure_openai_api_version: 2024-06-01
      azure_tenant_id: ${AZURE_TENANT_ID}
      azure_ad_client_id: ${AZURE_AD_CLIENT_ID}
      azure_ad_client_scope: ${AZURE_AD_CLIENT_SCOPE}
```

Ollama chat profile:

```yaml
- profile_id: chat.ollama.mistral
  capability: chat
  model:
    provider: ollama
    name: mistral:latest
    settings:
      base_url: http://host.docker.internal:11434
```

Vertex AI Model Garden chat profile:

```yaml
- profile_id: chat.vertex.mistral-small
  capability: chat
  model:
    provider: vertex-ai-model-garden
    name: mistral-small-3.1-24b-instruct-2503
    settings:
      model_family: mistral
      project: your-gcp-project-id
      location: europe-west1
      request_timeout: 90
```

### Knowledge Flow Models (`configuration*.yaml`)

OpenAI chat + embeddings + vision:

```yaml
chat_model:
  provider: openai
  name: gpt-4o-mini
  settings:
    temperature: 0

embedding_model:
  provider: openai
  name: text-embedding-3-large
  settings: {}

vision_model:
  provider: openai
  name: gpt-4o-mini
  settings:
    temperature: 0
```

Ollama chat + embeddings:

```yaml
chat_model:
  provider: ollama
  name: qwen2.5:3b-instruct
  settings:
    base_url: http://localhost:11434
    temperature: 0.7

embedding_model:
  provider: ollama
  name: nomic-embed-text
  settings:
    base_url: http://localhost:11434
```

Azure OpenAI chat + embeddings:

```yaml
chat_model:
  provider: azure-openai
  name: your-chat-deployment
  settings:
    azure_endpoint: https://<your-azure-openai>.openai.azure.com
    azure_openai_api_version: 2024-06-01

embedding_model:
  provider: azure-openai
  name: your-embedding-deployment
  settings:
    azure_endpoint: https://<your-azure-openai>.openai.azure.com
    azure_openai_api_version: 2024-06-01
```

Vertex AI Gemini chat + embeddings + vision:

```yaml
chat_model:
  provider: vertex-ai
  name: gemini-2.5-flash
  settings:
    project: your-gcp-project-id
    location: europe-west1
    temperature: 0
    request_timeout: 90

embedding_model:
  provider: vertex-ai
  name: text-embedding-005
  settings:
    project: your-gcp-project-id
    location: europe-west1

vision_model:
  provider: vertex-ai
  name: gemini-2.5-flash
  settings:
    project: your-gcp-project-id
    location: europe-west1
    temperature: 0
```

Vertex AI Model Garden embeddings with BGE M3:

```yaml
embedding_model:
  provider: vertex-ai-model-garden
  name: publishers/baai/models/bge-m3
  settings:
    project: your-gcp-project-id
    location: europe-west1
```

Vertex AI Model Garden embeddings with BGE Large:

```yaml
embedding_model:
  provider: vertex-ai-model-garden
  name: publishers/baai/models/bge-large-en-v1.5
  settings:
    project: your-gcp-project-id
    location: europe-west1
```

Vertex AI Model Garden embeddings with Qwen:

```yaml
embedding_model:
  provider: vertex-ai-model-garden
  name: publishers/qwen/models/qwen3-embedding-0.6b
  settings:
    project: your-gcp-project-id
    location: europe-west1
```

## Supported Providers

Provider support implemented in `fred-core/fred_core/model/factory.py`:

| Provider                 | Chat | Embeddings | Vision                    |
| ------------------------ | ---- | ---------- | ------------------------- |
| `openai`                 | yes  | yes        | yes                       |
| `azure-openai`           | yes  | yes        | yes                       |
| `azure-apim`             | yes  | yes        | yes                       |
| `ollama`                 | yes  | yes        | yes (if multimodal model) |
| `vertex-ai`              | yes  | yes        | yes                       |
| `vertex-ai-model-garden` | yes  | yes        | no                        |

## Required Settings By Provider

- `openai`
  - No required YAML setting.
  - Required secret in env: `OPENAI_API_KEY`.

- `azure-openai`
  - Required YAML settings:
    - `azure_endpoint`
    - `azure_openai_api_version`
  - Required secret in env: `AZURE_OPENAI_API_KEY`.

- `azure-apim`
  - Required YAML settings:
    - `azure_ad_client_id`
    - `azure_ad_client_scope`
    - `azure_apim_base_url`
    - `azure_apim_resource_path`
    - `azure_openai_api_version`
    - `azure_tenant_id`
  - Required secrets in env:
    - `AZURE_APIM_SUBSCRIPTION_KEY`
    - `AZURE_AD_CLIENT_SECRET`

- `ollama`
  - Common YAML setting:
    - `base_url` (example: `http://localhost:11434`)

- `vertex-ai` (Gemini/GenAI)
  - Required YAML settings:
    - `project`
    - `location`
  - Auth:
    - local/dev: `GOOGLE_APPLICATION_CREDENTIALS`
    - on GCP: ADC attached to runtime (no key file required)

- `vertex-ai-model-garden`
  - Chat required YAML settings:
    - `project`
    - `location`
    - `model_family` (`mistral`, `llama`, `anthropic`)
  - Embeddings required YAML settings:
    - `project`
    - `location`
  - Embeddings naming:
    - set `name` to the full Vertex model path, for example `publishers/baai/models/bge-m3`
    - embeddings do not use `model_family`
  - Typical auth: same as `vertex-ai` (ADC)

## Notes

- Keep secrets in `.env`, not in YAML.
- For agent pods (`apps/fred-agents` or your own pod), use `models_catalog.yaml` as the source of truth.
- For `knowledge-flow-backend`, keep using `chat_model` / `embedding_model` / `vision_model` in the runtime config files.
- Knowledge Flow's `embedding_model` is direct service configuration. It is
  not selected by the current agent chat-routing policy.
- Use environment-specific files only for active runtime values and deployment-specific overrides.

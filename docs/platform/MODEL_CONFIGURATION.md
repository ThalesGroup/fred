# Model Configuration Summary

This document is the central summary for model configuration across:

- `agentic-backend`
- `knowledge-flow-backend`

Detailed commented examples are centralized in:

- `agentic-backend/config/configuration_prod.yaml`
- `knowledge-flow-backend/config/configuration_prod.yaml`

## Where To Configure

Agentic backend (`agentic-backend/config/*.yaml`):

- `ai.default_chat_model`
- `ai.default_language_model`

Knowledge Flow backend (`knowledge-flow-backend/config/*.yaml`):

- `chat_model`
- `embedding_model`
- `vision_model`

## Supported Providers

Provider support implemented in `fred-core/fred_core/model/factory.py`:

| Provider | Chat/Language | Embeddings | Vision |
| --- | --- | --- | --- |
| `openai` | yes | yes | yes |
| `azure-openai` | yes | yes | yes |
| `azure-apim` | yes | yes | yes |
| `ollama` | yes | yes | yes (if multimodal model) |
| `vertex-ai` | yes | yes | yes |
| `vertex-ai-model-garden` | yes | no | no |

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

- `vertex-ai-model-garden` (generic)
  - Required YAML settings:
    - `project`
    - `location`
    - `model_family` (`mistral`, `llama`, `anthropic`)
  - Typical auth: same as `vertex-ai` (ADC).

## Minimal Examples

Agentic (Vertex Model Garden, Mistral Small 3.1):

```yaml
ai:
  default_chat_model:
    provider: "vertex-ai-model-garden"
    name: "mistral-small-3.1-24b-instruct-2503"
    settings:
      model_family: "mistral"
      project: "your-gcp-project-id"
      location: "europe-west1"
      temperature: 0.0
      max_retries: 2
      request_timeout: 90
```

Knowledge Flow (Vertex chat + embedding + vision):

```yaml
chat_model:
  provider: vertex-ai-model-garden
  name: mistral-small-3.1-24b-instruct-2503
  settings:
    model_family: mistral
    project: your-gcp-project-id
    location: europe-west1

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
```

## Notes

- Keep secrets in `.env`, not in YAML.
- Keep `configuration_prod.yaml` as the source of commented provider examples.
- Use environment-specific files (`configuration.yaml`, `configuration_bench.yaml`, `configuration_gcp.yaml`) for active runtime values only.

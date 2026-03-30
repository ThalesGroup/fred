# Fred Environment Variables

This is the central inventory for environment variables in the active Fred codebase.

Scope:
- `agentic-backend`, `knowledge-flow-backend`, `control-plane-backend`, `fred-core`, `frontend`
- excludes `ignored/`, virtual environments, and generated vendor folders

Rule of thumb:
- Use YAML (`configuration*.yaml`) for non-secret configuration.
- Use env variables for secrets and explicit runtime toggles.
- For Fred-owned knobs, prefer `FRED_*` naming.
- Keep startup contract variables as-is: `ENV_FILE`, `CONFIG_FILE`.

## 1) Variables Already Standardized In `.env.template`

These are the variables that are already present in at least one backend `.env.template`.

### 1.1 Startup Contract

| Variable | In templates | Purpose |
| --- | --- | --- |
| `CONFIG_FILE` | agentic, knowledge-flow, control-plane | Select YAML profile file at startup. |

Note:
- `ENV_FILE` is part of the shared startup contract and set by Makefiles/launchers; it is not listed in all `.env.template` files.

### 1.2 Security and Identity Secrets

| Variable | In templates | Purpose |
| --- | --- | --- |
| `KEYCLOAK_AGENTIC_CLIENT_SECRET` | agentic | Agentic M2M client secret (outbound calls / Keycloak admin). |
| `KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET` | knowledge-flow | Knowledge-flow M2M client secret. |
| `KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET` | control-plane | Control-plane M2M client secret. |
| `OPENFGA_API_TOKEN` | agentic, knowledge-flow, control-plane | Token for OpenFGA ReBAC API. |

### 1.3 LLM Provider Secrets

| Variable | In templates | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | agentic, knowledge-flow, app-backend | OpenAI provider authentication. |
| `AZURE_OPENAI_API_KEY` | agentic, knowledge-flow | Azure OpenAI direct authentication. |
| `AZURE_AD_CLIENT_SECRET` | agentic, knowledge-flow, app-backend (optional) | Azure AD client credential for Azure APIM/Azure AD token flow. |
| `AZURE_APIM_SUBSCRIPTION_KEY` | agentic, knowledge-flow, app-backend (optional) | APIM subscription key used by Azure APIM provider mode. |

### 1.4 Storage and Database Secrets

| Variable | In templates | Purpose |
| --- | --- | --- |
| `FRED_POSTGRES_PASSWORD` | agentic, knowledge-flow | Main Postgres password. |
| `TABULAR_POSTGRES_PASSWORD` | knowledge-flow | Tabular store Postgres password. |
| `OPENSEARCH_PASSWORD` | agentic, knowledge-flow | OpenSearch authentication. |
| `MINIO_SECRET_KEY` | knowledge-flow, control-plane | MinIO secret for content storage backends when `type=minio`. |
| `CLICKHOUSE_PASSWORD` | knowledge-flow | ClickHouse authentication. |

### 1.5 Observability / Tracing

| Variable | In templates | Purpose |
| --- | --- | --- |
| `LANGFUSE_PUBLIC_KEY` | agentic | Langfuse public key. |
| `LANGFUSE_SECRET_KEY` | agentic | Langfuse secret key. |
| `LANGFUSE_HOST` | agentic | Langfuse host URL used by current runtime code. |
| `LANGFUSE_BASE_URL` | agentic | Legacy naming in template; current runtime reads `LANGFUSE_HOST`. |

## 2) Startup Configuration and Feature-Switch Variables

This chapter lists env vars that change startup behavior or enable/disable runtime checks/features.

### 2.1 Startup File Selection

| Variable | Effect |
| --- | --- |
| `ENV_FILE` | Chooses which `.env` file is loaded by startup helper (`ConfigFiles`). |
| `CONFIG_FILE` | Chooses which YAML configuration file is parsed. |

### 2.2 API Startup Toggle

| Variable | Effect |
| --- | --- |
| `PRODUCTION_FASTAPI_DOCS_ENABLED` | Enables/disables `/docs`, `/redoc`, `/openapi.json` exposure in API apps. |

### 2.3 OIDC/JWT Strictness and Cache

| Variable | Effect |
| --- | --- |
| `FRED_STRICT_ISSUER` | Enforce strict issuer validation. |
| `FRED_STRICT_AUDIENCE` | Enforce strict audience validation. |
| `FRED_JWT_CLOCK_SKEW` | Allowed JWT clock skew (seconds). |
| `FRED_JWT_CACHE_ENABLED` | Enable JWT decode/validation cache. |
| `FRED_JWT_CACHE_TTL` | JWT cache TTL in seconds. |
| `FRED_JWT_CACHE_SIZE` | JWT cache max entries. |

### 2.4 Agentic Catalog and Routing Switches

| Variable | Effect |
| --- | --- |
| `FRED_MODELS_CATALOG_FILE` | Override models catalog path. |
| `FRED_V2_MODELS_CATALOG_FILE` | Backward-compatible alias for models catalog path. |
| `FRED_AGENTS_CATALOG_FILE` | Override agents catalog path. |
| `FRED_MCP_CATALOG_FILE` | Override MCP catalog path. |
| `FRED_MODELS_DEFAULT_CHAT_PROFILE_ID` | Force default chat profile from models catalog. |
| `FRED_MODELS_DEFAULT_LANGUAGE_PROFILE_ID` | Force default language profile from models catalog. |
| `FRED_V2_MODEL_ROUTING_PRESETS_ENABLED` | Enable legacy presets when no catalog controls are available. |
| `FRED_ENVIRONMENT` | Agentic portable environment selection (`dev`, `staging`, `prod`). |

## 3) External/Pass-Through Variables (Not Fred-Owned Runtime Controls)

These variables are important but are not Fred-owned switches in the same sense as `FRED_*`.

### 3.1 Consumed By Libraries/Toolchains or External Contracts

| Variable | Status | Notes |
| --- | --- | --- |
| `OPENAI_API_KEY` | direct runtime use | Required by provider SDK integration. |
| `AZURE_OPENAI_API_KEY` | direct runtime use | Required by Azure OpenAI SDK path. |
| `AZURE_AD_CLIENT_SECRET` | direct runtime use | Used for Azure AD token flow. |
| `AZURE_APIM_SUBSCRIPTION_KEY` | direct runtime use | Sent to APIM header by provider integration. |
| `GOOGLE_APPLICATION_CREDENTIALS` | external contract | Standard Google ADC variable (not directly parsed by Fred runtime logic). |
| `MINIO_SECRET_KEY` | direct runtime use | Loaded into MinIO config models when missing from YAML values. |
| `MINIO_ACCESS_KEY` | pass-through / deployment convenience | Not read directly from env by Fred runtime; only effective if deployment or config templating injects it into YAML `access_key`. |
| `TIKTOKEN_CACHE_DIR` | script/tooling use | Used by `scripts/download_encodings.py`. |
| `VITE_PORT` | frontend tooling | Consumed by Vite dev server config. |
| `VITE_ALLOWED_HOSTS` | frontend tooling | Consumed by Vite dev server config. |
| `VITE_BACKEND_URL` | frontend tooling | Dev proxy target for `/agentic`. |
| `VITE_BACKEND_URL_API` | frontend runtime config | API base URL override in frontend. |
| `VITE_BACKEND_URL_KNOWLEDGE` | frontend runtime config | Knowledge-flow URL override in frontend. |
| `VITE_BACKEND_URL_CONTROL_PLANE` | frontend runtime config | Control-plane URL override in frontend. |
| `VITE_WEBSOCKET_URL` | frontend runtime config | Websocket URL override in frontend. |

### 3.2 Declared But Not Currently Consumed In Active Runtime Code

These exist in templates/docs/deploy values but no active runtime read was found in the current code paths:

| Variable | Where it appears | Current status |
| --- | --- | --- |
| `LANGFUSE_BASE_URL` | `agentic-backend/config/.env.template`, deploy values | Runtime currently reads `LANGFUSE_HOST`. |
| `VITE_USE_AUTH` | deploy values | No active frontend code read found. |
| `FRED_AUTH_VERBOSE` | docs only | No runtime read found. |
| `FRED_TEMPORAL_CODEC_KEY` | docs only | No runtime read found. |

## 4) Naming Convention Going Forward

To keep ownership and intent clear:

- New Fred-owned env variables should use `FRED_*`.
- Keep third-party standard names unchanged (`OPENAI_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS`, etc.).
- Keep startup contract names unchanged: `ENV_FILE`, `CONFIG_FILE`.
- Any new env variable must be documented in:
  - this file, and
  - the relevant backend `config/.env.template`.

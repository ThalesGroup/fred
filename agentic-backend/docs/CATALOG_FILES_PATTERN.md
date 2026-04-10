# Catalog Files Pattern (Intermediate Step)

## Goal

Move business catalogs out of `configuration*.yaml` while keeping backward compatibility.

In this intermediate phase:

- If a catalog file is present, it takes precedence.
- If absent, existing `configuration*.yaml` sections are still used.
- Invalid catalog files fail fast at startup.

## Supported catalogs

1. `models_catalog.yaml`
- Purpose: model routing policy for v2 runtimes.
- Default path: `./config/models_catalog.yaml`
- Env override: `FRED_MODELS_CATALOG_FILE` (preferred), or `FRED_V2_MODELS_CATALOG_FILE` (compat).
- Single-file strategy: one catalog can contain profiles for multiple providers
  (`openai`, `azure-apim`, `azure-openai`, `ollama`/mistral, ...).
- Scope:
  - v2 ReAct + v2 Graph `ChatModelFactoryPort` routing policy
  - `ai.default_chat_model` / `ai.default_language_model` bootstrap at config load time
    (for shared model access including v1 code paths).
- Optional deployment-level overrides for defaults:
  - `FRED_MODELS_DEFAULT_CHAT_PROFILE_ID`
  - `FRED_MODELS_DEFAULT_LANGUAGE_PROFILE_ID`

2. `agents_catalog.yaml`
- Purpose: static agent declarations.
- Default path: `./config/agents_catalog.yaml`
- Env override: `FRED_AGENTS_CATALOG_FILE`
- Overrides: `ai.agents` from `configuration*.yaml` when file exists.

3. `mcp_catalog.yaml`
- Purpose: static MCP server declarations.
- Default path: `./config/mcp_catalog.yaml`
- Env override: `FRED_MCP_CATALOG_FILE`
- Overrides: `mcp.servers` from `configuration*.yaml` when file exists.

## Deployment guidance

For Helm/K8s:

- Mount the catalog files under `/app/config/*.yaml`.
- Set env vars only when using non-default paths.
- Keep `configuration.yaml` focused on platform settings (`app`, `security`, `storage`, `scheduler`, etc.).

See:

- [`models_catalog.yaml`](/home/dimi/run/reference/fred/agentic-backend/config/models_catalog.yaml)
- [`agents_catalog.yaml`](/home/dimi/run/reference/fred/agentic-backend/config/agents_catalog.yaml)
- [`mcp_catalog.yaml`](/home/dimi/run/reference/fred/agentic-backend/config/mcp_catalog.yaml)
- [`deploy/charts/fred/values.yaml`](/home/dimi/run/reference/fred/deploy/charts/fred/values.yaml)

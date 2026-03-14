# app-backend

Single-process backend entrypoint that runs:

- control-plane backend controllers
- agentic backend controllers
- knowledge-flow backend controllers

This app keeps the same route prefixes:

- `/control-plane/v1/*`
- `/agentic/v1/*`
- `/knowledge-flow/v1/*`

## Configuration

Use app-backend config files:

- `app-backend/config/.env` (copy from `.env.template`)
- `app-backend/config/configuration.yaml`
- `app-backend/config/configuration_prod.yaml` (optional production profile)

The app-backend configuration declares:

- app-level options (`app.name`, `app.docs_enabled`)
- per-service enable flag
- per-service route prefix
- per-service config file paths for control-plane, agentic and knowledge-flow

## Single `.env` for Embedded Mode

`app-backend` uses one global `ENV_FILE` for the whole process.

- Keep only one env file (for example `app-backend/config/.env`) containing the union
  of variables required by control-plane, agentic, and knowledge-flow.
- Keep three separate backend YAML files via each service `config_file`.
- Embedded backends are forced to reuse this same `ENV_FILE`; their local
  `agentic-backend/config/.env`, `knowledge-flow-backend/config/.env`, and
  `control-plane-backend/config/.env` are not used by `app-backend`.

## Quick Setup Checklist

1. Copy `app-backend/config/.env.template` to `app-backend/config/.env`.
2. Set `CONFIG_FILE` in that `.env`:
   - `./config/configuration.yaml` for standalone/dev profile.
   - `./config/configuration_prod.yaml` for local prod-like profile.
3. Fill required secrets in the same `.env` (Keycloak, OpenFGA, OpenAI, Postgres, MinIO).

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

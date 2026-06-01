# fred-agents

Small standalone Fred agent pod used to exercise `fred-sdk` and `fred-runtime`
outside `agentic-backend`.

## Local Runtime Wiring

`apps/fred-agents` currently serves its runtime API under:

- `app.base_url = /fred/agents/v2`

That base path must stay aligned across three places during local development:

1. `apps/fred-agents/config/configuration*.yaml`
2. `apps/control-plane-backend` `platform.runtime_catalog_sources.*`
3. the frontend reverse proxy (`frontend/vite.config.ts` or nginx ingress)

Minimal local example:

```yaml
# apps/control-plane-backend/config/configuration*.yaml
platform:
  runtime_catalog_sources:
    - runtime_id: fred-agents
      base_url: http://127.0.0.1:8000/fred/agents/v2
      enabled: true
      ingress_prefix: /fred/agents/v2
```

And in the frontend proxy, expose `/fred` to the local pod on port `8000`.

If `base_url` is correct but `ingress_prefix` or the frontend proxy is wrong,
templates may still appear in the UI while managed execution fails later during
`prepare-execution` or runtime calls.

## Docker image contract

The production image lives at:

- `apps/fred-agents/dockerfiles/Dockerfile-prod`

Build it from the repository root:

```bash
docker build -f apps/fred-agents/dockerfiles/Dockerfile-prod -t fred-agents .
```

Or from the app directory:

```bash
make docker-build
make docker-run
```

Runtime contract:

- entrypoint: `python -m fred_agents`
- host / port / log level come from the mounted YAML config
- `.env` + `configuration.yaml` stay externalized under `/app/config`
- `models_catalog.yaml` and `mcp_catalog.yaml` can be overridden the same way

Minimal run example:

```bash
docker run --rm -it \
  -p 8000:8000 \
  -v "$(pwd)/apps/fred-agents/config:/app/config:ro" \
  fred-agents
```

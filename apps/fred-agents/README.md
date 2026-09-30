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
- `models_catalog.yaml` and `mcp_catalog_external.yaml` are mounted by the Fred chart

The production image does not include `models_catalog.yaml`. Deployments outside
the Fred chart must mount it at `/app/config/models_catalog.yaml` or set
`FRED_MODELS_CATALOG_FILE` to their catalog path.

Fred's internal MCP catalog and its instructions are loaded from the installed package
[`fred-capability-mcp`](../../libs/capabilities/fred-capability-mcp/README.md).
The package contains one `mcp_catalog.yaml` with the Fred / Knowledge Flow servers.
The app's `config/mcp_catalog_external.yaml` adds deployment-owned servers;
its default `servers: []` leaves the packaged set unchanged. Set
`applications.fred-agents.mcp_catalog_external.servers` in Helm values to add
servers to a deployed Fred pod.
Internal HTTP entries use `service: knowledge_flow` and a relative `path`; the
runtime resolves their URL from `ai.knowledge_flow_url`, including its port and
API prefix. External entries can still provide a concrete `url`.
At startup, `FRED_MCP_CATALOG_FILE` takes precedence over an existing
`config/mcp_catalog.yaml`; either replaces the entire packaged server list.
Otherwise the pod discovers the installed package through its `fred.mcp_catalogs`
entry point and adds the servers from `FRED_MCP_EXTERNAL_CATALOG_FILE` (default:
`config/mcp_catalog_external.yaml`). Duplicate IDs fail startup.
The packaged catalog references its tabular Markdown prompt with
`prompt_file: pkg://fred_capability_mcp/prompts/tabular.md`.
The Fred chart leaves the packaged catalog active by default while adding the
external file's entries.
The pod reads them at startup; the package is installed locally and in the image,
so these references need no additional mount and work with a relocated catalog.

Instructions can also stay inline in `agent_instructions`, or use a UTF-8 file
path relative to the catalog directory (absolute paths also work). Declare only
one source; missing files fail startup. Mount any custom filesystem sources and
remove the file-reference key when supplying inline text. Existing MCP capability
IDs, composer controls and prompt rendering are unchanged. `McpCapability` and
the catalog loaders now live in `fred-sdk`; the package does not depend on the runtime.

Minimal run example:

```bash
docker run --rm -it \
  -p 8000:8000 \
  -v "$(pwd)/apps/fred-agents/config:/app/config:ro" \
  fred-agents
```

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

The two Dockerfiles are:

- `apps/fred-agents/dockerfiles/Dockerfile-base` - Ubuntu 24.04, Python 3.12,
  headless LibreOffice, fonts, `fred-pod`, `fred-core`, `fred-sdk`, `fred-runtime`,
  and their locked third-party dependencies. It contains no capabilities.
- `apps/fred-agents/dockerfiles/Dockerfile-prod`

Build both from the repository root:

```bash
docker build -f apps/fred-agents/dockerfiles/Dockerfile-base -t fred-agents-base:local .
docker build --build-arg BASE_IMAGE=fred-agents-base:local \
  -f apps/fred-agents/dockerfiles/Dockerfile-prod -t fred-agents:local .
```

Or from the app directory:

```bash
make docker-build
make docker-run
```

`make docker-build` builds the base first. In CI, a `code/v*` tag publishes both
images under the same version. A `swift` push republishes only images whose build
inputs changed; a capability-only change reuses the existing `fred-agents-base:swift-dev`.
The "Build and Push Docker Images" manual workflow on `swift` republishes all
images when a security refresh is needed without a dependency change.
Pull request checks build the base from the same checkout as the agent image.
Image CVE scans report findings without blocking publication.

The base has its own manifest and lock under `apps/fred-agents/base/`. After
changing shared Python dependencies or refreshing `apps/fred-agents/uv.lock`,
realign the base lock with the agent's common package versions:

```bash
cp apps/fred-agents/uv.lock apps/fred-agents/base/uv.lock
uv lock --project apps/fred-agents/base --offline
python3 -m unittest discover -s scripts/tests -p 'test_agent_base_lock.py'
```

The CI alignment check catches changes to shared direct dependencies and
version drift. Capability packages remain in the final agent image.

Runtime contract:

- entrypoint: `python -m fred_agents`
- host / port / log level come from the mounted YAML config
- `.env` + `configuration.yaml` stay externalized under `/app/config`
- `models_catalog.yaml` and `mcp_catalog_external.yaml` are mounted by the Fred chart

The preparation worker is a separate process using the same installed capability
registry. Run `make run-worker` locally or `make run-worker-docker` with the built
image. Both invoke `python -m fred_runtime preparation-worker`; the Docker target
uses `WORKER_CONFIG_FILE` (default `./config/configuration_prod.yaml`) and the
same `.env` as the API, mounted read-only and read by the local user's UID.
The local target accepts `WORKER_ENV_FILE` when the credentials live outside
the checkout; `make run-worker-prod` selects the
production YAML. The worker needs Temporal, the Control
Plane URL, workload credentials and shared object storage. The serving API
remains a separate process.
Any agent pod with `fred-runtime` installed can use the same library command
without a `fred-agents` module.

The production image includes the default `models_catalog.yaml`. Deployments
outside the Fred chart can use that default, mount another file at
`/app/config/models_catalog.yaml`, or set `FRED_MODELS_CATALOG_FILE` to their
catalog path.

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

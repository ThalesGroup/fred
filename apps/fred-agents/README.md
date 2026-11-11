# fred-agents

Fred's Weaver agent pod ships three templates:

- **Custom assistant** (`fred.github.assistant`): configurable ReAct assistant.
- **Custom planning assistant** (`fred.github.deep_assistant`): configurable Deep assistant with built-in workspace tools.
- **Test assistant** (`fred.github.test_assistant`): deterministic scenarios for UI and runtime validation.

The Custom and Planning templates impose no external capabilities by default.
Operators select each instance's tools from the capabilities authorized for its
organization. Capability packages remain installed independently of agent templates.

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
- `mcp_catalog_external.yaml` is mounted by the Fred chart when configured.

Model offers, defaults and permissions come exclusively from the central Weaver
resolver, once per external turn. The pod has no model catalog or discovery.
`inference_credentials` provisions only local access: each entry binds
`credential_binding` and `api_root`, and names the locally supplied secret environment
variables that the connection's authentication requires, among `api_key_env`,
`client_secret_env` and `gateway_key_env`. An entry is required even without a secret.
Both values and that exact set of variables must match the approved resolver connection.
This configuration grants no model permission. No source or credential is enabled by
default. Connection forms are described in the
[Control Plane README](../control-plane/README.md#inference-connection). A missing or
mismatched binding refuses execution.

M4 requires a managed instance and canonical `runtime_context.space_id`, plus
trusted person/workload delegation. Each turn, including a later HITL resume,
resolves again; retries and children keep the current turn's local authority.
The existing OpenAI direct-template and creation-assistant execution surfaces
explicitly refuse execution until they carry that context. See decision 5e and
F25 for the unvalidated integration boundary.

Tabular business instructions and composer controls come from the installed
[`fred-capability-mcp`](../../libs/capabilities/fred-capability-mcp/README.md)
capability package. The connection is declared, discovered and published once
in Control Plane. Compatible pods share its central offer and permission; the
package's `mcp_service` is a dependency, not another native offer. Both pods and
Control Plane must configure the same Knowledge Flow API base URL.

No Tabular or Prometheus technical catalog is packaged. Old KF pod catalog
entries fail startup with an explicit diagnostic. Sync editable dependencies
(`make dev`) after the entry-point change. Author defaults may retain the stable
Tabular dependency ID; Control Plane resolves it to the deployment's offer.

Independent/non-migrated pod MCP catalogs retain the SDK loader and explicit
`FRED_MCP_CATALOG_FILE` / `FRED_MCP_EXTERNAL_CATALOG_FILE` configuration. Their
instruction files and custom capability behavior remain supported. New managed
external servers, including Streamable HTTP gateways, use the central MCP page;
none receive Fred identity or document context. `document_access` remains native
SDK/REST. See [the unexecuted two-pod reception](../control-plane/README.md#real-knowledge-flow-reception-two-pods).

Minimal run example:

```bash
docker run --rm -it \
  -p 8000:8000 \
  -v "$(pwd)/apps/fred-agents/config:/app/config:ro" \
  fred-agents
```

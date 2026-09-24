# fred-pod

A **Fred pod** is a program you deploy next to Fred to contribute something to
it: agents a team can chat with, or documents kept in sync from an outside
source. Whatever it contributes, every pod does the same three things:

- it reads **one `configuration.yaml`**, with secrets in the environment only;
- it authenticates to Fred **as a workload**, with its own Keycloak client;
- it **names** what it contributes under a prefix its contributor owns.

`fred-pod` is that shared floor. You rarely install it yourself: `fred-sdk`
brings it in.

## Which pod are you building?

| You want to… | You build | Install | Working example |
| --- | --- | --- | --- |
| give teams agents to chat with | an **agent pod**: an HTTP service serving a registry of agents | `fred-runtime[app]` | [`fred-samples/agents`](https://github.com/fred-agent/fred-samples/tree/swift/agents) |
| keep a team's library in sync with an outside source | a **Knowledge Base pod**: no inbound port; `publish` declares it, `run` serves the runs Fred schedules | `fred-sdk[knowledge-base]` | [`fred-samples/knowledge-bases`](https://github.com/fred-agent/fred-samples/tree/swift/knowledge-bases) |
| add tools to agents that already run | a **capability package** — not a pod: it is installed into an agent pod | `fred-sdk[agents]` | [`libs/capabilities`](https://github.com/ThalesGroup/fred/tree/swift/libs/capabilities) |

The authoring guides are in the
[`fred-sdk`](https://github.com/ThalesGroup/fred/tree/swift/libs/fred-sdk) and
[`fred-runtime`](https://github.com/ThalesGroup/fred/tree/swift/libs/fred-runtime)
READMEs.

## How the packages stack

```
fred-pod                    configuration, identity, naming
└── fred-sdk                authoring contracts (base: fred-pod + pydantic + httpx)
    ├── [knowledge-base]    + the workflow engine          → a Knowledge Base pod
    └── [agents]            + fred-core, langchain, langgraph
        └── fred-runtime    execution, MCP, model routing
            └── [app]       + the FastAPI pod factory      → an agent pod
```

`fred-core` is the agents platform behind `[agents]`: stores, model providers,
observability. It depends on `fred-pod` too, and is never needed by a
Knowledge Base pod.

## What every pod shares

**Configuration.** `configuration.yaml` is found through `$CONFIG_FILE`, and
the `.env` next to it through `$ENV_FILE`. The environment carries secrets and
nothing else, so a Kubernetes ConfigMap and a local file differ only in where
they are mounted.

```python
from fred_pod import ConfigFiles, load_configuration_with_config_files
```

**Identity.** `security.m2m` gives the pod's Keycloak `realm_url` and
`client_id`, and `secret_env_var` names *which environment variable* holds the
client secret; the value itself never appears in the YAML. `M2MTokenProvider`
exchanges it for a token, caches it and refreshes it before it expires.

**Naming.** Everything a pod contributes has a dotted name under a prefix its
contributor owns: `fred.samples.local-folder`, `acme.support.router`. Fred
claims the prefix for the first client that publishes under it, so no central
registry is needed. `require_contributed_name` and `prefix_covers` check the
rule.

## Why a separate package

A Knowledge Base pod whose whole job is a few HTTP calls should not install the
agents platform, and `fred-core` carries all of it: database drivers, object
stores, a client for every LLM provider. So the floor every pod needs lives
here, and its dependency list is the contract:

```
pydantic   python-dotenv   pyyaml   httpx
```

A fifth dependency is a deliberate decision made in a diff. If a change needs
something heavier, it belongs in `fred-core`.

The module paths mirror `fred_core`'s, and `fred-core` re-exports every name
that moved here, so existing imports keep working. New code imports from
`fred_pod`.

## Layout

```
fred_pod/
├── common/
│   ├── naming.py          contributed names, prefixes, catalog ids
│   ├── structures.py      configuration models (scheduler, stores, KPI sinks)
│   ├── config_files.py    resolving configuration.yaml and its .env
│   └── config_loader.py   loading and validating it into a Pydantic model
└── security/
    ├── structure.py                security configuration models, KeycloakUser
    ├── delegation.py               the security.delegation configuration block
    └── backend_to_backend_auth.py  M2M token provider and httpx auth
```

## Development

```
make dev            # install with the local monorepo checkout
make test           # offline unit tests
make code-quality   # ruff, bandit, detect-secrets, basedpyright
make publish        # build and upload to PyPI (needs PYPI_TOKEN)
```

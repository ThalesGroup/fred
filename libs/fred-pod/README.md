# fred-pod

What a Fred component needs to *be* a pod: **configuration, identity, naming**.

A Knowledge Base pod, a capability pod, an MCP server pod and an agent pod all read a
`configuration.yaml`, get a machine-to-machine token, and name things under a prefix they
own. That floor is this distribution.

| Question | Answer |
| --- | --- |
| What do I need to *run* a Fred component? | `fred-pod` |
| What do I need to *build an agent*? | `fred-core` / `fred-sdk` |

## Why it is its own distribution

`fred-core` declares 31 runtime dependencies — pandas, pyarrow, google-cloud-storage, minio,
opensearch-py, sqlalchemy, asyncpg, azure-identity, fastapi, and a client for every LLM
provider. That is the right list for the agents/LLM platform `fred-core` is. It is the wrong
list for a pod whose job is one PROPFIND and a few GETs.

Extras were the obvious alternative and were rejected for one reason: **a boundary the build
does not enforce erodes.** `fred-core` reached 31 dependencies precisely because nothing
stopped it. Nothing would stop an `import pandas` landing in `structures.py` next month
either, and nobody would notice. A separate distribution cannot import what it does not
depend on — the rule keeps itself.

It showed its worth immediately: `config_loader.py` has always done `import yaml`, and
`fred-core` never declared PyYAML. It worked because something else happened to pull it in.
Here it is declared, because here it had to be.

## The dependency list is the contract

```
pydantic   python-dotenv   pyyaml   httpx
```

Four packages. Adding a fifth is a decision someone makes on purpose, in a diff, and that is
the whole point. If a change to this library needs a heavier import, the change belongs in
`fred-core`, not here.

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

The paths mirror `fred_core`'s on purpose: a call site migrates by swapping the prefix
`fred_core.` → `fred_pod.` and nothing else.

## Compatibility

`fred-core` depends on `fred-pod` and re-exports every name it moved, at both the package
top level and the original submodule paths. Existing code keeps working unchanged; imports
migrate opportunistically.

```python
from fred_pod import ConfigFiles, KeycloakUser, M2MTokenProvider
from fred_pod.common.naming import require_contributed_name
```

## Development

```
make dev            # install with the local monorepo checkout
make test           # offline unit tests
make code-quality   # ruff, bandit, detect-secrets, basedpyright
make publish        # build and upload to PyPI (needs PYPI_TOKEN)
```

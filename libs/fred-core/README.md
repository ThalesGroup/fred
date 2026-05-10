# Fred Core

`fred-core` is the shared utility layer for Fred backends. It centralizes the
foundational building blocks that must stay consistent across services.

What it provides
----------------
- Configuration helpers used by multiple backends.
- Storage and session primitives.
- Security and access-control utilities (ReBAC helpers, Keycloak helpers).
- Common runtime helpers (logging, KPI, scheduling utilities).

What it is not
-------------
- A full runtime or service on its own.
- A public SDK for agent authoring (that is `fred-sdk`).

Install
-------
```bash
pip install fred-core
```

Usage (example)
---------------
Fred backends import shared helpers from `fred_core` to keep configuration and
behavior aligned:

```python
import logging

from fred_core.common.config_files import ConfigFiles

logger = logging.getLogger("fred")
config_files = ConfigFiles(logger=logger)
env_path = config_files.load_environment()
yaml_path = config_files.resolve_config_file_path()
```

Notes
-----
`fred-core` is designed for internal Fred services and adapters. If you are
building agents or workflows, you likely want `fred-sdk` instead. In most
cases, end users should not install `fred-core` directly because it is pulled
in transitively by `fred-sdk`.

Development validation
----------------------
- `make test` runs the default offline test suite.
- `make coverage-offline` runs the canonical offline coverage command with
  terminal missing-line output.

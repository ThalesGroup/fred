# Fred Core

`fred-core` is the shared utility layer for Fred backends. It centralizes the
foundational building blocks that must stay consistent across services.

## What it provides

- Configuration helpers used by multiple backends.
- Storage and session primitives.
- Security and access-control utilities (ReBAC helpers, Keycloak helpers).
- Common runtime helpers (logging, KPI, scheduling utilities).
- The pod floor — configuration files, identity, contributed-name rules — now
  lives in [`fred-pod`](../fred-pod/README.md) and is re-exported from here, so
  existing `fred_core` imports are unchanged.

## What it is not

- A full runtime or service on its own.
- A public SDK for agent authoring (that is `fred-sdk`).

## Install

```bash
pip install fred-core
```

## Notes

`fred-core` is designed for internal Fred services and adapters. If you are
building agents or workflows, you likely want `fred-sdk` instead. In most
cases, end users should not install `fred-core` directly: `fred-sdk[agents]`
pulls it in. A Knowledge Base pod wants `fred-pod` (via the lean `fred-sdk`
base) and not this package at all.

## Weaver authorization model consumer

`fred_core.security.rebac.authorization_binding.read_authorization_binding`
borrows an `AsyncEngine` and releases its SQL connection before returning the
immutable `AuthorizationBinding`. Then call:

```python
from fred_core.security.rebac.authorization_model import validate_authorization_binding

validated = await validate_authorization_binding(binding, openfga_config, token=token)
```

The exact signature is `async def validate_authorization_binding(binding:
AuthorizationBinding, config: OpenFgaRebacConfig, *, token: str | None = None)
-> AuthorizationBinding`. Success returns the same object, without replacing any
identifier. This primitive is not connected to startup. It owns its HTTP client
and closes it on success, failure or cancellation; it takes no SQL resource.
It uses the configured API URL, static headers, explicit token or `token_env_var`,
and `timeout_millisec` (5000 by default; None explicitly disables the timeout).
Only `GET /stores/{active_store}/authorization-models/{model_id}` is issued,
without retries or redirects. The configured model ID and store creation/schema
synchronization flags do not select or mutate the published model.

Validation follows Rust `Fga::bind`: exact ID/schema, equal type definitions after
`normalized_model`, and absent/null/empty-object conditions. Normalization removes
only empty-string `object`/`condition`/`module`, null `metadata`/`source_info`, and
empty-object `relations`, recursively and before visiting children. Arrays retain
order and other fields survive. Raw JSON is required because SDK model
construction drops unknown fields. Non-JSON NaN/Infinity are rejected.

Model errors inherit `AuthorizationModelError` and `AuthorizationBindingError`:
`CanonicalModelError` (missing/invalid packaged resource),
`AuthorizationModelNotFoundError` (HTTP 404),
`InvalidAuthorizationModelResponseError` (invalid JSON/envelope),
`IncompatibleAuthorizationModelError` (different model), and
`AuthorizationModelCommunicationError` (transport/timeout/other HTTP failures).
Messages contain no response body, endpoint, credential or chained transport error.
A configured-store mismatch remains `AuthorizationBindingError`; missing token
remains `ValueError`, as in the existing OpenFGA engine.

### Canonical resource distribution

The sole maintained source is `apps/control-plane/openfga/model.json`.
`setup.py` copies it byte-for-byte to
`fred_core/security/rebac/weaver-model.json` before wheel, sdist and editable
builds. This ignored generated file is explicit setuptools package data; never
edit it. Reproduce from the repository with `cd libs/fred-core && uv build`.
For an existing editable environment after a canonical model change, run
`uv sync --reinstall-package fred-core` from that environment's project directory.
A standalone sdist carries the resource and needs no Control Plane checkout.
A build without either source or distributed resource fails explicitly.

The final fred-agents Docker stage copies the same Rust source directly into the
package before its editable installation. Installed code reads only the package
resource through `importlib.resources`, without walking up the checkout. Docker
builds and Python packaging do not require a separately maintained model copy.

## Schema migrations

Python services call `fred_core.sql.require_tables` at startup to check required
SQL tables. A missing table raises `SchemaNotMigratedError`; its message names
the owning component and the exact migration command to run. If a version table
is supplied but has no revision, the guard warns that the schema is unmanaged.
Inspect the owning component's Alembic migrations before resolving that state;
do not create tables or stamp a revision merely to silence the guard.

The Rust Control Plane uses its own
[SQLx migration procedure](../../docs/architecture/A3-manager-operations.md#sqlx-schema-evolution).

## Development validation

- `make test` runs the default offline test suite.
- `make coverage-offline` runs the canonical offline coverage command with
  terminal missing-line output.

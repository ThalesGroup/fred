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

## Development validation

- `make test` runs the default offline test suite.
- `make coverage-offline` runs the canonical offline coverage command with
  terminal missing-line output.

## Context

See proposal.md. Current code: `main.rs` runs `axum::serve` without a shutdown
signal; `fga.rs` maps any OpenFGA write 400 to the guard `Conflict`; `spaces::revoke`
always calls `audit_relation`; `documents/object_store.rs` discards SDK errors with
`map_err(|_| ...)`; `main.rs::import_setup_error` matches message strings.

## Goals / Non-Goals

**Goals:** Python parity on the five edges, each proven by a regression test.

**Non-Goals:** lock-wait timeouts on governance routes (deferred), authorization
helper unification and per-request context removal (next lot), new endpoints.

## Decisions

- **Shutdown:** `axum::serve(...).with_graceful_shutdown(signal)`; the cleanup task
  stops on the same signal. Kubernetes `terminationGracePeriodSeconds` becomes a
  chart value on the manager deployment, defaulting to `transfer_seconds + 30`.
  Alternative (rely on retries after kill) rejected: it blocks names for the lease.
- **Subject validation:** one function rejects empty, overlong (>254) or
  whitespace/`:`/`#`-containing subjects, called by space and platform role routes
  before locking. The FGA 400 → `Conflict` mapping stays for guard deletes only.
- **Revocation audit:** emit when the role was in `on_space`; the guard fence stays.
- **Storage logs:** a small helper logs `storage_operation`, `error_kind` (SDK
  service code or transport) at warn, never keys or bodies.
- **CLI errors:** a typed `SetupError` enum with fixed operator messages replaces
  string comparison; unknown causes keep the generic message.

## Risks / Trade-offs

- [A long upload exceeds the grace period] → grace follows `transfer_seconds`, the
  same bound the server enforces.

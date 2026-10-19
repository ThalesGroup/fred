## Why

Every manager request recomputes the caller's organization from all their direct
roles before its OpenFGA Check: about two Reads per held role (41 roles: p95 87 → 611 ms
at 50 clients). Uniqueness of the organization is already enforced at assignment, so
the Check alone refuses another organization. Three authorization helpers also answer
a foreign organization differently (403, 404, 200 false, 400) and a dependency
failure with 500 or 503. Decided in the 2026-10-19 audit (issue #3092).

## What Changes

- One authorization path per request: load the target space, one OpenFGA Check.
- A target in another organization returns 403, as in Python; authorization probes
  answer `allowed: false` for both foreign and missing targets.
- A folder identifier outside the requested space returns 404 everywhere.
- OpenFGA or SQL dependency failure during authorization returns 503 everywhere.
- Organization resolution remains only where a person is attached (role grants,
  import, organization creation) and in `/me/spaces`, which reports contradictions.

## Capabilities

### New Capabilities

### Modified Capabilities
- `fred-manager-provisioning`: business access no longer resolves an organization
  context per request; folder parents outside the space return 404.
- `document-storage`: storage authorization is the owning space's Check alone.

## Impact

`apps/fred-manager` authorization helpers (`api.rs`, `spaces.rs`, `documents/`),
request-budget tests and fixtures, arc42 security/matrix/quality cost tables and
journeys. No API path, payload or UI change; one status code changes for foreign
document targets (404 → 403).

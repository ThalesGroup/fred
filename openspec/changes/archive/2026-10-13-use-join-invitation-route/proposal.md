## Why

Invitation URLs currently expose the implementation-specific `/join-free` path. The feature has not been activated in any deployment, so the public path can be simplified before rollout.

## What Changes

- Generate team invitation URLs under `/join/:token` and serve the enrollment page at that path.
- Recognize the new path during admission denial and OIDC sign-in, and redact its token in Fred logs.
- **BREAKING**: Remove `/join-free/:token` without an alias. No deployed invitations require compatibility.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: Specify the invitation route and the same route for generated and recovered URLs.

## Impact

Frontend routing and link generation, shared log redaction, focused tests, and the operator log-masking note. The control-plane API and database do not change.

## Why

The provisioning browser journey starts with a pre-granted root and mocked control-plane shell reads. A fresh user cannot complete the agreed first journey entirely through control-plane. This slice implements the developer-approved sequence under #3092.

## What Changes

- **BREAKING on this experimental branch:** the frontend entry serves only manager onboarding, provisioning and the caller's organization/space memberships. It does not mount the legacy control-plane shell or add a compatibility mode.
- Enable versioned terms acceptance in manager configuration and the browser fixture. Acceptance records consent only; it creates no role, space or membership.
- Reuse the bootstrap screen and Rust durable root reservation. Root has platform authority only, with no implicit organization or personal space.
- Preserve ZIP import and display its report; after changing accounts, require each person's own acceptance and display their declared memberships.
- Keep a compact business-journey inventory outside the architecture dossier, and document implemented behavior in arc42.

## Capabilities

### New Capabilities

### Modified Capabilities

- `control-plane-provisioning`: fresh-platform onboarding and real browser acceptance before provisioning.

## Impact

Rust HTTP/configuration/SQL migration, generated OpenAPI and RTK client, frontend entry and shared onboarding components, browser/integration tests, manager k3d configuration and architecture documentation. No Python authority bridge, dual bootstrap, role mirroring, legacy admission-policy migration or legacy UI enablement.

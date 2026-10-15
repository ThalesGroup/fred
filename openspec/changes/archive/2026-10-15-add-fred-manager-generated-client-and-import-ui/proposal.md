## Why

The Rust provisioning importer has no generated frontend contract or browser journey. A reproducible UI import must exercise the actual ZIP, bearer authentication and manager authorization instead of treating a manual HTTP request as acceptance. This extends #3092 on `chore/rust-rebac`.

## What Changes

- Generate OpenAPI from existing Rust HTTP routes and DTOs without services or configuration.
- Add the conventional manager `generate-openapi` and frontend `update-fred-manager-api` Make targets, including aggregate generation, and register the generated RTK client.
- Add an admin provisioning UI using manager authorization and the synchronous import report, with explicit failure and replay semantics.
- Automate a browser import using the Make-generated ZIP, real Keycloak, PostgreSQL and OpenFGA; verify replay, hierarchy, roles and denied access.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fred-manager-provisioning`: generated HTTP contract and authenticated frontend import journey.

## Impact

`apps/fred-manager`, frontend API generation, Redux registration, admin navigation/import, local proxy routing, automated browser tests and `docs/architecture`. Add Rust OpenAPI dependencies and reuse the repository's RTK code generator and Playwright convention. No document functionality, legacy bundle compatibility, authorization model change or admission-policy migration. Work remains local until explicit push approval.

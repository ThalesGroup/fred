## Why

The next backend step must import a demo ZIP built inside control-plane with the
same `make build-demo-bundle` command as the control-plane. This provides the
concrete fixture for the subsequent generated-client and UI journey.

## What Changes

- Correct the shared role mutation protocol before exposing HTTP import. The
  developer approved this scope extension after a real-OpenFGA fault test exposed
  a delayed child grant becoming effective after parent revocation. The same gap
  also permits a platform grant after its actor's revocation. Preserve the role
  matrix and existing grants, retaining OpenFGA as the role source. Use native
  guarded atomic Writes with explicit offline store cutover, without introducing a
  distributed recovery job system. Record exact query types and cardinality costs.
- Add `build-demo-bundle`, `DEMO_PROVISIONING_FIXTURE_DIR` and `DEMO_BUNDLE_FILE`
  with the control-plane's defaults: checked-in JSON fixtures under
  `tests/fixtures/import_export/demo_provisioning/`, zipped to
  `target/demo-provisioning-bundle.zip`.
- Import one current ZIP format containing identities, organizations, teams,
  projects and their complete role declarations. Projects are supported now;
  the first demo can have an empty project array.
- Expose multipart `POST /control-plane/v1/import-export/import`, using the same
  existing provisioning service as the CLI. Return the completed result or a
  safe failure; do not introduce a background job system.
- **BREAKING**: reject the old JSON input and Python version-1 ZIPs with the stable
  `not_yet_supported` error and no provisioning writes. Do not add adapters,
  automatic conversion or compatibility paths.
- Verify the actual ZIP made by the Make target through automated HTTP import
  tests, including real Keycloak/PostgreSQL/OpenFGA and additive replay.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `control-plane-provisioning`: generated demo ZIP and authenticated hierarchical
  import, replacing the old input contract without legacy support.

## Impact

`apps/control-plane` authorization storage/client, mutation services, new SQL migration,
Makefile, fixtures, ZIP reader, existing provisioning service, HTTP/CLI entry points
and tests. Update applicable arc42 chapters after review in
that implementation commit. Tracking: [#3092](https://github.com/ThalesGroup/fred/issues/3092).

No export endpoint, migration framework, generic blueprint extension mechanism,
new admission policy, arbitrary execution timeout or durable task protocol.
OpenAPI/client generation and browser integration remain the following steps;
this backend step is not acceptance of the complete UI journey. No manual curl
validation and no push.

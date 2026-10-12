## Why

Fred v3.2.0 already stores GCU versions as strings, and the developer confirms all deployments now run that version. The legacy enum and input conversion can be removed. Tracking: [issue #2995](https://github.com/ThalesGroup/fred/issues/2995).

## What Changes

- **BREAKING**: Remove the public `GcuVersionsType` class and its `fred_core` and `fred_core.users` exports.
- Accept only string versions in the user-store interface and remove enum conversion.
- Adapt the existing store test to use `"v1"`, preserving its version, timestamp, identity, storage and concurrent-acceptance assertions.
- Document the retired Python API in a new migration note; retain the existing database and HTTP contracts and historical migrations.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `user-terms-acceptance`: Declare the string-only Python store input and removal of the legacy enum export.

## Impact

Changes are limited to six files in `libs/fred-core`, the existing capability specification and a migration note. External Python consumers still importing the enum must pass strings instead. No configuration, chart schema, dependency or database migration is required.

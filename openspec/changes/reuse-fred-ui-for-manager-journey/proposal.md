## Why

The Rust first-user journey replaces Fred's application entry with a parallel
`ManagerApp` navigation. This makes incremental reconstruction diverge from the
product UI instead of connecting its existing screens to fred-manager.

## What Changes

- Restore the existing Fred application, router, layout, sidebar and account menu
  as the only entry for this branch; delete the parallel manager shell.
- Connect the existing CGU and bootstrap screens and guards to manager state.
- Keep Provisioning in the existing administration console, with the existing
  upload page and completed report.
- Adapt the existing home and space navigation to display declared organizations,
  teams, projects and roles from the generated manager client, including root's
  empty state. Do not create a separate membership application.
- Restrict this branch's reachable routes and mounted data consumers to that
  journey. Hide unsupported navigation; direct URLs must not mount Python pages.
- Preserve admission, authorization, account isolation and real browser coverage.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fred-manager-provisioning`: use Fred's existing UI for the bounded first-user
  journey instead of an independent manager shell.

## Impact

Tracking: [#3092](https://github.com/ThalesGroup/fred/issues/3092).
Frontend entry, guards, application providers, router, home and sidebar consumers,
and existing browser tests. No manager API, role, migration, identity or deployment
change is proposed. Update the architecture journey and affected frontend/manager
documentation when implementation is complete.

## Non-goals

No full-UI migration, document or agent functionality, Python/Rust permission
bridge, synthetic control-plane bootstrap response, second application mode,
new backend configuration API, infrastructure, or environment reset.

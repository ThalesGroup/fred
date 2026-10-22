## Why

Platform access administration and Free enrollment currently require `platform_admin`, which also grants unrelated global powers. The existing `team_manager` can create and list teams but cannot maintain their registry details, so that work also requires a full platform administrator.

Tracks GitHub issue #3235.

## What Changes

- Add a delegated `platform_access_manager` role for the complete platform access administration surface, without import/export, platform reset, user administration, role assignment, team content, or other global administration.
- Extend `team_manager` to edit the name and description of any collaborative team. Keep Free enrollment, team deletion, admin appointment and removal, team-wide authorization, and all other platform access controls outside this role.
- Keep `platform_admin` access to both surfaces. Give a current `platform_access_manager` admission while filtering is active so the role can operate its own surface, subject to suspension and ordinary resource authorization.
- Update the admin UI, bootstrap role list, API types, documentation, and authorization checks. Free-link enrollment semantics remain unchanged: the caller joins as a member and gains a Free admission source only while the required link evidence, membership, and Free flag remain valid.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: delegate the entire platform access surface, including Free enrollment, to `platform_access_manager` while preserving admission and link protections.
- `team-registry-administration`: allow team managers to edit names and descriptions without changing team admins or gaining deletion authority.

## Impact

- OpenFGA organization relations and their Python enums, generated schema, platform role assignment and bootstrap reporting.
- Control-plane platform access and team registry routes, service checks, audit events and focused authorization tests.
- Admin Teams and Platform Access UI gating, role selector, generated API types, localization, and security/product documentation.
- No database schema change is expected; existing Free link and team metadata storage is reused.

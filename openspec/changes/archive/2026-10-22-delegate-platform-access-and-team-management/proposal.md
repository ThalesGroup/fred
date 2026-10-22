## Why

Platform access administration and Free enrollment currently require `platform_admin`, which also grants unrelated global powers. A dedicated role is needed for operators who manage admission without broader platform administration.

Tracks GitHub issue #3235.

## What Changes

- Add a delegated `platform_access_manager` role for the complete platform access administration surface, without import/export, platform reset, user administration, role assignment, team content, or other global administration.
- Keep `team_manager` unchanged: it creates and lists teams but cannot edit registry entries or manage Platform Access.
- Keep `platform_admin` access to both surfaces. Give a current `platform_access_manager` admission while filtering is active so the role can operate its own surface, subject to suspension and ordinary resource authorization.
- Update the admin UI, bootstrap role list, API types, documentation, and authorization checks. Free-link enrollment semantics remain unchanged: the caller joins as a member and gains a Free admission source only while the required link evidence, membership, and Free flag remain valid.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: delegate the entire platform access surface, including Free enrollment, to `platform_access_manager` while preserving admission and link protections.

## Impact

- OpenFGA organization relations and their Python enums, generated schema, platform role assignment and bootstrap reporting.
- Control-plane platform access routes, service checks and focused authorization tests.
- Admin Teams and Platform Access UI gating, role selector, generated API types, localization, and security/product documentation.
- No database schema change is expected; existing Free link and team metadata storage is reused.

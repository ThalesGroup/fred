## Why

Manager splits the space tree across SQL (`parent_id`, `path`) and OpenFGA (direct
roles without hierarchy). Roles cannot reach child spaces: an analyst of an
organization cannot see its projects without one explicit grant per project. The
developer decided on 2026-10-15 to keep the tree in OpenFGA only and let selected
roles descend, so OpenFGA alone answers who may do what where.

## What Changes

- The OpenFGA `space` type gains an immutable `parent` relation. Editor, admin and
  analyst reach every descendant; member stays local.
- A personal space has no parent and inherits nothing. A separate `organization`
  relation, used by no permission, records the organization that manages it.
- SQL keeps only space identity, kind, name and personal owner. `parent_id`,
  `path` and their constraints are removed; sibling-name and kind rules are enforced
  under the organization lock.
- A role on a child requires a **direct** content role on its parent. Inherited
  access does not satisfy it, so revoking a role never orphans a descendant grant.
- `GET /me/spaces` returns spaces reached by inheritance. `roles` lists effective
  roles and `inherited_roles` the subset held only through an ancestor.
- `POST /authorize/scope` reads ancestors from OpenFGA. An optional `levels` filter
  removes organization, team or project levels and never adds a space. A personal
  space's scope is itself.
- **BREAKING** Existing manager data cannot be converted: a dedicated local reset is
  required. The offline `migrate-authorization` cutover is deleted with its tests.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `control-plane-provisioning`: role inheritance, OpenFGA-owned hierarchy, personal
  spaces without inheritance, scope levels.

## Impact

Tracking: [#3092](https://github.com/ThalesGroup/fred/issues/3092). Code:
`apps/control-plane` (model, migration, space services, importer, HTTP handlers,
startup), regenerated OpenAPI and frontend manager client. Docs: arc42 chapters
3, 4, 9 and references A1-A3, manager README, migration note. Frontend behavior and
Python services are unchanged.

## Non-goals

fred-agents integration, conversation binding, agent availability in descendant
spaces, Python ReBAC removal, data conversion, project exclusions (`but not`).

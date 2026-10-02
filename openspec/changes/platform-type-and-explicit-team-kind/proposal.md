## Why

Release 1, step 1 of `docs/swift/rfc/ORGANIZATIONS-AND-PROJECTS-RFC.md` (issue #2921).
Two structural facts are implicit today: the platform is the hard-coded
singleton `organization:fred`, and a personal space is recognized by its
`personal-` id prefix. Organizations cannot become tenants until both facts are
explicit data.

## What Changes

- New ReBAC type `platform`. It takes over every platform role
  (`platform_admin`, `platform_observer`, `team_manager`, `feature_manager`,
  `prompt_editor`), account suspension, every platform-level permission, and the
  catalog anchors and class markers of `capability`, `app` and
  `knowledge_base_definition`. `organization` keeps only the team edge.
- A team has an explicit kind, `shared` or `personal`, held by the team
  registry. A personal space becomes a registry entry like any team.
- No code infers a team's kind from its identifier.
- Behavior is unchanged: every permission answers as before, for every
  existing holder. No API, UI or configuration change.

## Capabilities

### New Capabilities

- `tenancy`: the platform → organization → team hierarchy as explicit data. This
  change covers the platform authority and the team kind; later changes extend
  it with organizations and projects.

### Modified Capabilities

None.

## Impact

- `libs/fred-core`: ReBAC schema and engine, authorization helpers, team id
  helpers, team registry.
- `apps/control-plane-backend`: team, capability, application, routing-policy,
  user and import/export services; startup reconciliation; one Alembic
  migration on the team registry.
- `apps/knowledge-flow-backend`, `libs/fred-runtime`: personal-space checks.
- `apps/frontend`: personal-space checks read `kind` from the regenerated
  client instead of parsing the id; no visible change.
- Contracts: `docs/swift/platform/REBAC.md`,
  `CONTROL-PLANE-PRODUCT-CONTRACT.md` (team payload gains `kind`),
  `RUNTIME-EXECUTION-CONTRACT.md` (runtime context gains the team kind).

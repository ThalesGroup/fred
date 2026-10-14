## Why

fred-manager cannot provision Fred users and spaces from a bundle, and its role
catalog omits existing Python roles. A faithful import requires the complete
assignable role model, enforced permissions and replayable identity provisioning,
not rejecting established roles or merely storing unused role names.

## What Changes

- Complete the five platform roles and four space roles, with explicit cumulative
  grants, scoped permissions, role discovery and protected role administration.
- Add an authenticated, platform-admin-only CLI import of
  `{ "organization": { "name": "TSN", "admins": ["alice"] }, "users": [...] }`.
  Preserve control-plane user entries and extend platform role names to cover the
  complete catalog. Preserve the approved governance/content separation.
- Resolve or create Keycloak identities through fred-manager's own service
  account, declared in its factory-consumed `deploy/k3d/identities.yaml`.
- Reconcile organization, teams, memberships and roles additively; support retries
  after partial failures without identity updates or duplicate spaces.
- Apply the same root-only platform-admin grant protection to import and ordinary
  role administration, closing the Python import bypass.
- Record the branch's complete-feature workflow in AGENTS.md; update the arc42
  dossier after implementation and independent review, in each implementation commit.

## Capabilities

### New Capabilities

- `fred-manager-provisioning`: complete role authorization and authenticated,
  replayable CLI provisioning of identities and the organization/team hierarchy.

### Modified Capabilities

None. `simplify-corpus-authorization` targets the Python cross-stack corpus
replacement; this change targets the isolated Rust component and does not claim
to implement that change's UI, runtime or corpus behavior.

## Impact

apps/fred-manager domain, OpenFGA model/client, role services/API, CLI,
configuration, factory identity declaration and tests; AGENTS.md and
docs/architecture. Keycloak Admin REST, Postgres and OpenFGA are dependencies.
Existing applied migrations remain untouched; existing stored role tuples retain
their meaning. No push is authorized.

## Non-goals

This step implements authorization decisions, provisioning and role lifecycle;
it does not implement the product operations those decisions can gate, such as
evaluation execution, prompt editing or feature configuration. No UI, OpenAPI,
admission/charter workflow, ingestion, search, CI/chart integration or space deletion
is added. Those boundaries must not be presented as implemented behavior in arc42.

## Context

See [proposal](proposal.md). Sources are the control-plane `BundleUserEntry`,
`importer.py`, `users/platform_roles.py`, `teams/schemas.py`, and fred-core's
`security/rebac/schema.fga`. The assignable catalog contains five platform and
four team roles. `pending_team_admin` and `suspended` are lifecycle state;
ownership, public visibility and structural links are not assignable user roles.

Rust uses direct space roles, a SQL organization/team/project tree and one
advisory lock per organization. Platform admin is stored as `platform:root#admin`.
`/me` currently reports only that platform role. CLI initialization can migrate
SQL and create/sync FGA before authorization; it cannot be reused unchanged for
authenticated import. `security.m2m` currently only supplies an accepted issuer.

## Goals / Non-Goals

Implement the [observable contract](specs/control-plane-provisioning/spec.md)
without introducing per-resource ACLs or implying that permission checks execute
the associated product operation. Keep the Python implementation unchanged.
The user-approved separation of governance and content supersedes Python's
implicit team-admin membership. Existing Rust roles and IDs retain their meaning.

## Decisions

### Complete role model and its consumers together

Keep existing FGA `admin`, `member`, `editor` tuples; add space `analyst` and
platform `observer`, `team_manager`, `feature_manager`, `prompt_editor`. Platform
delegated relations include platform admin for effective checks, while direct
tuple reads drive administration. Extend `/me` and space role parsing, listing,
grant/revoke, content-role detection and child revocation guards together.

Preserve at least one admin on each non-personal space: enumerate its direct
admins under the organization lock before revocation, using higher consistency.
The Python `team-member-roles` spec's automatic member fallback is deliberately
not copied: the approved Rust model requires explicit content grants, including
when an admin role is removed. Removing a last role removes access, subject to
the parent/child and last-admin guards; it never creates content access.

Retain document permissions read/write/manage. Add a separate typed space
capability vocabulary for evaluation rather than making evaluation a document
permission. Authenticated self-check endpoints for platform and space capabilities
report current FGA decisions; they do not accept an arbitrary impersonated user.
Keep DSL and JSON models equivalent through generation and a parity check.

Preserve the Python computed platform capabilities: create/list/delete teams,
rescue team admin, edit agent class path, observe platform, administer users,
manage platform, manage capabilities and edit platform prompts. Preserve the
three distinct evaluation capabilities. A tested matrix covers every positive
and negative role/capability pair, plus isolation between spaces. This implements
the authorization contract, not absent evaluation/catalog/deletion operations.

Extend team creation to accept the platform create-team capability as an
alternative to parent-space management. Parent existence and the nominated
admin's content membership remain required; project creation keeps local
authorization. Add a metadata-only team registry listing for platform list-team
holders. No delegated role bypasses ordinary space grant/revoke checks.

Provide platform-role list/grant/revoke API operations using Fred's public
platform role names. Only direct tuples are mutable. Use a shared platform
mutation lock for bootstrap, role changes and provisioning. Recheck platform
admin and completed bootstrap root under that lock. Admin grants are root-only
even through import; root revocation is forbidden. This deliberately closes the
Python importer's bypass rather than reproducing it.

Before any ordinary platform grant, resolve the target subject in Keycloak.
Missing identities fail and directory outages fail closed before a tuple write.
Keep stale non-root grants revocable without a successful directory lookup.
Introduce the shared service-account configuration and read-only directory
client in the role foundation so its public API has no unchecked-identity gap;
the import step extends that same client with creation.

### CLI and preflight

Add `control-plane import-provisioning <bundle.json> --token-file <path>` and a
matching Make target. Read a bearer from the file rather than command arguments;
do not acquire the operator token through the service client's credentials.
Reuse the existing authenticator and configured JWT restrictions, requiring
Keycloak subject mapping and enabled authentication.

Parse and validate the entire bundle without echoing payload values in errors.
Reject duplicate usernames to avoid order-dependent identity fields. Require
organization admins to name bundle entries; use current organization creation's
explicit admin+member initialization. Only team-role holders otherwise get org
membership. Normalize legacy/canonical platform aliases into the same typed role.
Reject lifecycle states as non-assignable rather than promote pending admins.

Connect to existing FGA state without create/sync, verify caller authority and
root-only declarations, then inspect existing SQL state and Keycloak identities.
Complete all predictable preflight checks before the first mutation. Require an
initialized, compatible schema/model, and report the normal service initialization
procedure if missing; the import command does not migrate or sync them itself.
No Temporal client is initialized.

### Keycloak client and factory convention

Extend `security.m2m` with Fred's `enabled`, `client_id`, `secret_env_var`
convention while preserving issuer-only configurations used by the existing
server. Import requires enabled outbound credentials. Keep secrets out of Debug,
URLs and upstream error messages. Use one timeout-bounded HTTP client, encoded
URL segments/query parameters, client-credentials tokens and exact username
lookup with pagination. Reject ambiguous results. On username creation conflict,
resolve again. Never modify existing identities. Use enabled users, non-temporary
passwords and the Python fallback email. Test against a local fake Admin REST
server, including expiration/401 handling, conflicts, malformed replies and
credential-echo errors; include a real disposable Keycloak integration test.

Declare `control-plane` with secret key `KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET` in
`apps/control-plane/deploy/k3d/identities.yaml`, granting realm-management
query-users/view-users/manage-users. The existing factory already consumes it;
no factory engine change is needed. Wire the secret reference into app-owned
k3d values and the environment template. Do not claim Docker Compose creates
this client: document the actual factory k3d provisioning path and host access.

### Reconciliation and locking

Use a private import path for platform-authorized reconciliation, sharing space
validation and organization locking with ordinary writes. Never grant temporary
space roles to the importer. Acquire platform lock before organization lock;
all platform revocations use the same platform lock. Under those locks, reread
authority and relevant direct roles using higher-consistency FGA reads/checks.
Revalidate the bearer at mutation boundaries so an expired token cannot authorize
later phases of a long import. Hold the platform lock through each outbound
identity mutation as well, to serialize it against revocation.

Resolve committed organizations by root name and teams by parent/name, checking
kind and personal ownership. Serialize root-name creation, then reread after
locks; unique constraints remain the final guard. Commit space rows only after
initial requested grants are accepted. Grants for an uncommitted random space ID
cannot authorize a real space; never reuse that uncommitted ID. Replay repairs
missing grants on committed IDs. Write parent member grants before child grants;
bounded batches honor FGA write limits without releasing the organization lock
between invariant checks and dependent writes.

Do not hold one database transaction across the complete identity phase. There
is no distributed transaction across Keycloak, SQL and FGA. Successful identity
creation remains after failure, and a retry resolves it. Return safe phase/count
information; never delete identities as compensation. Cancellation and ambiguous
network outcomes follow the same replay contract.

## Risks / Trade-offs

- Broader role catalog can silently enlarge content access: test admin isolation,
  analyst read-only corpus rights, delegated platform restrictions and I4/I5/I8.
- Public Python and import protections differ: enforce the stronger shared root
  rule and document this explicit difference in the import contract.
- Cross-system partial writes are unavoidable: exercise failures after each
  boundary and verify replay against real SQL/FGA, not only mocked call order.
- Long dependency calls block revocations while holding a mutation lock: use
  bounded timeouts and per-phase transactions; verify deterministic lock races.
- Unknown JSON fields are refused rather than silently ignored as Python can do:
  protect against misspelled grants; keep all defined user fields compatible.

## Migration Plan

Add model relations without renaming stored tuples. Deploy/sync the extended
model through the existing service initialization before invoking import.
Use new SQL migrations only if additional constraints/state prove necessary;
never modify applied migrations. Retain the operator-only `create-org` command
with its existing trust boundary; do not describe the new import restriction as
securing all operator/database access. Rollback must not delete identities or
tuples; do not run an older model that cannot interpret newly assigned roles.

## Delivery and documentation

Implement the role foundation as one complete reviewed/tested commit, then the
CLI import as a second complete reviewed/tested commit. Both belong to this one
provisioning outcome. After each implementation and independent correction review,
perform the arc42 documentation pass, regenerate blocks and check them. Keep all
plans and absent features out of the dossier. Each accepted review finding gets
a regression test and a reviewed fix. No push without explicit agreement.

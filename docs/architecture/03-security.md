# 3. Security

## Identity, consent and authority are separate

In the organization/team/project journey, Keycloak authenticates the person,
PostgreSQL records their personal terms-of-use (CGU) acceptance and OpenFGA decides
their rights.
A valid login is not consent; consent is not a role; platform ownership is
not membership of an organization. The following rules describe this journey's
manager authority, not a universal replacement for every Python security boundary.

## Authentication

| Aspect | Rule |
| --- | --- |
| Token | `Authorization: Bearer`, RS256 only, key chosen by `kid` among the realm's signing keys |
| Endpoints | Keycloak: `<realm>/protocol/openid-connect/certs`; OIDC: discovery, issuer must match the configured one |
| Identity | `sub` is the user id and the OpenFGA subject; roles from `resource_access.<client_id>.roles` or `roles_claim`; client from `azp` or `client_id`; service account recognised by case-insensitive `preferred_username = service-account-<client>` together with matching `client_id` or `clientId` |
| OIDC subjects | A non-UUID `sub` becomes `uuid5(NAMESPACE_URL, "<issuer>#<sub>")`; an empty `sub` is refused |
| Strict mode | `profile: c3`, or `FRED_STRICT_ISSUER` / `FRED_STRICT_AUDIENCE`: exact issuer (user and m2m realms), audience `audience` or `client_id` |
| Times | `exp` and an integer `iat` required, `iat` not in the future, `exp - iat` at most `FRED_JWT_MAX_LIFETIME_SECONDS` (3600), leeway `FRED_JWT_CLOCK_SKEW` (0) |
| Key cache | Keys kept 300 s; an unknown `kid` refetches at most once per 30 s, failures included, one fetch at a time, cached keys readable meanwhile; tokens are verified on every request |
| Disabled | `security.user.enabled: false`: every caller is the mock `admin`, client `local-dev`; `profile: c3` refuses to start that way |

401 answers carry a `WWW-Authenticate` header:

| Detail | `WWW-Authenticate` |
| --- | --- |
| `No authentication token provided` | `Bearer` |
| `Invalid token signature` | `Bearer error='invalid_token'` |
| `Token has expired` | `Bearer error='invalid_token', error_description='token expired'` |
| `Invalid token` | `Bearer error='invalid_token'` |
| `Token has invalid iat/exp claims` | `Bearer error='invalid_token', error_description='exp before iat'` |
| `Token lifetime exceeds the maximum permitted duration` | `Bearer error='invalid_token', error_description='token lifetime too long'` |
| `Invalid token claims` | `Bearer error='invalid_token'` |

## Personal CGU acceptance

Manager's public `/frontend/config` supplies authentication coordinates, the active
terms version and bootstrap state. `/me/onboarding` reports the authenticated
person's own acceptance. Both responses use `Cache-Control: no-store`; neither
returns the bootstrap secret.

`app.gcu_version: v1` enables consent in the reference and k3d configurations.
A nonempty version is at most 128 UTF-8 bytes, without surrounding whitespace or
control characters. `null`, an omitted version or disabled authentication removes
the gate. The frontend's localized legal markdown and the configured version are
deployed together; replacing text requires a version change.

`POST /gcu {version}` accepts only the caller's own human credential and the active
version. A stale version returns 409. Changing the displayed version reloads the
text and resets its reading state. Repeating acceptance of the same version keeps
its original timestamp. The [SQL record](A2-manager-contracts.md#fred-manager-schema)
contains subject, version and server timestamp, without roles or membership.

The server checks consent before business HTTP operations, bootstrap and authenticated
CLI import. Missing acceptance returns 403 `user_not_accept_gcu`, even for root.
Acceptance creates no default team, personal space or organization. Import never
accepts terms on behalf of its users. Fred's existing guards use manager state;
loading or unavailable admission does not mount business routes. The account menu
uses authenticated claims only and remains available to change accounts before
admission. Hiding unsupported navigation does not grant permission: its routes
also remain unmounted and the manager enforces each operation on the server.

Onboarding, acceptance and bootstrap reject service-account credentials, the
`service_agent` identity role and query parameters. Acceptance and bootstrap bodies
reject unknown fields, including asserted subjects. These operations act on the
verified caller only.

## Root bootstrap and its deployment secret

The bootstrap token proves possession of a deployment secret. It is distinct from
the person's Keycloak bearer and from manager's Keycloak service-client secret.
`app.bootstrap_token_env_var` names its environment variable; the reference uses
`FRED_BOOTSTRAP_TOKEN`. The k3d overlay sources it from `fred-secrets` key
`CONTROL_PLANE_BOOTSTRAP_TOKEN`. That shared secret location does not synchronize
Python and manager bootstrap records or roles.

A person first accepts CGU, then presents their bearer and this secret. Comparison
is constant-time; a token shorter than 16 characters is rejected with 422, a wrong
secret with 403. The secret cannot nominate another person or bypass consent. The first owner is
a real authenticated IAM person, not a local account created by the secret.

Manager commits a root reservation for that caller before the OpenFGA grant. A
failed grant can be retried only by the claimant. Once completion is recorded,
all later bootstrap attempts return 409, even if a role is subsequently removed.
Rotating the secret does not reset completion. Root receives platform ownership,
with no organization, team, project or personal-space membership.

The [reservation sequence](A1-manager-runtime.md#root-platform-admin-bootstrap)
shows the two transactions and failure recovery (I9). Afterwards root is an ordinary
platform owner: any platform owner grants or revokes platform owners, and the platform
always keeps one (I15).

## Roles, permissions and ReBAC

Roles are cumulative and granted on one space. Member grants content read; editor
grants content read and write. Analyst grants content read and the capabilities
`run_evaluations`, `manage_evaluation_corpus` and `read_conversations_for_evaluation`.
Admin grants space management and the first two evaluation capabilities, without
content read or evaluation-conversation read.
Editor, admin and analyst also apply to every descendant space; member applies to
its own space only (I20). A personal space has no parent and inherits nothing.
No platform role reaches a space.

The organization-only `personal_space_creator` role grants
`can_create_personal_space`, with no content access or inheritance. Organization
administrators manage it through existing role routes. Its recipient must hold a
direct content role on that organization; the last such role cannot be removed
while eligibility remains. Bundles enforce this dependency and publish content
before eligibility across batches. Creation requires eligibility and organization
read; reuse requires current organization and personal read, with no role writes.

Administration is business, ownership is technical. Each organization also has an
`owner` role: it names and removes the organization's admins and holds no content,
management or descending permission (I21). Platform owners name organization owners,
and an organization always keeps one (I14). New owner grants verify the subject in
the configured Keycloak realm; an unavailable directory prevents the grant. This
also applies to operator organization creation and import. Revocation accepts a
deleted identity so stale grants can be removed. The check proves existence at
lookup time; external IAM deletion is not transactional with OpenFGA. Teams and
projects have no owner.

Platform owner implies all platform capabilities. Feature manager grants
`manage_capabilities` and team registry listing; prompt editor grants
`edit_platform_prompt`; observer grants `observe_platform`. These grants do not imply
space membership or content access: a platform owner creates organizations and names
their owners, and creates teams only through an organization admin role.

Direct role tuples and the space tree are canonical in OpenFGA: each space carries
one immutable `parent` link. The model evaluates permissions, including roles
descending from ancestors; manager stores no inherited grant and computes no
permission. Manager enforces the parent-membership rule when changing roles: a role
on a child requires a direct content role on its parent, which inherited access
does not satisfy. Business access first verifies the caller's unique organization
context, then lets OpenFGA evaluate permission on the owning space. Resolving context
does not confer read or management authority (I23).

See the [space rules](04-organizations.md#spaces-and-memberships),
[generated model](A2-manager-contracts.md#openfga-model),
[administration endpoints](A1-manager-runtime.md#platform-administration-and-self-checks)
and [request costs](09-quality.md#openfga-request-costs).

## Mutation ordering and revocation

An organization lock serializes live callers. Each authorized mutation also
consumes an OpenFGA guard revision captured before its checks; a delayed remote
write cannot reuse a consumed revision. Platform operations acquire the platform
lock before organization locks. All direct space-role grants and revocations,
operator organization creation and import share this platform serialization and
guard, preventing competing assignments in different organizations. Team/personal
creation and content mutations retain their organization lock and guard. Role revocation cannot silently leave a child role,
or a personal space role in an organization, without a direct parent content role,
nor remove a non-personal space's last administrator.

I5 orders role publication and SQL commits, not HTTP response arrival. Keycloak
creation and Temporal submission are authorized at dispatch; cancellation or later
revocation does not roll back already dispatched effects. A read-only permission
check describes evaluation time, not a lease. The [runtime reference](A1-manager-runtime.md#role-and-space-mutations)
and [invariants](09-quality.md#invariants) give the mechanisms and proofs.

## Service identities

Manager resolves and creates provisioning identities with its own Keycloak client,
declared in `identities.yaml`. The operator bearer proves Fred authority; it is
never used as a directory administration credential. The
[directory boundary](A3-manager-operations.md#outbound-keycloak-directory) describes
realm/subject checks, retries and safe errors.

## Account lifecycle and platform admission

## Delegation and execution credentials

## Privacy and personal data

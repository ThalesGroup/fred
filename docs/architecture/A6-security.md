# Reference: security mechanisms and contracts

Technical companion to [Security](03-security.md), for Fred developers and coding
assistants. It preserves authentication, consent, authorization, publication and
lifecycle mechanisms for the Control Plane organization/team/project path.
The [action and role matrix](A7-action-role-matrix.md) details individual permissions.
These contracts do not establish identical behavior for every other Fred service.

## Identity, consent and authority are separate

In the organization/team/project journey, the configured Keycloak or OIDC provider authenticates the person,
PostgreSQL records their personal terms-of-use (CGU) acceptance; Control Plane decides
their rights.
A valid login is not consent; consent is not a role; platform administration is
not membership of an organization. The following rules describe this journey's
manager authority, not a universal replacement for every Python security boundary.

## Authentication

| Aspect | Rule |
| --- | --- |
| Token | `Authorization: Bearer`, RS256 only, key chosen by `kid` among the realm's signing keys |
| Endpoints | Keycloak: `<realm>/protocol/openid-connect/certs`; OIDC: discovery, issuer must match the configured one |
| Identity | The configured UID claim (default `sub`) identifies the user and authorization subject; roles from `resource_access.<client_id>.roles` or `roles_claim`; client from `azp` or `client_id`; service account recognised by case-insensitive `preferred_username = service-account-<client>` together with matching `client_id` or `clientId` |
| OIDC subjects | A non-UUID configured UID becomes `uuid5(NAMESPACE_URL, "<realm_url>#<identity>")`; an empty UID is refused |
| Issuer and audience | Always required: exact issuer (user and m2m realms), audience `audience` or, by default, `client_id` |
| Times | `exp` and an integer `iat` required, `iat` not in the future, `exp - iat` at most `FRED_JWT_MAX_LIFETIME_SECONDS` (3600), leeway `FRED_JWT_CLOCK_SKEW` (0) |
| Key cache | Keys kept 300 s; an unknown `kid` refetches at most once per 30 s, failures included, one fetch at a time, fresh cached keys readable meanwhile; when a refresh fails or waits for its cooldown, a known `kid` keeps verifying for at most 3600 s after its last successful fetch, and a successfully fetched set always replaces the cache; tokens are verified on every request |
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
its original timestamp. The [SQL record](A2-manager-contracts.md#control-plane-sql-catalogue)
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
secret with 403. The secret cannot nominate another person or bypass consent. The first platform admin is
a real authenticated IAM person, not a local account created by the secret.

Control Plane grants the first platform-admin role and records bootstrap completion
in one SQL transaction under the platform lock. Once complete, later bootstrap
attempts return 409, even if a role is subsequently removed. Rotating the secret
does not reset completion. Root receives no business membership.

Afterwards platform administrators manage platform roles, while preserving at least
one administrator.

## Roles, permissions and ReBAC

The [action/role matrix](A7-action-role-matrix.md) enumerates every manager HTTP
action, operator entry point and evaluable permission, including additional gates. The following explains the security model.

The [roles annex](A11-roles.md) defines the complete role inventory, inheritance
(I20), owner/content separation (I21), required organization admins and owners
(I14), and attribution constraints. It distinguishes the agreed responsibilities
from the permissions currently enforced. Teams and projects have no technical admin role.

Every direct space-role grant checks, after authorization, that its subject is
usable as an authorization subject (1..255 characters
without whitespace, `:` or `#`) and known to the configured user directory: Keycloak by
subject, or the local directory of observed profiles. Otherwise it answers 422; an
unavailable directory prevents the grant (I27). Owner grants additionally require
Keycloak subjects in the configured realm, which import also verifies. Revocation accepts a
deleted identity so stale grants can be removed. The check proves existence at
lookup time; external IAM deletion is not transactional with PostgreSQL.

Personal-space eligibility is checked against direct organization content
membership. Provisioning publishes content grants before eligibility across batches;
reuse of a personal space writes no new role. See the
[role-attribution rules](A11-roles.md#attribution-accumulation-and-removal).

Direct role grants and immutable hierarchy live in PostgreSQL. The typed Rust
permission evaluator applies local roles and the descending editor, owner and
analyst roles; personal spaces inherit nothing. Child role grants require direct
parent content membership. Business access also checks the person's unique
organization context, which itself grants no content access.

See [permission storage](A2-manager-contracts.md#permission-storage-and-evaluation)
and [role semantics](A11-roles.md).

## Mutation ordering and revocation

Mutations acquire the relevant SQL advisory locks before checking authority,
and retain them through commit. Role changes and content writes use the same
organization serialization; platform changes acquire the platform lock first.
Checks and role writes use that transaction's connection. A successful revocation
therefore precedes subsequent decisions without a second authorization service.

No mutation may remove the last required administrator or owner, or leave dependent
child grants without direct parent content membership. External Keycloak operations
remain authorized at dispatch and do not participate in the SQL transaction.
A permission probe is an observation, not a lease.

## Business authorization answer

Every business route on a space, including folder, document, processing, scope,
team/project and personal-space routes, answers one way (`spaces::authorize`): a
missing space, or one outside the caller's organization, returns 404; then a retired
space returns 409 `space_pending_deletion`; then a missing permission returns 403.
Writes evaluate the same rule on the connection that holds the organization lock.
Role grants and revocations keep their own role rules and report retirement only
after them. Authorization probes answer `allowed: false` for each of these refusals.

## Original-document boundary

Directory, receipts and downloads use private/no-store responses and follow the
business authorization answer above. Provider and authorization dependency failures
return a safe 503 rather than granting access.

An upload checks space write permission before consuming its body, then checks
current organization, permission, token expiry and CGU under the organization lock
at reservation and publication. A revocation committed during object IO prevents
publication. Receipts belong to the initiating actor and also require current space
read authority; an admin receives no implicit receipt access.

Object keys use document UUIDs and a validated filename, not user-supplied paths. Downloads
use manager authentication and attachment/octet-stream/nosniff headers. MIME and
filename metadata are not trusted for execution or rendering. The autonomous cleanup
loop retains no user token: SQL journal, published rows and the durable `fred-installation` object marker
constrain its deletions; only strict document `input` keys are candidates.
The [document chapter](05-documents.md) describes that state machine.

## Processing authority and publication

Worker callbacks require a signed service-account token with the exact configured
issuer, audience and client, independently of the browser profile. Human bearer
tokens cannot use this protocol. Manager binds callbacks to installation, document,
original digest, accepted actor and stage generation; serialized worker user claims
confer no authority. Original access and final publication recheck that actor's
current organization, space Write permission and CGU. Publication uses the same
organization lock and transaction-local checks as other content writes, after remote artifact
verification. Failed-stage fencing remains possible after actor revocation.

Previews use current reader authority, allowlisted manifest paths, bounded streams,
private/no-store and nosniff headers. Browser rendering suppresses remote embeds
and active content. The worker's object credentials cover only `output` paths in
the shared documents bucket; original bytes are obtained through manager. The
manager API writes `input` and reads both zones. Its lifecycle/dispatch worker
has no object-store credential. The factory uses separate auxiliary credentials
for KF objects/filesystem and a scoped OpenSearch account. Local SeaweedFS IAM
object rules reject bucket requests carrying a forged `prefix`; its worker list
permission requires an output prefix. Provider enforcement is part of deployment,
not inferred from application path validation. Workflow histories and safe
public errors carry no bearer tokens, storage secrets or provider diagnostics.

## Service identities

Manager resolves and creates provisioning identities with its own Keycloak client,
declared in `identities.yaml`. The operator bearer proves Fred authority; it is
never used as a directory administration credential. The
[directory boundary](A3-manager-operations.md#outbound-keycloak-directory) describes
realm/subject checks, retries and safe errors.

## Account lifecycle and platform admission

In this manager journey, a valid personal credential from the configured issuer
allows access to onboarding. After accepting the active CGU, a person with no
organization or platform roles can reach an empty Home view. This creates no
membership, personal space or content access. Business operations still require
one organization context and the operation's Control Plane permission; platform actions
require their separate platform permission.

Python control-plane additionally has configurable platform-access filtering and
admission sources. Manager's onboarding checks authentication and consent, not
that Python admission policy. A deployment using Python filtering therefore does
not retain equivalent platform admission merely by directing the UI to manager.
This security boundary is distinct from organization membership and from CGU.

## Space retirement and cleanup authority

`platform.can_delete_space` is computed from `platform_admin` only. Request and receipt APIs
require real authentication and CGU admission, including for receipts whose target
no longer exists. Deletion grants no content access. Organization administration and
space administration confer no implicit deletion power.

Acceptance checks authority after acquiring the platform lock and capturing its
revision, then locks the organization, verifies the scope and fences both guards.
All retired descendants are marked in the same SQL transaction. Mutation waiters
recheck retirement after their lock; reads already authorized may finish. Existing
role revocation remains an immediate role operation without a purge request.
The worker executes the accepted durable scope without retaining a user token.
Remaining grants on retired rows still count towards the unique organization
attachment, using `space.organization_id` throughout retirement.

## Managed agent turn authority

Companion to [model permission and conversation access](03-security.md#35-model-permission-and-conversation-access).
Browser preparation does not grant execution. The Agent Pod authenticates the
person, checks conversation ownership and resolves one complete context from
Control Plane at turn admission. Control Plane verifies the person's space access,
template-use permission, instance lifecycle and conversation association.

A trusted workload authenticates with its own service credential and identifies
the person, run and instance it acts for. These asserted fields are accepted only
from configured delegation callers; service roles never replace the person's
roles. The returned context binds person, canonical space, instance, conversation
and model policy. The pod enforces that context locally for the admitted turn;
policy changes are observed at the next admission, not by per-model-call refresh.
Cancellation and closed-run checks remain effective within the turn.

| Boundary | Implementation reference |
| --- | --- |
| Trusted delegation and canonical binding | [`agent_instances/runtime.rs`](../../apps/control-plane/src/agent_instances/runtime.rs), `RuntimeQuery::subject`, `resolve_runtime` |
| Identity, session and one turn resolution | [`agent_app.py`](../../libs/fred-runtime/fred_runtime/app/agent_app.py), `_authorize_and_resolve`, `_resolve_agent_instance` |
| Local lifetime and context checks | [`model_routing/turn.py`](../../libs/fred-runtime/fred_runtime/model_routing/turn.py), `TurnAuthority` |
| Selection and preparation diagnostics | [Model contract](A2-manager-contracts.md#chat-model-preparation-and-turn-admission) |

This describes the managed chat boundary. External-tool authorization and HITL
are not connected under it.

## Document search within a turn

Capabilities call Knowledge Flow API with the canonical space bound to the turn.
The API validates the incoming workload and asserted person. It then calls Control
Plane once for the readable scope, using its own M2M bearer and the validated
person/run/agent triplet. It does not forward the Agent Pod's bearer.

Control Plane returns an explicit anchor and the exact readable subset of its
ancestors and itself. An empty corpus remains empty. The API applies document
selection only as a further restriction; attachments use the explicit anchor and
separate conversation ownership checks.

Index filters narrow candidates. Before returning content, the shared visibility
primitive checks SQL publication, lifecycle and generation facts. Markdown,
summary, extraction and tabular access use the same scope boundary. A dependency
failure returns an unavailable error, never an unrestricted or fabricated empty
success. These data checks do not refresh the admitted agent turn's authority.

Source references: [`weaver_admission.py`](../../apps/knowledge-flow-backend/knowledge_flow_backend/security/weaver_admission.py),
[`access.py`](../../libs/fred-core/fred_core/documents/access.py),
[`authorization.rs`](../../apps/control-plane/src/authorization.rs) and
[`spaces.rs`](../../apps/control-plane/src/spaces.rs).

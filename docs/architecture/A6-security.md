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
person's admission from existing roles and their own acceptance. Both responses use `Cache-Control: no-store`; neither
returns the bootstrap secret.

`app.gcu_version: v1` enables consent in the reference and k3d configurations.
A nonempty version is at most 128 UTF-8 bytes, without surrounding whitespace or
control characters. `null`, an omitted version or disabled authentication removes
the gate. The frontend's localized legal markdown and the configured version are
deployed together; replacing text requires a version change.

`POST /gcu {version}` accepts only the caller's own human credential and the active
version, after platform admission. A stale version returns 409. Changing the displayed version reloads the
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

### Independent platform initialization

This is the admission boundary for a new Weaver installation, including one sharing
an SSO with Swift. Authenticating an existing SSO subject is not a user import.
Before initialization, reading onboarding status or preferences performs no identity
snapshot or user-state insertion. CGU acceptance, preference writes and business
handlers refuse with `platform_bootstrap_required`. No new table or migration is
introduced for this feature.

The installer presents their verified human bearer and the installation secret.
An existing Swift platform-admin role provides no authority for this claim: the
secret must belong to the Weaver installation. The shared SSO subject is reused,
while Weaver's role grant is independent and leaves Swift's grant unchanged.
Comparison is constant-time; a short token is rejected with 422 and a wrong secret
with 403. A successful claim grants only the caller's platform-admin role and records
completion in one SQL transaction under the platform lock. Concurrent claims cannot
elect two initial administrators. The local directory, when configured, snapshots
only the successful claimant at this point. Root receives no organization, team or
content membership. Later bootstrap attempts return 409; neither removing a role
nor rotating the secret reopens initialization.

The UI identifies the currently connected account and offers the existing sign-out
operation to select another one. The SSO session may be shared with Swift, so signing
out can also end that provider session; a separate browser profile isolates the test.
CGU follow successful initialization and remain required before protected operations.
Subsequent users retain the normal personal-consent and role checks; this increment
is not a general user-provisioning or Swift migration mechanism.

| Boundary | Owner and persistent effect |
| --- | --- |
| Read the current SSO identity | [`OwnUser` in onboarding.rs](../../apps/control-plane/src/onboarding.rs); read-only authentication |
| Block writes before initialization | `require_admitted`, reused by `AdmittedUser`, CGU acceptance and preference PATCH |
| Claim the first platform role | [`bootstrap_platform_admin` in api.rs](../../apps/control-plane/src/api.rs), [`grant_root` in bootstrap.rs](../../apps/control-plane/src/bootstrap.rs); existing `platform_bootstrap` and `platform_role_grant` tables |
| Personal consent and preferences | Existing `terms_acceptance` and `users_preferences`; no rows created by simply visiting the UI |
| Optional local directory | [`snapshot` in users.rs](../../apps/control-plane/src/users.rs); existing `user_identity` remains a display cache, not an account or permission authority |
| UI sequence | [`OnboardingGuard`](../../apps/frontend/src/rework/core/guards/OnboardingGuard.tsx) replaces the two separate guards; [`BootstrapPage`](../../apps/frontend/src/rework/components/pages/BootstrapPage/BootstrapPage.tsx) reuses the existing secret form and sign-out service |

Focused evidence: `consent_and_root_bootstrap_are_personal_and_do_not_create_memberships`
in [`integration.rs`](../../apps/control-plane/tests/integration.rs) checks a foreign
SSO visitor and the claimant against a disposable database, including the local-directory
mode; the other bootstrap tests cover concurrency and permanent completion. UI ordering,
refresh/error handling and logout are covered by
[`Onboarding.test.tsx`](../../apps/frontend/src/app/Onboarding.test.tsx) and
[`OnboardingGuard.test.tsx`](../../apps/frontend/src/rework/core/guards/OnboardingGuard.test.tsx).
These focused checks do not establish end-to-end production SSO or migration validation;
the changed browser journey still needs functional validation on the deployed images.

After initialization, platform administrators manage platform roles while preserving
at least one administrator.

## Roles, permissions and ReBAC

The [action/role matrix](A7-action-role-matrix.md) enumerates every manager HTTP
action, command-line entry point and evaluable permission, including additional gates. The following explains the security model.

The [roles annex](A11-roles.md) defines the complete role inventory, local scope
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

Personal-space eligibility and the published-snapshot marketplace share one
organization-participant predicate: a direct business role on an active collective
space, with active organization and parent. The Rust matrix supplies the role sets
bound by SQL lists. Invitations supply no rights and have no persisted tables.
Provisioning publishes content grants before eligibility across batches; reuse of
a personal space writes no new role. See the
[role-attribution rules](A11-roles.md#attribution-accumulation-and-removal).

Direct role grants and immutable hierarchy live in PostgreSQL. The typed Rust
permission evaluator applies only roles granted on the requested space; no role
reaches a child. Personal spaces inherit nothing. Child role grants require direct
parent content membership. Business access also checks that the person holds a direct
role in the target's organization, which itself grants no content access.

See [permission storage](A2-manager-contracts.md#permission-storage-and-evaluation)
and [role semantics](A11-roles.md).

## Mutation ordering and revocation

Mutations acquire the relevant SQL advisory locks before the final authority check,
and retain them through commit. Role changes and content writes use the same
organization serialization; platform changes acquire the platform lock first.
Checks and role writes use that transaction's connection. A successful revocation
therefore precedes subsequent decisions without a second authorization service.

Role grants authorize the caller before looking up the target identity, without
retaining a SQL connection or transaction during the directory call. They recheck
authority and business constraints under the mutation locks before writing; a
revocation committed during the lookup prevents the grant. Identity existence
remains an observation at lookup time, not protection against later IAM deletion.

No mutation may remove the last required administrator or owner, or leave dependent
child grants without direct parent content membership. External Keycloak operations
remain authorized at dispatch and do not participate in the SQL transaction.
A permission probe is an observation, not a lease.

## Business authorization answer

Every business route on a space, including folder, document, processing, scope,
team/project and personal-space routes, answers one way (`authorization::authorize`): a
missing space, or one outside the caller's organization, returns 404; then a retired
space returns 409 `space_pending_deletion`; then a missing permission returns 403.
`load_facts` reads placement, activity, organization context, participation and
direct roles in one SQL statement; `decide` is a pure Rust decision. Reads and writes
use the same executor-generic `authorize` function. Organization-only operations use
`authorize_organization`, which rejects another space kind with 404 before any access
decision. `spaces::authorized_mutation` acquires the organization lock and returns
both the transaction and the authorized space; its organization target uses
`authorize_organization`. The lock stays held through commit. A pool authorization
before this boundary is retained when it protects external discovery before the lock.
Role grants and revocations keep their governance rules and platform-then-organization
lock order, but now apply the common context, retirement, permission precedence.
Organization-admin assignment still requires explicit platform authority. Authorization probes answer `allowed: false` for each of these refusals.

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
declared in `identities.yaml`. The initiating platform admin's bearer proves Fred authority; it is
never used as a directory administration credential. The
[directory boundary](A3-manager-operations.md#outbound-keycloak-directory) describes
realm/subject checks, retries and safe errors.

## Account lifecycle and platform admission

A valid personal credential from the configured issuer allows read-only onboarding.
Admission requires an existing platform role or a direct role in an active organization,
team or project; an orphaned personal space or an old CGU acceptance does not suffice.
Space activity includes its organization and parent. No separate admission record is stored.

The local directory requires explicit registration through the deployment CLI before the first role
assignment; observing a shared SSO session does not register the person. Registration
stores only a profile in the existing directory and grants no access or consent.
See the [registration procedure](../../apps/control-plane/README.md#admit-a-user-with-the-local-directory).

After platform initialization, an unadmitted person sees an access-unavailable message
before the CGU. The API rejects consent, preference writes and business requests with
403 `user_not_admitted`. The initial administrator can still claim the first platform
role through bootstrap. Disabling CGU does not disable admission; local deployments
with authentication disabled retain their development behavior.

The frontend rechecks onboarding every minute and when its window regains focus,
so a revoked last role also closes an already open view. Each new protected API
request checks current admission independently of this display refresh.

Admission grants no additional permission. Business operations still require their
direct space roles, and platform actions require their separate platform permission.

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
Remaining grants on retired rows still count towards organization attachment,
using `space.organization_id` throughout retirement.

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

The Python SDK carries the admitted space explicitly in `RuntimeContext`,
`PortableContext` and `CapabilityIdentity`; `team_id` is ancestry only. The in-thread update store
checks that space against the conversation history when accepting a message or
retrying its identity. An expiring database lease admits one active turn per conversation
and guards its checkpoint and final history writes; lease loss stops the turn,
and steering addresses the active turn. History and
checkpoint owner metadata record it without granting access: the existing
`binding_json` provenance and Control Plane checks still govern conversation
reads. Missing provenance is never inferred from retention metadata. See the
[runtime schema notes](../../libs/fred-runtime/fred_runtime/migrations/README)
for the immutable space migration and the replacement of the steering mailbox
by conversation-owned history. Deployment acceptance for this replacement remains
in the [integration record](../../WEAVER_SWIFT_PORTAGE_A_REPRENDRE.md#16-integration-swift-du-9-novembre-2026).

| Boundary | Implementation reference |
| --- | --- |
| Trusted delegation and canonical binding | [`agent_instances/runtime.rs`](../../apps/control-plane/src/agent_instances/runtime.rs), `RuntimeQuery::subject`, `resolve_runtime` |
| Identity, session and one turn resolution | [`agent_app.py`](../../libs/fred-runtime/fred_runtime/app/agent_app.py), `_authorize_and_resolve`, `_resolve_agent_instance` |
| Local lifetime and context checks | [`model_routing/turn.py`](../../libs/fred-runtime/fred_runtime/model_routing/turn.py), `TurnAuthority` |
| Selection and preparation diagnostics | [Model contract](A2-manager-contracts.md#chat-model-preparation-and-turn-admission) |

This describes the managed chat boundary. External-tool authorization and HITL
are not connected under it.

## Document search within a turn

Control Plane resolves the exact readable corpus at turn admission, alongside the
canonical space, person, instance and conversation. The Agent Pod retains that
scope in its private turn authority and carries it in the existing document-context
header over HTTP and MCP. Browser and model selections can only narrow it.

Knowledge Flow accepts this context only after verifying workload authentication
and the asserted person/run/agent. It trusts the delegated pod to relay Control
Plane's decision and enforce turn lifetime; it does not independently prove the
admission or refresh the person's permissions on each document call. Revocation
and new grants affect the next admission. An empty corpus remains empty;
attachments retain their explicit anchor and separate conversation ownership checks.

Index filters narrow candidates. Before returning content, the shared visibility
primitive reads only Control Plane-owned `cp_read` views. The SQL `visible` fact
combines publication and lifecycle: no first-publication content is available,
while a previous published generation remains available during reprocessing unless
retirement or search-inclusion state makes it unavailable. Python applies the
authorized corpus, explicit selection and conversation ownership, then verifies
chunk ordinals against the published generation. It does not reconstruct lifecycle
policy or read the Control Plane tables. Markdown,
summary, extraction and tabular access use the same scope boundary. A dependency
failure returns an unavailable error, never an unrestricted or fabricated empty
success. These data checks do not refresh the admitted agent turn's authority.

Source references: [`weaver_admission.py`](../../apps/knowledge-flow-backend/knowledge_flow_backend/security/weaver_admission.py),
[`access.py`](../../libs/fred-core/fred_core/documents/access.py),
[`authorization.rs`](../../apps/control-plane/src/authorization.rs),
[`runtime.rs`](../../apps/control-plane/src/agent_instances/runtime.rs) and
[`turn.py`](../../libs/fred-runtime/fred_runtime/model_routing/turn.py).

### Runtime CGU dependency inventory

With `security.user.enabled` and `app.gcu_version` configured, runtime's explicit
`app.security.current_user` dependency reads `cp_read.terms_acceptance` after
`fred_core.security.oidc.authenticate_request` verifies JWT and delegation.
It checks the effective person's canonical ID and configured version; missing
acceptance returns 403 `user_not_accept_gcu`, SQL failure returns a redacted
503 `terms_acceptance_unavailable`, and an unconfigured version skips the read.
Admission uses no dependency override or Python identity snapshot/store.
The following paths are relative to the pod's configured base URL (normally
`/fred/agents/v2`). A future removal must preserve JWT/delegation verification,
effective-person binding and the current errors independently of the SQL read.

| Method | Route | Is consent checked again by the Control Plane resolver? |
| --- | --- | --- |
| POST | `/agents/execute` | Yes, `_authorize_and_resolve` before execution |
| POST | `/agents/execute/stream` | Yes, `_authorize_and_resolve` before streaming |
| POST | `/agents/evaluate` | Yes, `_authorize_and_resolve` before evaluation |
| GET | `/agents/skills` | Yes, public runtime resolution in `get_instance_skills` |
| GET | `/agents/skills/{skill_name}` | Yes, via `get_instance_skills` |
| GET | `/agents/kpi-turns` | No turn resolution |
| GET | `/agents/audit-events` | No turn resolution |
| GET | `/agents/web-research/activity` | No turn resolution |
| DELETE | `/agents/web-research/activity/users/{user_id}` | No turn resolution |
| POST | `/agents/creation-assistant/draft` | No turn resolution |
| POST | `/agents/capabilities/{capability_id}/validate-config` | No turn resolution |
| POST | `/agents/capabilities/{capability_id}/copy-config` | No turn resolution |
| POST | `/agents/capabilities/{capability_id}/export-config` | No turn resolution |
| POST | `/agents/capabilities/chat-controls` | No turn resolution |
| GET | `/agents/sessions` | No turn resolution |
| GET | `/agents/sessions/{session_id}/messages` | No turn resolution |
| DELETE | `/agents/sessions/{session_id}` | No turn resolution |
| DELETE | `/agents/sessions/{session_id}/filesystem` | No turn resolution |
| GET | `/agents/checkpoints` | No turn resolution |
| GET | `/agents/checkpoints/_stats` | No turn resolution |
| GET | `/agents/checkpoints/{session_id}` | No turn resolution |
| DELETE | `/agents/checkpoints/{session_id}` | No turn resolution |
| POST | `/agents/sessions/{session_id}/steer` | Checks conversation ownership and execution authorization; stores an in-thread message without starting a turn |
| GET | `/capabilities/writable_document/sessions/{session_id}/documents` | No turn resolution |
| GET | `/capabilities/writable_document/sessions/{session_id}/documents/{document_id}` | No turn resolution |
| PUT | `/capabilities/writable_document/sessions/{session_id}/documents/{document_id}` | No turn resolution |
| GET | `/capabilities/writable_document/sessions/{session_id}/documents/{document_id}/export` | No turn resolution |
| POST | `/capabilities/ppt_filler/analyze` | No turn resolution |
| POST | `/v1/chat/completions` (absolute, optional compatibility router) | No; execution remains explicitly unsupported |

Installed capability routes mounted under `/capabilities/{id}` inherit the same
CGU dependency at mounting; `writable_document` handlers separately bind the
common authenticated identity and keep their owner checks. Its OpenAPI-only
wrapper is not a served application. The default pod's five capability routes
are listed above. Additional installed packages contribute their own paths and do not
implicitly resolve a turn. The five resolver-backed routes above are candidates
for eliminating the duplicate local read in a later change, not permission to
remove admission from the remaining routes. This inventory follows
`app/agent_app.py`, `skills/api.py`, `app/openai_compat_router.py` and
`apps/control-plane/src/agent_instances/runtime.rs::resolve`.

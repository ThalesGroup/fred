## Context

See [proposal.md](proposal.md) for motivation and [the delta spec](specs/platform-access-control/spec.md) for acceptance.

Observed on parent `06d71e0bf85b6e9638505d85a4bafbbdca5c5a56`:

- `fred_core.security.oidc.decode_jwt` already verifies tokens, maps configured claims and caches decoded principals. `resolve_request_principal` applies the legacy file whitelist before account-status enforcement; it is also used outside the ordinary HTTP dependencies.
- The IdP branch records minimal human profiles in `users`, including before CGU acceptance. The existing profile-write throttle is ten minutes and cannot serve as a live admission cache.
- Runtime SQL initialization already installs a user store. Control plane and Knowledge Flow also use asynchronous SQL engines. Configured production/developer Compose deployments share PostgreSQL; standalone runtime defaults can use their own SQLite database.
- Team metadata is shared SQL state; effective membership is OpenFGA state. `team_member` includes established member roles. `can_read` can come from public visibility and is unsuitable as admission evidence.
- Ordinary `POST /teams/{id}/join` requires a fully admitted user and `joining_mode=OPEN`. A private team cannot be OPEN. Free enrollment therefore needs its own narrow operation, without changing either existing invariant.
- `/user` returns a personal team as well as CGU state, and `/gcu` currently joins default teams on first acceptance. Neither is a safe blanket admission exemption.
- Public `/frontend/config` precedes protected bootstrap. Static branding already defines `contactSupportLink`; the new refusal page must resolve support without loading product state.

## Goals / Non-Goals

**Goals:** extend the shared authentication dependencies, user store and team registry; preserve the existing authorization engine and service lifecycle; keep live exceptions authoritative across replicas.

**Non-Goals:** new IdP integrations, additional platform roles, storing whole JWTs, a replicated in-memory allowlist, or an inventory of unrelated personal attributes. Third-party backends that do not use Fred security are not automatically protected by this feature.

## Decisions

### Configuration and two-stage activation

Add `security.platform_access` to the shared security configuration:

```yaml
security:
  platform_access:
    enabled: false
    jwt_claim: []
    accepted_regex: null
    supportLink: null
```

`enabled` installs this feature and its admin surface; a persisted `filtering_enabled` switch starts false and activates enforcement. This separates operator readiness from administrator cutover and allows T0 preparation before denial starts. Enabled mode requires human auth, local user-directory mode, OpenFGA and the shared admission database. Enabled configuration requires a nonempty sequence of claim keys, a nonempty compilable regex and an absolute HTTPS support URL. Disabled omitted fields remain valid.

The canonical Helm block is `global.platformAccess`, rendered into the three backend security blocks, with matching local YAML examples. Site-specific claim paths, accepted expressions and support destinations are supplied by private deployment overlays. Public defaults/examples, documentation, issue/PR wording and commit messages contain no customer or organization-specific rules. It must not coexist with enabled `global.whitelist`, and startup must also detect a nonempty file whitelist in non-chart deployments. Retain the old mode when the new feature is disabled; do not silently import a legacy email file into UUID exceptions.

Compile once at startup. Use whole-value matching with bounded attribute size, array length and a matcher deadline; a timed-out match cannot establish eligibility. Declare the timeout-capable regex dependency explicitly rather than relying on the transitive `regex` entry already present in `fred-core/uv.lock`. Read only the selected attribute from the verified payload and keep it excluded from public principal serialization and logs.

Publish `supportLink` on public `FrontendConfig`. When configured, it also feeds the existing `useFrontendProperties().contactSupportLink` consumer; otherwise retain the static branding fallback. This avoids two different support destinations within an enabled deployment.

### Durable state, owned by control plane

Use one additive control-plane migration, based on the actual parent migration head:

| State                                                                           | Storage                                   | Authority                          |
| ------------------------------------------------------------------------------- | -------------------------------------------------- | ---------------------------------- |
| Filtering state, policy fingerprint and completed T0 marker                     | Singleton `platform_access_settings`               | Control plane                      |
| Individual user exceptions, manual/T0 origin and grant metadata                 | `platform_access_users`, keyed by stable user UUID | Control plane                      |
| Team authorization and Free flags, hashed enrollment token                      | Additive team-metadata columns                     | Platform access admin service only |
| Selected verified attribute, claim-path fingerprint and token observation times | Additive internal user columns                     | Verified human requests only       |

Bind admission reads to the existing asynchronous SQL engine and schema guards in each participating backend. Only control plane initializes the singleton or changes its policy fingerprint. Other readers require the initialized authority and matching configuration fingerprint; missing authority, schema or inconsistent policy fails closed. Enabled services must point to the same database. Independent standalone SQLite databases are not a supported enabled deployment; SQLite remains useful for single-authority unit fixtures.

The gate reads filtering state and exceptions on each request. Do not cache mutable admission decisions in `_JWT_CACHE`, profile-write throttles or process-local state. A disabled persisted filter still needs a successful authority read in enabled mode. Read shared state and short-circuit claim/individual sources, then a higher-consistency membership check only for relevant authorized teams if claim/individual sources do not already admit the person. Membership checks must use effective `team_member`, not public `can_read`; reuse existing bounded batch-check facilities (50 targets per batch). Do not derive denial from ListObjects enumeration, which can be truncated by server limits.

Manual and T0 are individually managed exceptions. Team/Free sources are derived from current flags and actual membership and projected in the whitelist view with team ID/name. Do not copy Free membership into permanent manual entries: deriving it avoids synchronization races and makes flag removal, departure and team deletion revoke the source immediately. Paginate users and bound projection concurrency to eight; release ordinary SQL sessions before membership I/O. Do not load every roster on each request.

### Verified attributes and delegated people

Direct human requests evaluate their current verified token. Persist the selected scalar/string-array observation, path fingerprint, `iat` and `exp` only when a newer token generation is observed, independently of the identity profile throttle. An older token cannot overwrite newer evidence; equally issued contradictory evidence fails closed. Never persist the raw bearer or unrelated personal claims.

For an asserted/delegated person, use their individual/team sources or re-evaluate their latest verified attribute observation under the current regex. The observation must use the configured claim path and remain within its original verified token lifetime. A missing/expired observation is not a claim match. The workload's own attributes and service marker cannot establish the person's eligibility. This retains the existing delegation envelope without copying a human token into a workload or turning a configured attribute match into a permanent exception.

After caller/subject resolution, enforce existing suspension, then platform admission, then the applicable CGU/resource checks. Cover all public resolution callers, including runtime query-token paths and SDK/first-party security consumers. Pure service calls retain their existing checks; only established workload identities qualify for that branch. Any consumer enabled for this feature must initialize the same authority; do not assume the browser gate protects directly reachable endpoints.

### Explicit T0 snapshot and live administration

Expose the access page at `/admin/platform-access` under the existing platform-admin navigation and permission hooks. All new administrative operations use `OrganizationPermission.CAN_MANAGE_PLATFORM`, independently of directory/team picker permissions.

Control-plane surface under `/admin/platform/access`:

| Operation                                               | Purpose                                                                             |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `GET` and `PATCH`                                       | Read policy summary/state; explicitly change `filtering_enabled`                    |
| `GET /users`, `PUT /users/{uid}`, `DELETE /users/{uid}` | Paginated provenance view and individual exception edits                            |
| `GET /t0-preview`, `POST /t0-import`                    | Preview and commit the one-time snapshot                                            |
| `GET /teams`, `PATCH /teams/{id}`                       | Team authorization and Free controls                                                |
| `POST /teams/{id}/enrollment-link`                      | Generate/rotate a link; return its plaintext token only in this authorized response |

Use Fred's local user table for selection even when normal directory consumers use other sources; do not provision IdP accounts or accept arbitrary emails as identities. Reject personal teams for team-based exceptions and Free enrollment. Access flags cannot be written by normal team metadata PATCH, import, generic relation APIs or a team-manager route.

T0 takes an atomic database snapshot once and records completion in the same transaction. Include current human records without reliable claim evidence; skip people demonstrably matched by a still-valid observation. Report totals and existing exceptions without storing another inventory file. An idempotent retry returns the existing completion; it never restores deleted exceptions or imports users registered afterward. Suspended identities remain suspended regardless of any T0 entry.

Serialize policy mutations with the existing PostgreSQL advisory-lock pattern. Before activation or an access-admin mutation that withdraws the acting administrator's last source, evaluate the resulting policy and refuse self-lockout. This safeguard does not prevent a person voluntarily leaving a team or another authorized administrator revoking their access. Existing secret-gated, one-time root bootstrap remains independent and does not become a general recovery bypass. Operator rollback can disable the feature if all admins lose admission.

### Bounded Free enrollment

Use a standalone browser route `/join-free/:token`, retaining the route through the existing OIDC login redirect. Mint an opaque random token, store only its hash, and rotate it whenever explicitly requested or Free is removed/re-enabled. A minimal authenticated link-preview response exposes only the target team's name and legal/enrollment state. Resolve the target from the token; never accept a client-selected user, role or alternative team.

Add narrowly scoped own-credential dependencies that verify authentication and suspension while omitting platform admission. Only self-status, valid-link preview/enrollment and necessary CGU acceptance use them. The ordinary `get_current_user_without_gcu` paths keep admission enforcement; do not globally weaken all pre-CGU endpoints.

`GET /platform-access/status` returns only admission and CGU state for the caller, records their verified local profile and does not resolve/provision a personal team. Adapt the CGU guard to this minimal state when the feature is enabled. The denied enrollment flow accepts CGU through a dedicated operation scoped to the valid link, without enrolling default teams; the normal `/gcu` route remains admission-gated before its existing default-team side effects.

Enrollment rechecks the live Free flag/link, account status and CGU under the same team-policy advisory lock used for Free mutations/deletion. It grants only the caller's effective member relation through the existing membership writer and uses its higher-consistency token. The derived Free whitelist source then follows that membership. Retries are idempotent; enrollment racing Free removal cannot return a durable admitted result after the flag is removed. Free does not change visibility or ordinary `joining_mode`; a private team remains undiscoverable to strangers without its link.

### Refusal UX and errors

Normal admission denial is `403 / platform_access_denied`. Authority/configuration read failures are `503 / platform_access_unavailable`. Match only the specific denial detail in frontend API handling and the managed-runtime request consumers. Render `/platform-access-denied` outside `MainLayout`, protected bootstrap and CGU guards, with localized support wording, the validated public support link, retry and sign-out actions. Clear protected cached product state when entering denial so old data is not retained in the shell.

Do not use `/coming-soon` for the new policy; it remains the legacy-file landing page. Preserve 401 renewal, CGU refusal and other resource-permission errors. Free enrollment renders independently of the shell and refetches admission/bootstrap after successful membership.

## Risks / Trade-offs

- Extra admission reads add request latency - reuse async engines, short-circuit eligibility sources and review bounded batches; never trade revocation freshness for a long decision cache.
- The selected attribute is personal data - retain only that field, redact serialization/logging and keep identity administration permission-gated. No collection of unrelated personal attributes.
- A delegated run whose only claim observation expires needs fresh human evidence - refuse new delegated requests until a new verified observation or exception exists. Work already authorized is not retroactively cancelled.
- A denied person can appear in the local directory after authentication - identity discovery is not admission, and only explicit T0 completion defines grandfathering.
- Previously used identities absent from Fred's database cannot be grandfathered by this import - operators must verify local inventory coverage before cutover; no production collection occurs in this PR.
- Shared-store or policy mismatch outages deny access - fail closed with a distinguishable 503 and document deployment ordering and rollback.

## Migration Plan

1. Deploy the additive control-plane migration and matching service/chart code with feature enablement off. Keep parent IdP migration ancestry linear.
2. For optional activation, confirm all participating readers use the shared database, matching policy and local directory. Supply claim/regex/support settings and transition away from any legacy file gate explicitly.
3. Enable the feature configuration, leaving the durable filtering switch off. Confirm administrator admission sources, preview/import T0, adjust individual/team exceptions, and configure desired Free teams/links.
4. Activate filtering in platform administration. Validate matching, grandfathered, new external, Free-enrollment and revocation journeys across direct and delegated requests.
5. Roll back optional enforcement by disabling the durable filter while admin access remains, or operator feature enablement if necessary. This reopens admission intentionally and retains exception data. Code rollback requires compatible shared libraries/chart settings; retain additive tables/columns until all readers have been rolled back.

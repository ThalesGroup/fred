---
schema: 1
title: "Activate configurable platform admission and live user/team exceptions"
impact: minor
configuration: production
configuration_reason: "Removes admission deployment settings; authenticated readers require the shared migrated authority and suspended-account model."
---

## Applicability

Applies to authenticated deployments with enforced ReBAC and either the Keycloak or local user directory. Administration is available after migration; filtering starts inactive. Admission policy is separate from resource authorization.

## Prerequisites

The configurable identity-provider/local-directory support is included in this standalone change. Admission readers require authenticated users and workloads, a Keycloak or local user directory, enforced OpenFGA with a finite timeout, and the same shared PostgreSQL database in every participating backend. Publish and select an OpenFGA model carrying `organization.suspended` on every reader before rollout, including Keycloak deployments without delegation. Migrate control plane before starting readers. Standalone SQLite admission is unsupported.

## Configuration

There is no admission-specific deployment configuration. Remove `security.platform_access`, `global.platformAccess` and `FRED_PLATFORM_ACCESS` from earlier draft deployments; they no longer initialize, enable or override admission. Keep the existing `security.user_directory` choice and a finite `security.rebac.timeout_millisec` (the default is 5000). Configure support through the existing frontend `properties.contactSupportLink` and remove earlier draft `supportLink` fields. Keep actual identity values and support destinations outside public examples.

First-party backends using the shared ReBAC SDK must pass their shared PostgreSQL engine to `rebac_sdk_factory(platform_engine=...)`. They are readers and cannot initialize the authority. A legacy file whitelist can continue while SQL filtering is inactive; remove it before activating the new filter. Activation refuses concurrent gates, and readers fail closed if a conflicting legacy gate appears while filtering is active.

## Upgrade

1. Back up the shared database and apply control-plane Alembic head. This PR adds one revision, `f9a2c7d81e40`, following `aac66348e27b`. It adds selected internal identity evidence, versioned policy settings, a claim-name/type catalog, individual exceptions and team enrollment state with independent links and aggregate authenticated opening counters. This revision is still part of this unreleased PR. If an isolated development database already applied an earlier draft of `f9a2c7d81e40`, recreate that disposable database from migrations; do not stamp it to conceal schema drift. Preserve a backup and use an explicit data-preserving migration for any database that must retain its data.
2. Deploy control plane first; it initializes the SQL authority once with filtering inactive. Deploy runtime and Knowledge Flow with the same shared database. An absent authority starts with no policy, revision zero and filtering inactive; restarts preserve saved settings. Missing or incompatible authority fails closed with 503.
3. In **Platform access**, use **Choose an account field** to select a root text attribute from your verified current session or another observed name. Protocol metadata, arrays and nested paths are hidden by default; **Show advanced fields** restores the complete picker. Select nested or literal dotted keys through the advanced explorer; there is no manual path input. Current-value copying is explicit. Add up to 16 conditions, choose AND/OR and literal contains/not-contains/equals/not-equals or advanced whole-value regex. Literal comparison ignores case by default; the case toggle is explicit. Test against your own verified token, then save. Missing, empty or incompatible claims fail predicates too. Discovery lists supported names/types observed in human tokens, not the full IdP schema or other people's values.
4. In **Platform access**, explicitly import existing users (T0). Unknown existing classifications receive removable exceptions. This import completes once; retries never restore removed entries or include subsequent registrations.
5. Add independent user/team exceptions as needed, then enable filtering. Select up to 100 existing Fred users across searches/pages for an atomic manual grant. Authorize members derives access from current team membership instead of copying users into permanent exceptions; removing a member withdraws that source on their next direct or delegated request. Activation requires a saved rule. The acting administrator must retain a valid source; activation, active rule saves and access-policy self-lockout are refused. A stale save returns 409 and preserves the newer policy and the administrator's draft. If recovery is necessary, explicitly disable the persisted SQL filtering switch, then repair the saved rule or independent sources in the UI. An operator can recover a locked-out administrator with `UPDATE platform_access_settings SET filtering_enabled = false WHERE id = 1;`; this deliberately widens admission.
6. For bounded demonstration enrollment, enable Free on a non-personal team and generate its opaque link. Preserve team visibility/joining policy. Handle the link as a capability; share it only with intended participants. Generate multiple independent invitations with optional notes and expiration; previous invitations remain valid until revoked, expired or suspended. Removing Free suspends links and withdraws the team-derived access source; restoring Free resumes unrevoked, unexpired links. Revoke individual links in history to prevent future enrollment. Existing membership and independent sources remain. A valid link permits deliberate re-enrollment after member removal, so revoke it if re-enrollment must be prevented. History counts authenticated opening signals, not anonymous clicks, unique people or message delivery; repeated submitted signals count again. Administrators can reveal the original URL. Recoverable capability tokens are stored in SQL: protect the database and backups accordingly. Ordinary history excludes tokens; creation/reveal require own-human platform-management credentials and disable HTTP caching.

The own-claims picker requires the matching control-plane and generated frontend client. It adds no migration or deployment setting; the endpoint is administrator-only, uncached and does not persist its bounded payload. Admission errors reuse the shared Fred error presentation.

## Validation

Check a matching person, an imported person, a newly denied person and a valid Free enrollment. The denied, Free and profile screens must use the same `contactSupportLink` before protected bootstrap. Check direct and delegated calls, suspension, required CGU acceptance, and revocation with the same JWT through a different replica. Confirm missing/incompatible authority produces `platform_access_unavailable` (503), rather than the definitive denial (403).

## Rollback

Disable persisted filtering through the administrator UI to suspend policy enforcement while retaining exceptions and team state. If the UI is unavailable, explicitly disable the SQL filtering switch as above. Keep ordinary authentication, suspension and resource authorization enforced. This widens admission and is an explicit operator choice. Do not downgrade the additive migration while a participating backend is running. A schema downgrade removes admission state and selected attribute observations; restore the database backup to recover them.

## Limitations

Verified selected evidence used for delegated people expires with its human access token. A newly selected claim without a stored observation also requires a fresh direct human request; a predicate-only edit can reuse compatible unexpired evidence. Cached direct JWTs retain bounded internal facts and evaluate the current saved rule on every request. An independent live source remains sufficient. Admission revocation affects subsequent requests, not already authorized work. All participants must share the PostgreSQL policy authority; independent databases are unsupported. Mask `/platform-access/free/<token>` and `/join-free/<token>` in ingress/proxy logs as Fred does in its own access logs. Four-replica production load and private IdP/Helm overlays require operator validation.

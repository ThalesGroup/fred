---
schema: 1
title: "Activate configurable platform admission and live user/team exceptions"
impact: minor
configuration: production
configuration_reason: "Adds disabled security.platform_access defaults and canonical global.platformAccess Helm values, shared across control plane, runtime and Knowledge Flow."
---

## Applicability

Applies to deployments opting into platform admission control on top of the configurable IdP/local-directory feature. Ordinary upgrade keeps the feature disabled. Admission policy is separate from resource authorization.

## Prerequisites

Apply the parent identity-provider change first. Enabled admission requires authenticated users and workloads, the local Fred directory, enforced OpenFGA with a finite timeout, and the same shared PostgreSQL database in every participating backend. Migrate control plane before starting enabled readers. Standalone SQLite admission is unsupported.

## Configuration

Set `global.platformAccess` in the private deployment overlay. It is the canonical chart policy and overwrites each backend's `security.platform_access` block. Defaults:

```yaml
global:
  platformAccess:
    enabled: false
    jwt_claim: []
    accepted_regex: null
    supportLink: null
```

For activation, supply `enabled: true`, a list of nested JWT keys, a whole-value regular expression and an HTTPS support URL. A string or any member of a string array can match; unsupported or oversized values cannot. Never put real deployment attribute values or support destinations into public examples. Do not enable `global.whitelist` or retain a nonempty legacy whitelist file alongside this feature.

First-party backends using the shared ReBAC SDK can supply the equivalent JSON block in `FRED_PLATFORM_ACCESS`; pass their shared PostgreSQL engine to `rebac_sdk_factory(platform_engine=...)`. They are readers and cannot initialize policy authority.

## Upgrade

1. Back up the shared database and apply control-plane Alembic head. This PR adds one revision, `f9a2c7d81e40`, following `aac66348e27b`. It adds internal identity evidence, settings, individual exceptions and team enrollment state.
2. Deploy control plane with the configured policy first; it initializes the authority with filtering inactive. Deploy runtime and Knowledge Flow with the identical policy/database. Old or mismatched enabled readers fail closed with 503 until reconciled.
3. In **Platform access**, explicitly import existing users (T0). Unknown existing classifications receive removable exceptions. This import completes once; retries never restore removed entries or include subsequent registrations.
4. Add independent user/team exceptions as needed, then enable filtering. The acting administrator must retain a valid source; activation and access-policy self-lockout are refused.
5. For bounded demonstration enrollment, enable Free on a non-personal team and generate its opaque link. Preserve team visibility/joining policy. Handle the link as a capability; share it only with intended participants. Rotation invalidates previous links for new enrollments. Removing Free clears the link and its access source; existing membership and independent sources remain.

## Validation

Check a matching person, an imported person, a newly denied person and a valid Free enrollment. The denied page must display the configured support link before protected bootstrap. Check direct and delegated calls, suspension, required CGU acceptance, and revocation with the same JWT through a different replica. Confirm missing/mismatched authority produces `platform_access_unavailable` (503), rather than the definitive denial (403).

## Rollback

Disable persisted filtering through the administrator UI to suspend policy enforcement while retaining exceptions and team state. Setting feature enablement false on all backends restores the previous admission behavior; keep ordinary authentication and resource authorization configured. This widens admission and is an explicit operator choice. Do not downgrade the additive migration while an enabled backend is running. A schema downgrade removes admission state and selected attribute observations; restore the database backup to recover them.

## Limitations

Verified attribute evidence used for delegated people expires with its human access token. A fresh human request or another live source is then required. Admission revocation affects subsequent requests, not already authorized work. All participants must share policy and PostgreSQL; independent databases are unsupported. Mask `/platform-access/free/<token>` and `/join-free/<token>` in ingress/proxy logs as Fred does in its own access logs. Four-replica production load and private IdP/Helm overlays require operator validation.

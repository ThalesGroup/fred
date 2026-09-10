## Context

See [proposal.md](proposal.md) for the feature scope. Applications use a
dedicated authorization type and existing configuration/catalog administration.
A separate app-only lifecycle subsystem is not required to deliver that feature.

## Goals / Non-Goals

**Goals**

- Keep configuration-based app registration and typed, team-scoped admission.
- Preserve existing entitlement controls and independently useful security fixes.
- State deployment and lifecycle limitations without claiming automated recovery.

**Non-goals**

- App-wide Deactivate/Delete, config-removal permission cleanup or fresh-registration generations.
- An app lifecycle registry, reconciliation command, global active marker or database permission revisions.
- UI lifecycle controls, agent enrollment, Workspace implementation or downstream object permissions.
- Deployment, live-service modification or automatic migration of existing authorization state.

## Decisions

### D1 — Separate authorization and catalog identifiers

Registration and SDK calls use the validated raw `app_id`. Administration
continues using `app__<app_id>`; tuple operations resolve that entry to
`app:<app_id>`. Invalid identifiers are rejected, not repaired into another
resource. Runtime capability manifests remain limited to their existing kinds.

This reuses the shared catalog without giving an application the authorization
or execution behavior of a capability with a similar identifier.

### D2 — Reuse configuration and entitlement controls

An enabled entry in `platform.application_sources` is registered in the catalog.
Configured applications remain admin-gated and startup seeding does not write
their authorization tuples. An authorized entitlement mutation establishes the
typed organization anchor. Catalog registration and an anchor alone grant no
team access.

The app model is:

```text
inherited = team from default_on
can_use = (enabled or inherited) but not disabled
can_manage = platform_admin from organization
```

There is no `active` marker or additional lifecycle adoption prerequisite.
Existing platform-admin enable, team disable, reset and default-on controls
continue to work. Default-on OFF does not revoke explicit team grants; reset
may restore inherited access. A catalog-hidden but still configured app
retains supported revocation, while new grants remain refused.

These operations do not enter agent dependency, impact, suspension, revival,
settings or model-binding paths. Personal app grants and personal-class controls
remain forbidden; stale personal tuples can still be revoked.

### D3 — Keep membership and fresh app authorization separate

Check the user's selected-team membership before querying app entitlement or
returning app metadata. Public visibility and platform administration are not
membership. Personal teams are excluded locally.

Discovery and first-party app checks request higher consistency from the
authorization engine. This protects ordinary revocation and deny visibility
without a catalog/database call in the SDK request path. Administration
relation caches never serve as admission decisions.

### D4 — Preserve typed, process-local administration caches

Use the existing typed cache keys and invalidation markers. Retain monotonic
invalidation tickets and invalidation in `finally` after attempted writes,
including partial failure. A concurrent invalidation must prevent an older
fill from becoming a reusable cache entry.

These caches are process-local presentation optimizations with the existing
expiry policy. They do not promise cross-replica instantaneous display freshness,
distributed write serialization or an atomic read/write snapshot. No durable
permission-revision registry is introduced for apps alone. Shared lifecycle
work must revisit those guarantees where needed.

### D5 — Retain independent security hardening

Keep exact validated resource mapping, personal-space restrictions, authorization
before metadata/writes, and the narrow fail-closed first-party SDK. Its startup
requirements and process-lifetime client ownership remain unchanged.

Keep bounded, paginated, exact-reference cleanup for existing callers such as
team removal. Failure to reach completion is explicit; the primitive does not
supply app lifecycle authority or exclude concurrent distributed writers.

Keep identifier-free operational messages on touched authorization, seeding,
cleanup and database-construction paths. Failure logging must not attach raw
provider exceptions or connection details. Synthetic canary tests cover the
changed sinks; this is not a claim that every logging path in the repository
has been audited. Offline tests use test-owned storage rather than user data.

### D6 — Preserve downstream trust boundaries

The frame receives no raw bearer. The host forwards it only to the application
service, which validates the caller before entitlement. An arm's-length backend
checks the authenticated team catalog; an operator-admitted first-party backend
uses the narrow SDK with its own configured authentication and authorization
credentials.

App access does not grant agent capability, managed-instance, corpus-object or
Workspace access. Downstream owners enforce their own permissions through their
APIs. The planned Workspace execution-binding contract remains separate.

## Deferred gap — shared resource lifecycle

Global **Deactivate**, later **Activate**, and **Delete** must be designed in a
future cross-resource change covering all or most applicable ReBAC types.
Not every type has identical ownership, inheritance or deletion semantics;
the applicable types and exceptions require an explicit design.

That future work must establish:

- Desired-state authority and any config/UI precedence.
- Global denial that overrides retained grants and inherited defaults.
- Safe removal detection, ownership/inventory and deliberate-removal confirmation.
- Whether and how retained settings survive deactivation and reactivation.
- Exact permission cleanup, re-registration semantics and unrelated-resource protection.
- Interrupted/uncertain-write recovery, stale-writer protection and rollout safety.
- Cache freshness, mixed-version behavior and operational verification across replicas.

The future lifecycle design has no selected storage mechanism or per-type
migration. Generic cleanup hardening does not establish lifecycle guarantees.

**Current limitation:** `enabled: false` and removal from configuration affect
catalog availability; neither guarantees global first-party denial nor deletion
of stored grants/defaults. Re-adding an identifier can reuse surviving permissions.
Revoke entitlement through existing controls and restrict routes when required;
catalog disappearance alone is not a security boundary.

## Risks / Trade-offs

- Similar catalog identifiers could target the wrong type → validate exact
  identities and keep tuple/cache keys typed; never use a legacy-grant fallback.
- Catalog withdrawal can be mistaken for revocation → retain explicit operator
  warnings and the deferred shared lifecycle gap.
- Presentation caches can lag another replica → keep admission on fresh engine
  checks and avoid describing display caches as authorization.
- A stolen backend authorization credential is not scoped by the SDK's narrow
  interface → retain the documented first-party trust and provisioning boundary.
- Incompatible deployed schema or authorization-model revisions can prevent a
  safe rollout → verify compatibility before deployment and stop for a separately
  approved state-preserving migration plan when incompatible state is present.

## Migration Plan

No deployment or data migration is executed by this change.

For the existing no-legacy-state app-type cutover:

1. Fence application administration writers and drain their in-flight requests.
2. Verify absence of semantic legacy `capability:app__<app_id>` relations.
   Grants, denies and defaults block this cutover; an inert organization anchor
   alone does not. Stop for a separate migration design if semantic state exists.
3. Publish/verify the app-aware model and update every pinned reader/writer.
4. Drain incompatible replicas and repeat the legacy-state check before reopening.
5. Verify membership, explicit/default entitlement, deny precedence, personal-space
   exclusion and absence of legacy fallback through each supported trust tier.

Rollback after new app grants exist requires explicit state preservation.
Verify that deployed database revisions and authorization models are supported
by the target version. Incompatible schema, model or authorization state requires
a separately approved state-preserving migration before deployment. No automatic
database downgrade or authorization-state migration is provided.

## Local Evidence

- [Product contract](../../../docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md#46-contract-notes--team-applications-are-runtime-registered-frame-hosted-uis-2026-08-31)
- [ReBAC guide](../../../docs/swift/platform/REBAC.md)
- [Authorization model](../../../libs/fred-core/fred_core/security/rebac/schema.fga)
- [Application helpers](../../../libs/fred-core/fred_core/security/rebac/application_authz.py)
- [SDK](../../../libs/fred-core/fred_core/security/rebac/rebac_sdk.py)
- [Verification map](verification.md)

The verification map distinguishes executed checks from outstanding live
integration and deployment verification.

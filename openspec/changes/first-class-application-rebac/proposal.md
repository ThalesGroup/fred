## Why

Applications need a dedicated authorization resource without becoming agent
capabilities. Configuration-based registration and the existing entitlement
controls provide that boundary without an application-specific lifecycle system.

## What Changes

- Authorize applications as `app:<app_id>`, retaining `app__<app_id>` for the
  shared catalog and administration routes.
- Register enabled applications through existing deployment configuration.
  Registration populates the catalog without creating authorization tuples.
- Require team membership and explicit or default-on app entitlement; an
  explicit team deny wins. Preserve personal-space exclusion and agent independence.
- Preserve the narrow first-party SDK, higher-consistency app admission reads,
  typed administration caches, mutation invalidation and sensitive-log protections.
- **BREAKING:** app checks and writers use the dedicated resource type without
  falling back to legacy capability-app grants. The documented cutover requires
  absence of semantic legacy state.
- Exclude app-wide Deactivate/Delete, automatic permission cleanup on config
  removal, lifecycle tables, recovery commands and lifecycle-specific cache revisions.
  These require a separate cross-resource design, recorded in the
  [deferred shared lifecycle gap](design.md#deferred-gap--shared-resource-lifecycle).

## Capabilities

### New Capabilities

- `application-rebac`: configuration-based registration, typed app admission,
  administration, security boundaries and explicit lifecycle limitations.

### Modified Capabilities

None. Agent, model, tool, team and Workspace authorization contracts remain
unchanged by the app-type feature.

## Impact

- Shared authorization model/helpers/SDK and control-plane catalog,
  administration and startup seeding.
- Existing API shapes and frontend behavior remain; no new UI lifecycle controls.
- No application lifecycle database migration or reconciliation deployment job.
- Generic security fixes remain where they protect existing authorization,
  cleanup, logging and offline verification paths independently of app lifecycle.
- [Requirements](specs/application-rebac/spec.md), [design](design.md),
  [tasks](tasks.md) and [verification](verification.md) describe the feature,
  implementation evidence and outstanding checks.
- The [product contract](../../../docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md#46-contract-notes--team-applications-are-runtime-registered-frame-hosted-uis-2026-08-31),
  [ReBAC guide](../../../docs/swift/platform/REBAC.md) and
  [configuration guide](../../../docs/swift/platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md)
  retain the warning that catalog removal is not global revocation or permission cleanup.
- Deployment, migration of populated legacy grants, and the separately planned
  Workspace contract remain outside this change.

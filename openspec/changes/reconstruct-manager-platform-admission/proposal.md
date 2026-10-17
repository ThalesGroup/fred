## Why

Manager currently verifies human identity and consent without evaluating Python's platform-admission policy. The user approved documenting this gap and reconstructing admission in a separate lot; its absence is not an approved security-policy change.

## What Changes

Prepare the manager reconstruction of the existing admission contract while retaining the UI, one-person/one-organization model and separate OpenFGA content authority. Implementation is not authorized by this proposal alone: the decisions below determine its buildable scope.

The parity inventory includes inactive-by-default durable policy/revisions; allow/block rules and verified evidence; manual/T0 exceptions; authorized teams and Free-link provenance; fresh platform-management bypass; own-human status, consent and enrollment exceptions; exact refusal/error contracts; current authority across replicas and delegated consumers; administration, preview, audit and link lifecycle.

Pausing filtering must preserve rules and grants without suspending authentication, account-status checks, consent or resource authorization. No UI controls may be enabled against a partial implementation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: preserve the established admission behavior through manager entry points and affected consumers.
- `fred-manager-provisioning`: integrate admission with explicit organization attachment and existing scoped authority, without synthesizing undeclared grants.

## Impact

Manager authentication/onboarding, policy persistence/configuration, generated contracts and existing UI guards; affected Python/runtime admission consumers and migration ownership. Canonical space/platform grants remain in OpenFGA. This preparation is part of reconstruction issue #3092; implementation tracking follows the agreed scope.

## Decisions required before design and implementation

1. **Organization enrollment:** define an invitation's explicit organization grants and behavior for unattached versus already-attached people. Free access cannot silently create a second organization or bypass parent-role prerequisites. Cover concurrent enrollment/import/grants.
2. **Authority and data ownership:** choose reuse/mapping of existing Python settings, exceptions, removals, links, joiners, user evidence and team flags. Reconcile Python team ids with manager space UUIDs before adding tables or parallel policy stores.
3. **Enforcement boundary:** identify authoritative active-account and delegated-evidence sources and all callers. Gating manager's consent extractor alone does not protect runtime or delegated Python paths. Classify public, own-status, bootstrap, legal and enrollment exceptions explicitly.

## Evidence and acceptance preparation

Independent read-only review at `738768468` confirmed the gap in `onboarding.rs`, `/me/onboarding` and frontend configuration. The capability `platform-access-control` must be read with active changes `team-join-link`, `refresh-t0-before-filtering`, `whitelist-lists-individual-exceptions` and `condense-platform-access-admin-screens`: current code includes provenance-based Free enrollment and explicit T0 refresh beyond the main spec's older wording.

Primary sources: `libs/fred-core/fred_core/security/platform_access/{access_control,store,models}.py`, `apps/control-plane-backend/control_plane_backend/platform_access/`, `apps/frontend/src/common/platformAccess.ts`, manager `onboarding.rs` and arc42 chapters 03/04.

The subsequent design must inventory existing tables first, preserve `403 platform_access_denied` versus `503 platform_access_unavailable`, keep fresh authority and revision/lockout protections, and specify exact OpenFGA request budgets, pagination, SQL lock boundaries and fixture/concurrency evidence. No admission code, migration or UI behavior changes are included in this preparation.

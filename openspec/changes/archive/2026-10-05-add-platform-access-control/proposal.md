## Why

Fred deployments need to restrict new registrations using an IdP attribute while preserving explicitly approved users and demonstration teams. Fred must own these editable admission exceptions so operators do not have to rebuild images or edit Keycloak roles.

Tracking: GitHub issue #2965. This change is stacked on PR #2863, using its local user directory; it does not extend that PR's provider-portability scope.

## What Changes

- Add opt-in platform admission configuration: a verified JWT claim path, acceptance regex and `supportLink`, in developer YAML and Helm values. Matching is provider-independent. Deployment-specific attribute paths, accepted values and support destinations belong in privately maintained Helm overlays; repository defaults and examples remain generic.
- Add a platform-admin access page with a live filtering switch, individual exceptions selected from Fred users, authorized teams, and the Free-team flag. Enabling the configuration makes administration available; filtering is initially inactive until explicitly activated by an administrator.
- Provide an explicit, atomic T0 import of existing Fred users. Entries remain individually removable, and later registrations are not grandfathered automatically.
- Admit a person through a matching claim, an individual exception, or current membership of an authorized team. Preserve independent admission sources and existing account suspension, CGU and resource permissions.
- Provide an authenticated direct enrollment link for a Free team. Record the user/team source only after successful enrollment. Withdraw that source when the person leaves or Free is removed; ordinary authorized teams do not become open to enrollment.
- Enforce admission on direct and delegated human requests across participating backends. Shared durable state makes exception edits effective on the next request without token renewal or process restart.
- Route denied people to a standalone localized error page with the configured support link. Authentication, enrollment and support remain reachable without exposing the platform directory or product bootstrap.
- Keep omitted configuration compatible with existing deployments. Explicitly configured database filtering replaces the legacy file gate on those deployments; reject simultaneous activation rather than applying conflicting policies.

## Capabilities

### New Capabilities

- `platform-access-control`: configured admission policy, live administrator-managed exceptions, explicit T0 grandfathering, Free-team enrollment and refusal behavior.

### Modified Capabilities

None. Existing provider configuration, local identity snapshots and account suspension remain prerequisite contracts. No shipped capability currently specifies platform admission exceptions.

## Impact

- Shared security and storage: `libs/fred-pod` typed configuration and `libs/fred-core` verified claims, request principal resolution, users and team metadata. Extend existing asynchronous store/engine lifecycles.
- Control plane: platform administration routes, identity snapshot and CGU flow, team lifecycle, bootstrap safeguards and one additive Alembic migration based on the parent branch's head.
- Runtime and Knowledge Flow: shared admission-store initialization and direct/delegated enforcement. Enabled deployments must use the same authoritative admission database and policy.
- Frontend: public `FrontendConfig.supportLink`, generated client, access administration, a bounded enrollment route and standalone access-denied page.
- Deployment: local `configuration_prod.yaml` files, Helm configuration and regenerated schemas; one operator migration note describing optional activation, T0 import, legacy whitelist transition and rollback.

## Non-Goals

Collecting deployment-specific user inventories, querying a production IdP, creating an external inventory system, provisioning IdP accounts, hardcoding organization identities, and granting new team/resource roles are outside this change. The gate retains only its configured attribute, not arbitrary JWT personal data.

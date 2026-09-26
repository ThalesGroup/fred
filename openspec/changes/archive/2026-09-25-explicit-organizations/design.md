## Context
The ReBAC schema and `ORGANIZATION_ID = "fred"` currently combine platform governance and organization scope. Team metadata has no organization field. Control-plane startup already reconciles team/organization edges under a lock; bootstrap persists administrative grants. See proposal.md for scope.

## Goals / Non-Goals
Preserve the single-organization deployment with a small backend evolution. No generic tenancy framework, duplicated team registry, frontend work, or filesystem changes.

## Decisions
- Persist organization identity in a new control-plane `organizations/` feature; extend existing team metadata with its organization reference instead of introducing parallel teams. Keep global team-name uniqueness.
- Preserve `organization:fred` and existing resource IDs. Keep the existing `platform_admin` grants on `organization:fred` as the platform authority and add explicit `organization_admin` grants on each organization; scope team-registry administration and the editable prompt to organizations rather than renaming every existing resource or granting platform-wide inheritance.
- Keep memberships and administrative grants authoritative in ReBAC. Reuse existing services and migrations; organization context must reach authorization, data filtering and cache keys, not just route parameters.
- Resolve omitted organization context to `fred` for legacy APIs, subject to the same authorization checks; no unrestricted fallback when another organization is selected.
- Keep technical deployment settings, model bindings, Keycloak account management, global analytics and import/export/reset platform-owned. Organization admins manage their team registry and organization prompt. Existing administrative functions backed by global state must be classified and scoped before exposing them to organization administrators; never delegate a global mutation through a nominally scoped gate.
- Reject deletion of `fred` or non-empty organizations in this slice; cascading erasure is separate work. No transfers or cross-organization sharing.

## Risks / Trade-offs
- SQL and ReBAC are not one transaction → use retryable, locked initialization with durable migration progress; mark administrator migration complete only after grants succeed.
- Singleton assumptions extend into contextual tuples, discovery, capabilities and admin services → inventory those call sites and cover cross-organization access, while retaining default behavior.
- Backend-only delivery cannot add an organization selector → preserve existing default-scope routes and expose explicit scope through backend APIs.

## Migration Plan
1. Add organization persistence and the default record; backfill community teams without changing IDs or resource ownership. Display-name configuration defaults to `Fred`.
2. Retain existing platform-administrator grants on `fred`; give their captured holders an additional `organization_admin` grant on `fred`. Preserve delegated roles and bootstrap-admin access; future platform-only grants do not inherit organization rights.
3. Reconcile from stored team assignments, never from the singleton assumption. Verify repeated and interrupted startup, including personal/system team paths.
4. Release verification uses a representative pre-upgrade fixture. Retain old data and authorization grants during migration; document the supported recovery procedure before rollout. Do not claim an old binary is safe after additional organizations exist.

## Organization prompt compatibility
Move the saved prompt to organization scope and preserve `fred` content, including saved empty strings. Keep legacy API/wire names for default clients; resolve scope server-side from team metadata for execution. Only `fred` retains the shipped legacy fallback when no prompt was saved; a new organization starts with an empty prompt. No parallel global editable prompt remains.

## Membership and terms
An explicit ReBAC `organization#member` relation survives team changes. Existing team/admin memberships remain recognized for compatibility and are materialized on authenticated onboarding. Users with no organization enter `fred`; preassigned users retain their organizations. Organization admins may grant membership through a scoped backend endpoint. Bootstrap and first terms acceptance initialize membership; self-join also checks it for direct API callers. Default-team enrollment filters by organization. CGU configuration, user acceptance storage and admission checks remain global and unchanged.

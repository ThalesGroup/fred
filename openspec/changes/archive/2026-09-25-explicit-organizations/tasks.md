## 1. Persistence and authorization
- [x] 1.1 Classify singleton gates, global admin state, contextual tuples and personal/system-team paths; verify a compact permission mapping accounts for every existing administrative surface before changing its scope.
- [x] 1.2 Add organization persistence, default-name configuration and community-team association using existing stores/migrations; verify upgrade fixtures preserve IDs, memberships and resource links.
- [x] 1.3 Separate platform lifecycle permissions from organization administration and adapt scoped helpers; verify an organization administrator cannot acquire platform or other-organization powers.

## 2. Compatible bootstrap and APIs
- [x] 2.1 Implement locked, retryable default-organization/admin migration and assignment-aware reconciliation; verify old admins retain both roles across restart/interruption without replaying revoked grants.
- [x] 2.2 Add minimal organization lifecycle/admin APIs and scope existing administration/team APIs, filtering and caches; verify default clients still work, cross-organization calls fail and protected/non-empty deletion is rejected.

- [x] 2.3 Migrate the saved prompt into organization scope and bind execution to the team organization; verify distinct prompts, explicit empty values and default-organization fallback through unchanged runtime fields.

## 3. Production acceptance
- [x] 3.1 Add focused upgrade and two-organization regressions, including direct IDs, discovery, delegated roles and personal/system teams; execute the agreed checks and record results.
- [x] 3.2 Update only relevant backend contracts and deployment instructions with optional display-name configuration and recovery limits; verify the documented default upgrade requires no manual role edits or UI changes.
- [x] 3.3 Review the implementation for isolation and migration compatibility, address findings and record evidence before archiving; run repository checks only under the agreed test-execution policy.

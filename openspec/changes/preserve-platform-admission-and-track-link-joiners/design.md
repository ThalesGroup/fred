## Context

See proposal.md. The shared SQL setting already has `filtering_enabled`, and both the API and page offer disabling; the existing backend path does not clear the policy or exceptions. Free links currently store only opening aggregates. Enrollment writes team membership in OpenFGA under a control-plane SQL mutation, but has no per-link join record. All participating backends call the shared `PlatformAccess` admission service. The current specification explicitly avoids visitor identity analytics; a successful join is a separate event.

## Goals / Non-Goals

**Goals:**

- Make the open-access state and retained configuration explicit and regression-tested across the admin UI and shared admission path.
- Use live ReBAC platform authority for the administrator admission source, including delegated-person requests and role removal.
- Attribute new successful membership grants to their specific Free link and display current local user profile fields to platform administrators.

**Non-Goals:**

- Backfill joiners for existing links: opening aggregates cannot identify them.
- Capture visitors, IPs, arbitrary token claims, or a historical snapshot of user profile fields.
- Change team membership semantics, resource authorization, or the link-opening aggregate.

## Decisions

### 1. Keep the existing filtering switch

Use the current SQL boolean, versioned API mutation and top-right UI action. Add focused regression coverage for disable, open access and re-enable with the same stored rule and exceptions. No new switch or migration is needed for this part. A separate bypass configuration would create a second authority and complicate reactivation.

### 2. Check the current platform permission inside shared eligibility

`PlatformAccess.eligible` will check the subject UID against the organization `can_manage_platform` permission with higher consistency before evaluating the rule and team sources. The same method is used by direct admission, delegated admission, activation preview and actor-lockout safeguards. A removed role therefore stops granting access on the next request. The check accepts both human and delegated person principals, never a service account's own role. Authorization failures remain unavailable-authority errors; they are not treated as a non-admin result. A local user flag or token role would be stale after role changes.

### 3. Persist one join record per link and person

Add one `platform_access_link_joiners` table in a single control-plane migration. Its composite link/user key prevents duplicate attribution, `joined_at` records first successful enrollment through that link, and foreign keys cascade on link-history or user deletion. The control-plane enrollment path writes the record only when it creates the caller's team-member relation. An existing member opening another link is not attributed to it. If the person later leaves and explicitly rejoins through a different link, both links retain their respective history. The existing SQL mutation and link validity check serialize the join with revocation and cleanup; preserve the existing rollback behavior when the membership grant fails.

Read joiners by team and link ID under the existing platform-admin dependency, with bounded server pagination and stable `joined_at`/user-ID ordering. Join `users` at read time to show current first name, last name and username; no duplicate profile values are stored. The endpoint returns no token and excludes unrelated teams. The existing link manager gets a localized row action that opens a joiner list with loading, empty, error and pagination states. It remains accessible for revoked, expired and suspended links.

A separate joiner table is preferable to extending the opening aggregate: visits and joins have different meanings and retention. It also avoids trying to infer origin from current team membership, which loses provenance when a member leaves.

## Risks / Trade-offs

- [OpenFGA and SQL are separate authorities] -> Keep the record creation within the existing serialized enrollment mutation after a successful relation grant, test grant failure and rollback, and surface any commit failure. A cross-system failure between the relation grant and SQL commit may require operator reconciliation; the current enrollment path already has this boundary.
- [Live administrator checks add a ReBAC call on active-filter requests] -> Use the existing shared client and bounded timeout, exercise concurrent admission tests, and review request-path impact before readiness. Correctness after role revocation takes priority over token-local caching.
- [New history contains personal data] -> Restrict it to platform administrators, store only link/user IDs and join time, derive names from current profiles, and cascade it on explicit link-history and identity deletion. Do not add it to logs or opening analytics.
- [Old links have no attributable history] -> Show an empty joiner list until a new successful enrollment occurs; describe this limit in the PR and operator guide.

## Migration Plan

Apply the single control-plane migration before deploying readers that require the joiner table, then deploy control plane and frontend. Existing filtering state, rules, exceptions, links and opening counts remain untouched. No backfill is possible. Rollback requires reverting the application first, then dropping the new table through that migration's downgrade; saved joiner history would be lost on downgrade.

## Context

See `proposal.md` for the observed recipe gap and confirmed photo exclusion. The current router mounts only Home, provisioning and resources. `UserProfile` deliberately shows identity/logout only, including inside `MainLayout navigation={false}` before consent/bootstrap.

The original `UserSettingsPage` remains in place with its shared controls and SCSS. Its identity fields come from `KeyCloakService`, but its role line checks an identity-provider `admin` role, and its photo code mounts `useFrontendBootstrap` and Python avatar mutations. Mounting that page unchanged would therefore break manager's no-Python boundary. `ReleaseNotesPage`/`ReleaseNotesContent` read shipped markdown; the separate `usePatchNoteHistory` and `PatchNoteDialog` read published Python announcements. `GcuPageContent` already offers an accepted/read-only presentation, while the admission wrapper performs acceptance.

## Goals / Non-Goals

**Goals:** Reconnect the same UI files, retaining their presentation and preference mechanisms, with manager-owned authority and no organization prerequisite. Extend the existing browser recipe rather than introducing a second application or harness.

**Non-Goals:** Photo upload/storage, published patch-note announcements, profile-identity editing, Help Center reconstruction, admission-policy reconstruction, role administration, or new backend/storage infrastructure. Identity remains the signed-in person's provider identity.

## Decisions

1. **Reconnect routes and the existing menu.** Add `/settings`, `/gcu`, `/gdpr` and `/release-notes` under the current consent/bootstrap guards. Pass the sidebar's existing admitted-navigation state to `UserProfile` so Profile/support entries can be mounted after admission without adding a protected query to the pre-admission menu. Reuse its existing `MenuPopoverItem` navigation and configured support-link behavior. Preserve identity/logout, Escape/focus restoration and keyboard access. Merely adding a link is insufficient because the router currently redirects these URLs Home.

2. **Adapt `UserSettingsPage` in place.** Keep its identity, preferences, logout and legal/release link markup and shared components. Replace the identity-provider role condition with `platform_roles` from generated manager `useMeQuery`, using the established freshness/error conventions and distinguishing empty, pending and failed results. Remove the page's Python bootstrap/avatar subscriptions and unmounted photo actions from this branch's rendered profile; keep the existing shared avatar widgets available for the separate photo lot. No copied `ManagerProfilePage`, new preference store, backend-selection flag or second settings renderer is needed.

3. **Reuse content pages directly.** Mount `ReleaseNotesPage` and `GdprPage` with their existing content loaders, return navigation and errors. For admitted CGU consultation, reuse `GcuPageContent` in its accepted view using current manager consent/version; preserve the separate guarded acceptance flow. Reopening legal text must send no acceptance mutation. The profile's release-notes link uses shipped markdown; it does not mount `PatchNoteGate` or `usePatchNoteHistory`.

4. **Keep authority unchanged.** The existing manager `/me` is sufficient; no Rust handler, schema, role mapping, SQL table/lock or tuple write is added. Share the existing RTK cache/freshness behavior with navigation; add no polling or per-role request fan-out. The endpoint retains the request budget documented in arc42 chapter 09. Own-profile access applies to every admitted person, including an owner without spaces and a member without platform roles. Do not widen platform administration or resource access.

## Risks / Trade-offs

- An apparently harmless reused component can mount Python consumers. Extend the real browser harness's existing request-denial assertions across every new page and account switch.
- The original profile-role line is not a manager authorization source. Render only manager roles and clear/unmount stale account data using the existing logout/cache-reset path; cover pending/error/empty responses.
- Restoring CGU as a route can accidentally write consent again. Exercise the accepted view and assert no mutation while consulting it; keep the guard authoritative on a version change or outage.
- Existing menu tests and browser logout helpers assume logout is the sole item. Update them for admitted navigation while preserving pre-admission keyboard behavior, and inspect narrow-screen scrolling and both color modes without restyling.
- The photo section is intentionally absent in this lot, as confirmed by the developer. Do not expose a disabled or misleading control implying that storage is implemented.

## Migration Plan

No schema or identity migration. After implementation and manual feature validation, run focused component/router checks and the existing isolated provisioning browser recipe, then the applicable quality/review checks. Document the actual implemented path in arc42 chapters 02, A1 and 09 and the frontend UX guidance. Add the ordinary no-operator-action migration note required for the eventual PR.

Rebuild/deploy the branch's frontend with the existing factory workflow; manager and imported data retain their state. A frontend rollback removes the restored navigation without changing consent, grants or imports. Keep commits local on `weaver`; pushing requires the developer's explicit agreement.

## UI parity correction requested during the Priya recipe

The developer's explicit correction supersedes the earlier bounded-shell decision:
use the complete UI from `origin/swift` at `13029601f` as the restoration reference.
Restore existing components, styles and route topology, including standalone
account/legal pages. Keep manager admission around these routes, retaining the
already accepted photo exclusion. Restore ordinary background consumers after
admission. Non-migrated control-plane, knowledge-flow and runtime calls remain
unchanged and may fail normally when those services are unavailable; no forwarding,
fallback or invented API success is added.

Use manager memberships only for the already migrated team/personal navigation,
and show organization name only in Profile. Reuse the existing team list's search,
sort, avatars and role text; remove the generic kind/hierarchy/detail presentation.
Retain the manager personal-opening operation and navigate to the ordinary agents
route using its UUID. Do not infer permissions from display roles or fabricate a
Python bootstrap payload. Non-migrated permission-dependent UI keeps its original
backend-driven conditions.

Restore the original Resources page and DocumentWorkspace instead of maintaining
the reduced manager-specific explorer. Its richer library/document contract remains
an explicit binding gap; manager folder/document APIs themselves stay unchanged.
Reconnecting that UI must preserve its controls and must not substitute a reduced
screen. This correction does not claim resource workflow parity.

Verification is focused on route retention, original Home widgets and navigation,
manager personal opening, profile-only organization display, and TypeScript checks.
The broad campaign remains deferred by the developer. Review the exact patch
independently and retain the deferred manual/browser evidence in tasks.

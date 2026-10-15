## Context

See [proposal](proposal.md). The current entry in `apps/frontend/src/index.tsx`
imports `app/ManagerApp.tsx`. `app/App.tsx`, `common/router.tsx`, `MainLayout`,
`Sidebar`, `MainNavBar`, `HomeNavPanel`, `AdminNavbar` and `UserProfile` still
implement Fred's original presentation. Provisioning already has a route and
navigation item there, but returning to `App` alone is insufficient:

| Consumer | Observed dependency to remove from this journey |
| --- | --- |
| ApplicationContextProvider | Control-plane public configuration subscription |
| GcuGuard / BootstrapGuard | Python consent query / configuration-based bootstrap gate |
| App | Announcements, patch notes and optional platform-admission flow |
| MainLayout | Task rehydration, polling and team-admin charter gate |
| MainNavBar / AdminNavbar / admin redirect | Control-plane capabilities, alongside manager authority |
| HomeNavPanel / UserProfile | Python bootstrap, personal team assumption, avatar and patch notes |
| HomePage | Agent search, recents, activity and marketplace widgets |

The generated manager slice already exposes onboarding, terms acceptance, root
bootstrap, current platform roles, own spaces and provisioning. Public startup
configuration already comes from manager. The existing browser harness rejects
control-plane and knowledge-flow calls.

## Goals / Non-Goals

Use the existing UI components and styles as the continuing product UI. Keep the
accepted [scope](proposal.md#non-goals) bounded. No Rust or authorization-model
change is needed. Unmounted Python feature implementations are not bulk-deleted.

## Decisions

1. **One entry and one router.** Restore `App` as the entry, adapt its existing
   composition, and remove `ManagerApp` and its shell-specific styles/tests after
   moving useful coverage. Move startup-error styling into the existing app styles.
   Keep `MainLayout` and the existing sidebar hierarchy. Do not rename the parallel
   shell, clone the sidebar, or introduce a backend-selection framework.

2. **Manager admission in the existing guards.** Move the existing manager journey
   behavior into the CGU/bootstrap guards and screens. Reuse the generated queries
   and mutations and their cache invalidation; preserve retry, focus refresh,
   version changes, disabled CGU and unavailable-service behavior. Mount no admitted
   route until current personal consent and bootstrap state permit it. Existing
   toast, confirmation, theme and loading components remain available without
   starting unrelated services. Read presentation configuration already loaded at
   startup; do not add a platform-theme administration endpoint.
   Keep the existing account menu's identity/logout accessible before admission,
   including CGU, bootstrap and admission failures. It must use authenticated
   identity alone there, without fetching protected manager or Python data.

3. **Existing navigation, bounded destinations.** `/` leads to `/home`; the home
   page keeps Fred's greeting/layout and shows own memberships and roles instead
   of mounting agent/activity widgets. Adapt `HomeNavPanel` to the declared
   organization/team/project hierarchy, without a synthetic personal team.
   Selecting an entry shows its membership details within `/home`; it does not
   open an agent or resource page. Reuse existing list, text and badge primitives;
   consume generated manager types directly rather than fabricating Python team
   DTOs. Root sees an empty state. The admin rail and `/admin` lead to the existing
   Provisioning page only for manager platform administrators. Keep the existing
   profile menu's identity and logout; hide unavailable profile/history actions.

4. **Route restriction, not just hidden links.** Keep only this journey's routes
   reachable in the existing router on this branch. Unknown and unsupported routes
   return to `/home` after admission without mounting their components. A direct
   `/admin/provisioning` visit retains the existing explicit denied/unavailable
   authority feedback. Remove Python consumers from the mounted composition rather
   than catch their failures or return fake success data. No full-UI feature flag
   or compatibility mode is added.

5. **Reuse the real acceptance harness.** Extend `test-provisioning-browser` rather
   than create a second campaign. Assert the real Fred sidebar, home and account
   menu as well as the existing complete business journey. Block unexpected Python
   and runtime requests, exercise direct URLs and reloads, and inspect screenshots
   at desktop and narrow widths. Unit tests cover admission changes and authority
   failure; browser tests prove actual wiring without fabricated API responses.

## Risks / Trade-offs

- Hidden subscriptions can survive visual reuse: intercept network requests in
  browser acceptance, including navigation and account changes, and fail on them.
- Old cached membership or role state can leak across identities: preserve/reset
  session caches and exercise root/member transitions in the same browser,
  including switching away from a wrong account before accepting terms/bootstrap.
- The existing team list assumes Python roles and a personal team: change its data
  consumer explicitly; do not translate manager roles into legacy permission flags.
- Removing the shell must not remove safeguards: retain server enforcement and
  all previous consent/bootstrap/import refusal and replay scenarios.
- The existing dashboard is intentionally limited to memberships for this branch.
  This is not a promise that agents, documents or other administration pages work.

## Migration Plan

No persisted state or infrastructure changes. Deploy the rebuilt frontend against
the existing manager; existing root, consent and imports remain valid. Reverting
the frontend commit restores the previous entry without resetting any service.

The implementation commit updates arc42 and the existing READMEs only after review,
describing implemented behavior in the present tense. Main capability specs remain
unchanged until the completed change is synced and archived.

The developer confirms this scope before implementation. If a consumer requires a
new backend contract, Python/Rust compatibility, or an unagreed admission rule,
stop and discuss that exact dependency rather than expanding this lot.

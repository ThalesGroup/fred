# RFC: Frontend page modules — every screen implements one interface

**Status:** proposed — open design question; no implementation approved by this RFC alone
**Author:** TBD (team review)
**Date:** 2026-08-18
**Revised:** 2026-08-18 — seventh pass: cold re-review. PR 3 split into 3a (navbar primary) / 3b (chat remount). `buildRoutes` joins the `{catalog, errors}` contract (absolute child vs parent prefix — a typo must not throw inside `createBrowserRouter`). Churn on `TeamContentNavbar` is **not** mostly the primary list. PR 0 pins `make test` verbatim; suite measured green locally (see §9).
**ID:** FRONT-PAGE-01
**Area:** `apps/frontend` (`rework/core/pages/`, `common/router.tsx`, sidebars; later `common/store.tsx`)
**Related docs:**
- `docs/swift/rfc/AGENT-CAPABILITY-PRESENTATION.html` slide 11 (four registries) and slide 20 (“full page — missing slot”) — **composition metaphor only; do not amend that deck**
- `docs/swift/capabilities/AUTHORING.md`
- `docs/swift/platform/FRONTEND_CODING_GUIDELINES.md` §1
- `docs/swift/platform/FRONTEND-AUTHZ-PATTERN.md` — team gates stay in-page; `Protected` is org-tier only
- `docs/swift/platform/FORKING_GUIDE.md`
- `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` §3.1
- GitHub `#2307` (SI UI; packaging deferred to a dedicated RFC)
- GitHub `#2296` (MUI purge as *prep* for later extensibility — did not spec plugins)

**Contract impact:** none in the committed PRs. Product-mode (out of this RFC) would add an inline dated note in `CONTROL-PLANE-PRODUCT-CONTRACT.md` §3.1 plus a new numbered Contract Note — not “§8”, which is the Backend Completeness Gate. No runtime OpenAPI change. `FRONTEND-AUTHZ-PATTERN.md` is **amended** if we document the existing settings redirect (`TeamSettingsPage.tsx:48`); team gates stay off the router (`Protected` remains org-tier). That doc still cites `src/components/Protected.tsx`; the file is `src/rework/core/guards/Protected.tsx`.

---

## 1. Problem

Adding a screen to Fred is a horizontal edit. The capability system already refused that shape for chat UI. Pages never got the equivalent.

| Hotspot | File | What an author adds |
| --- | --- | --- |
| Route | `apps/frontend/src/common/router.tsx` | import + `path` + optional `<Protected>` + remount wrapper |
| Nav | `TeamContentNavbar` / `AdminNavbar` / `MarketplaceNavbar` / `MainNavBar` | another hardcoded item + a local `if` |
| Settings (if applicable) | **both** `TeamContentNavbar` *and* `TeamSettingsPage` | duplicated section list and gates — **already drifted** |
| Store | `common/store.tsx` | reducer + middleware, if the page (or capability) has an RTK API or local slice |
| i18n | `locales/{en,fr}/translation.json` | both files (`AUTHORING.md` still requires this for capabilities) |
| Proxy | `vite.config.ts` + `docker-entrypoint.sh` | only if a **new backend** (nginx upstreams, not page flags) |

`router.tsx` still statically imports ~26 page components. `store.tsx` hand-wires three capability APIs (`demoEcho`, `writableDocument`, `pptFiller`) **and** their local slices (`writableDocument`, `pptPreview`, `sidePanelOpenRequest`) plus platform APIs. `Sidebar.tsx:26–31` sniffs pathname prefixes; anything that is not `/home`, `/marketplace`, or `/admin` gets the **team** navbar, including `/dev/*`.

Two product needs hit this wall:

1. **First-party growth.** Every new Fred page repeats the hotspot dance.
2. **Composition.** A deployment that wants “2–3 pages using existing FE and BE” cannot say so. `enableK8Features` / `enableElecWarfare` have **zero** TSX consumers (`isFeatureEnabled` is never called). Only `enableAllResourceSpaces` is read (`TeamResourcesPage.tsx:86`). Those two unused keys also exist on a separate pre-auth `FeatureFlagKey` surface in `config.tsx` that is not the bootstrap `FrontendFeatureFlags` type. `MainNavBar` is role-gated, not flag-gated.

`FORKING_GUIDE.md`: if a fork must edit a `.tsx` to add a screen, the open-source tree is missing an extension point.

**Why this is not reachable by deletion alone.** The duplicated gate lists and `router.tsx` imports are the thing to delete. Doing that without a registry just moves the list. A small host + `page.module.ts` for the screens we migrate is net-additive in the first PR and net-reducing on the hotspots we touch. Per-page authoring is **not** cheaper than today's ~15-line SelfTestPage edit (`router.tsx` + navbar); the win is **one conflict surface and one gate table**. This RFC does **not** fund a ten-PR rewrite of every screen. Committed work is §9 only.

---

## 2. Current as-built baseline (verified against this tree)

Increments 1–6 of this RFC are **not implemented**. There is no `rework/core/pages/`, no `page.module.ts`, no `FredPageModule`, no `buildRoutes` / catalog `href()`.

### 2.1 Capability UI plugins — shipped, chat-scoped, do not register pages

`CapabilityUiPlugin` (`rework/features/capabilities/types.ts:152–191`) has `partRenderers`, `configWidgets`, `chatTurnControls`, `sidePanels`, `sessionProbes`. **No `pages` field.** Index: `demo_echo`, `writable_document`, `ppt_filler`.

The HTML deck’s slide 11 still shows **four** registries. Runtime already grew a **fifth** (`sessionProbeRegistry.ts`). That is evidence that “extend the side-panel slot” already accreted a new registry — another reason pages must not hang off `CapabilityUiPlugin`.

`document_access` (the canonical backend capability) has **no** plugin folder. Its composer rows are stock-kit descriptors (`stockKit/index.ts`). That cheap lane is correct for chat widgets and **wrong** as a model for routes.

Registries are pure `buildXRegistry(plugins)` with one host each. Part kinds: first-wins + `console.warn` (`partRendererRegistry.ts:24–47`). Unknown parts **silent-skip** so an older frontend never crashes on a newer pod (`types.ts:18–20`). **Copy the composition. Do not copy skip or first-wins for routes.**

`AGENT-CAPABILITY-RFC.md` is **not on disk**. “RFC §9” lives in comments + the HTML deck. Slide 20:

> full page — the one slot we don't have
> a future page-slot must be a natural extension of the side-panel slot — not a different mechanism.

Read as: **same pattern** (module → registry → host). Not: hang `pages` on `CapabilityUiPlugin`. Not: migrate Knowledge Flow into a capability. Reasoning was already built as a capability and withdrawn (`AUTHORING.md` / contract §33) — the same category error this RFC must not repeat.

### 2.2 Pages are not modules

`FRONTEND_CODING_GUIDELINES.md` §1 places page *components* under `pages/` and says nothing about how a page is *declared*. `router.test.tsx` locks **removed** paths (`monitoring/*`, `test-renderer`, `tools`) **and** the `*` → `PageError` catch-all.

Help content uses `import.meta.glob("./content/*/*/*.md")` in `helpCenter/content.ts:52`. `HELP_SECTIONS` in `manifest.ts` is a **hand-written section list**, not that glob. Either way: articles, not app routes.

`App.tsx` wraps the router with `GcuGuard` / `BootstrapGuard`, which can replace the whole tree with `GcuPage` / `BootstrapPage`. Those also have standalone routes. They stay **shell**, not discovered pages.

### 2.3 Drift already in the hand-wired tree

| Item | Navbar | Page |
| --- | --- | --- |
| Usage | settings-nav sibling, `hasElevatedTeamRole` (`TeamContentNavbar.tsx:170–180`) | **not** a `:section`; `/team/:id/usage`; personal KPIs visible to members (`TeamUsagePage.tsx:53–69`) |
| Personal-team gear | always → `/usage` | same weaker in-page gate |
| Routing | elevated to **see** | `canUpdateResources` to **write** (`TeamSettingsPage.tsx:77–80`) |
| Retention | not in nav | allowed then redirected to parameters (`TeamSettingsPage.tsx:67–70`) |
| Prompts | hardcoded English `"Prompts"` (`TeamContentNavbar.tsx:118`); no `rework.sidebar.team.menu.prompts` key | — |

Settings gates are re-expressed in the navbar and the page; they are not one table. **Usage already falsifies a single module-level `gate`:** the URL is open, the nav entry is elevated-only. Gate the **contribution**, not the page.

### 2.4 Reuse is blocked by folder placement

`DocumentWorkspace` lives under `pages/TeamResourcesPage/DocumentWorkspace/` and is imported only by that page. Shared organisms live under `shared/organisms/`. Lift on demand when a second page mounts it — not as the framework.

### 2.5 Cross-repo clients and `#2307`

- Evaluation **client is committed and used** (`TeamSettingsEvaluations/*`, `TaskActivity.tsx`). `make update-evaluation-api` `cd`s to missing `apps/fred-evaluation-backend`. The README documents `ignored/fred-agent-evaluator/apps/fred-evaluation-backend`. Snapshot `openapi.json` is gitignored (repo-root unanchored rule) and absent. `update-all-apis` depends on the broken target.
- **No** `slices/rags/` on this tree. That work is on diverged `origin/mvp/rags-support` — prior art for the **pain** (hotspot edits), not a page-module implementation.
- `#2307` decided: rags-services stays out of this monorepo; SI UI in-tree + flag; **packaging / independently deployable UI = dedicated RFC**. This file is that RFC’s **in-SPA** half. Independently deployable `libs/fred-ui` stays deferred.

### 2.6 What this RFC is not rediscovering

- Agent pods are already independently deployable (`FORKING_GUIDE.md`).
- `contrib/` already covers static fork content. It cannot register a React page.
- Application Workflows / Temporal-in-activity (`CAPABILITY-EXECUTION-FLOW-RFC.md` §9) are a backend open question. A page that *displays* runs does not wait on it.

---

## 3. Industry patterns (what we copy)

| Source | Pattern | What we take | What we leave |
| --- | --- | --- | --- |
| **VS Code** [contribution points](https://code.visualstudio.com/api/references/contribution-points) | Manifest declares *slots*; host owns chrome; `when` clauses gate visibility | Named contribution points: `route`, `nav`. Rail is a host table; settings are child routes. Declarative gates, not ad-hoc `if`s in the host | JSON remotes, activation events, runtime extension loading |
| **Backstage** [frontend extensions](https://backstage.io/docs/frontend-system/architecture/extensions/) / [`PageBlueprint`](https://backstage.io/docs/frontend-system/building-plugins/migrating/) | Plugin provides a lazy page; **typed route refs**; extensions attach to named **inputs** on a parent, not one god object; `if` predicates for flags/permissions | `PageRef` + `href(ref, params)`. Per-slot inputs (nav host, rail host, route host). Conditions as data | Full Backstage frontend-system / package-per-plugin / YAML `app.extensions` |
| **Grafana** [app plugins](https://grafana.com/developers/plugin-tools/key-concepts/anatomy-of-a-plugin) | Apps add **pages** to existing nav; UI extensions hook core slots | Page = React view + nav contribution. Shell stays Fred’s | Separate Grafana runtime, `plugin.json` loader |
| **Vite `import.meta.glob`** ([docs](https://vite.dev/guide/features.html#glob-import)) | Convention discovers modules at compile time | Discover `**/page.module.ts`. **Already used** for help markdown (`helpCenter/content.ts:52`) | Do **not** move `pages/` onto a `src/routes/` file tree or replace React Router |
| **Module Federation** ([when to use](https://scriptedalchemy.medium.com/when-should-you-leverage-module-federation-and-how-2998b132c840)) | Runtime composition across independently deployed apps | Nothing in v1 | Shared Keycloak + Redux + i18n + bootstrap make a second app a multi-week extract |

Classic design rules this maps to:

- **Open/Closed** — a **new admin, settings, or team-primary** page is a `page.module.ts`. Help, ComingSoon, TaskPlayground, and user `/settings` still require a `router.tsx` (or `shellModules`) edit in this RFC.
- **Interface Segregation** — hosts depend on one contribution type, not a bag of optional fields.
- **Registry** — one in-memory catalog per slot (already how `buildPartRendererRegistry` works).
- **Strategy** — `evaluateGate(gate, ctx)` is the only interpreter; hosts never `switch` on gate kinds for visibility.
- **Factory** — `definePage(...)` validates and freezes; `composePageCatalog` records collisions and does **not** throw at boot.
- **Fail-fast in CI** — duplicate `id` or `path` fails vitest (`catalogErrors.length === 0`) **after** PR 0. Production keeps the first module and logs.
- **Fitness function** — after PR 2, `AdminNavbar` has no admin path literals. After **PR 3a**, `TeamContentNavbar` has no `/agents` literal. A full `router.tsx` import-ban is **out of this RFC** (TaskPlayground, ComingSoon, Help, user settings stay imported).

---

## 4. Proposed solution

### 4.1 Authoring container + per-slot registries (not a bag hosts read)

A first-draft `FredPageModule` with six optional fields (`nav`, `gate`, `defaultForPlacement`, `sections`, `remountOnParams`, `rail`) is a god object. Legal but meaningless combos (rail + team placement + `chrome: "none"` + sections) will accrete `apis`, `i18n`, `badge`. Hosts will keep growing `if (module.x)`.

**Runtime model:** factory returns a typed container. Hosts never import it. Each contribution point has its own `buildXRegistry` + host — the capability composition.

```
page.module.ts ── definePage({ ref, route, nav? })
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        routeRegistry          navRegistry
              │                     │
              ▼                     ▼
        buildRoutes()           navItems()
        href()                  AdminNavbar / TeamContentNavbar

Rail is a 4-row host table, not a registry. Settings sections are child routes, not a sectionRegistry.
```

Adding `i18n` later is a new optional field + a new registry + a new host. Existing `page.module.ts` files and existing route/nav hosts do not change.

```ts
// rework/core/pages/types.ts  — future @fred/page-sdk (GENERIC only)

export type PageChrome = "main" | "none";
export type RailBehavior = "navigate" | "externalTab";

/** Combinators only. Fred predicates live in host/fredGates.ts. */
export type PageGate<Pred = never> =
  | Pred
  | { all: readonly PageGate<Pred>[] }
  | { any: readonly PageGate<Pred>[] }
  | { not: PageGate<Pred> };

export interface RouteContribution<Pred = never, Placement extends string = string> {
  path: string;
  chrome: PageChrome;
  placement: Placement;
  element: LazyExoticComponent<ComponentType>; // lazy() only
  gate?: PageGate<Pred>;
  remountOn?: readonly string[];
}

export interface NavContribution<Pred = never, Placement extends string = string, Icon = unknown> {
  placement: Placement;
  group?: string;            // Fred uses "primary" | "settings"
  labelKey: string;
  icon: Icon;                // NOT IconType — host maps it
  order: number;
  gate?: PageGate<Pred>;
}

// rework/core/pages/host/fredGates.ts  — STAYS IN THE APP
export type FredPred =
  | { pred: "platform"; requires: "admin" | "observer" }
  | { pred: "team"; requires: keyof TeamCapabilities | "member" | "elevated" | "collaborative" }
  | { pred: "flag"; flag: keyof FrontendFeatureFlags }
  | { pred: "env"; requires: "dev" };

export type FredPlacement = "home" | "team" | "admin" | "marketplace" | "none";

export function createDefinePage<Pred, Placement extends string, Icon>(): (
  mod: FredPageModule<Pred, Placement, Icon>,
) => FredPageModule<Pred, Placement, Icon>;
// host re-exports: export const definePage = createDefinePage<FredPred, FredPlacement, IconType>();
```

`element` on `RouteContribution` is **`lazy()` only**. `App.tsx:73–77` already dynamically imports `router.tsx`, so the 26 page imports are out of the entry chunk; a non-lazy `page.module.ts` would silently undo the Help-style reason `router.tsx:86–89` exists. `buildRoutes` wraps each page in the existing `SuspenseWrapper` (`router.tsx:99–101`) so chrome stays mounted. Nothing in `App.tsx`'s entry graph may import the catalog.

Fred-only nav extras (not SDK types — they live on the bound host contribution):

- `badge` from live store (`AdminNavbar.tsx:29,45` — `selectActiveCount`)
- `label` / `icon` from `useFrontendProperties()` (`TeamContentNavbar.tsx:106–107` — agents nickname + icon)

A placement's **landing** is its first gate-passing nav entry by `order`. That replaces `defaultForPlacement` and reproduces `AdminIndexRoute`'s observer branch (analytics is visible when teams is not).

`rail` is **not** a per-page slot. `MainNavBar`'s four entries (home, marketplace, help=`window.open`, admin) are a 4-row table in `host/fredPlacements.ts`.

`sections` is **not** a SDK slot. Settings is a nested route: `team/:teamId/settings/:section` as children of a settings layout — **same public URLs**. That deletes `TeamSettingsPage.tsx:53–84`'s switch. **Caveat:** today any *unknown* `:section` redirects to members (`TeamSettingsPage.tsx:59`). Static children would fall to `PageError` unless the settings layout keeps an index/catch child that redirects to members. PR 4 must ship that catch child or it is a behavior change, not a pure deletion.

`evaluateGate` in the SDK folder only folds `all` / `any` / `not` and calls an **injected** `(pred, ctx) => "allow" | "deny" | "unknown"`. It must not mention `"platform"` or `"team"`. A typo `{ pred: "teem" }` is a type error because pages import the **bound** `definePage` from `host/`.

**Tri-state is mandatory.** `Protected.tsx:51–58` and `TeamSettingsPage.tsx:39–45` already return `null` while bootstrap / team permissions are loading — deciding on the default `false` redirects an admin to `/unauthorized` (or a member off settings) and `replace` makes that irreversible. Hosts evaluate gates **during render**, not at `createBrowserRouter` time.

| Result | Route host | Nav host |
| --- | --- | --- |
| `unknown` | render `null` (chrome stays) | hide the item |
| `allow` | render the page | show |
| `deny` | policy table in §4.4 | hide |

`PageContext` is assembled during render from `useUserCapabilities()` and `useSelectedTeam()`. **Readiness winner for PR 4:** on a **collaborative** team, ctx is `unknown` until both `"permissions" in selectedTeam` (`TeamSettingsPage.tsx:43`) and `"my_relations" in selectedTeam` (`TeamContentNavbar.tsx:88`). Do **not** apply the `my_relations` wait on the personal space — that key is not a team-roles field there (`TeamContentNavbar.tsx:78–80`); waiting for it would leave personal usage/settings chrome unknown forever.

**Gate lives on the contribution, not the module.** Usage is the existence proof:

```ts
route: { path: "team/:teamId/usage" /* no route gate — URL stays open */ },
nav: {
  placement: "team",
  group: "settings",
  gate: { all: [{ pred: "team", requires: "elevated" }, { pred: "team", requires: "collaborative" }] },
},
```

### 4.2 Two authors, one type — not a 6th capability field

| Author | Where `definePage` lives | When |
| --- | --- | --- |
| First-party Fred screen | `pages/<Name>/page.module.ts`, discovered | Always |
| Capability that truly needs a **management page** | still a `page.module.ts` under `components/pages/` | Rare |

Do **not** add `pages?:` to `CapabilityUiPlugin`. Chat slots are session-active-capability driven and silent-skip. App routes are URL + authz and must 404. Same *composition*, different *type and failure policy*.

Application surfaces that are not agent features (RAGs workflow console, SI admin, slim ingest) are first-party page modules. They are **not** fake capabilities.

`store.tsx` listing capability APIs is a **capability** hotspot. Kill it later with an `apis` field on `CapabilityUiPlugin`, not on the page module. Platform slices stay store-owned.

### 4.3 Discovery: glob, not a growing `catalog.ts`

A hand-edited `catalog.ts` is the same hotspot this RFC exists to kill (fine for 3 capability plugins; not for 25+ pages). This SPA already discovers help markdown with `import.meta.glob`.

```ts
// rework/core/pages/host/discover.ts  — ONLY here, not under core/pages/
const discovered = import.meta.glob(
  "../../../components/pages/**/page.module.ts",
  { eager: true, import: "default" },
);

export const { catalog: pageCatalog, errors: catalogErrors } = composePageCatalog([
  ...shellModules,
  ...Object.values(discovered).map(assertPageModule),
]);
```

`composePageCatalog` **does not throw**. It returns `{ catalog, errors }`. Production logs collisions and keeps the first module (SPA must boot — `App.tsx:73–77` dynamically imports `router.tsx`; a throw leaves the loading screen up forever). A vitest asserts `catalogErrors.length === 0`. That test is unenforceable until PR 0 puts `make test` on the frontend CI matrix (`Check-pending-requests.yml` today runs only `type-check` and `format-check`).

Checked errors (logged, not thrown) — **both** `composePageCatalog` and `buildRoutes` return `{ catalog | routes, errors }`. Neither throws. `createBrowserRouter` must never be the first thing that sees a bad path: React Router throws at config time if an absolute child does not start with its parent's combined path (e.g. a settings child `/team/:teamId/sttings/:section` under parent `/team/:teamId/settings`). That throw happens inside the dynamically imported router module (`App.tsx:73–77`) and leaves the loading screen up — same class as B2.

- Duplicate `ref.id` or `route.path`
- `nav` without a `route`
- `remountOn` names a param that is not in `path`
- Absolute `ref.path` is not a prefix-legal child of the parent it will nest under (`/` for MainLayout children; `/team/:teamId/settings` for settings children). Drop the route and record the error.

Under parent `path: "/"` every absolute path is legal (no stripping). Under the settings layout, children **must** be the full prefix. One example `buildRoutes` must implement:

```
parent "/"                  → child "/team/:teamId/agents"           OK
parent "/team/:teamId/settings" → child "/team/:teamId/settings/members" OK
parent "/team/:teamId/settings" → child "members"                    OK (relative)
parent "/team/:teamId/settings" → child "/settings/members"          ERROR, drop
```

Filename `page.module.ts` is the filter so `*.test.ts` is not picked up. `src/pages/TaskPlayground.tsx` is **outside** this glob (legacy `src/pages/`, same as `ComingSoon`). It stays a `shellModules` entry or a second explicit import — do not pretend the glob covers it.

Forks still cannot add a `.tsx` in `src/` (`FORKING_GUIDE.md`). Glob does not change that. A new screen is an upstream `page.module.ts`, not a `contrib/` file.

### 4.4 Collision, missing-module, and hide policy (no “or”)

| Event | Policy |
| --- | --- |
| Two modules share `id` or `path` | first wins; error recorded; vitest asserts zero errors (**after** PR 0, in CI) |
| Unknown `href(...)` | throw in dev / test; do not emit `/undefined`. `tsconfig.json` has `"strict": false` — **ids** are compile-safe, **params** are not; `href` runtime-guards a missing params object |
| User hits a path no module owns | existing `PageError` (`*`) |
| Gate result `unknown` | render `null` / hide nav — never redirect |
| `platform` deny | `/unauthorized` — today’s `<Protected>` (`Protected.tsx:59–60`) |
| `team` deny on settings | redirect to members or agents — today’s `TeamSettingsPage.tsx:48–59` (already a redirect; `FRONTEND-AUTHZ-PATTERN.md` says hide-not-redirect and is **wrong about current settings**) |
| `env.dev` deny | keep the path; render `PageError` — today’s `/dev/*` (`router.tsx:240–246`) |
| `flag` deny | **nav only.** Keep the route. Element may render `PageError` if we want it hidden from deep links, but do **not** omit it from the router. Flags arrive on async bootstrap (`useFrontendBootstrap.ts:55`) while `createBrowserRouter` runs once (`router.tsx:320`). Omitting the route freezes on the initial `undefined` and 404s forever. Precedent: `#2307` on `mvp/rags-support` keeps `admin/information-systems` under `<Protected requires="admin">` and gates **only the nav** (`visible: canAdmin && enableInformationSystems`). **Flag = maturity switch. Allowlist (§4.8) = SKU.** |
| Capability chat part unknown | unchanged: skip (not this RFC) |

Do **not** put team gates on the router via `<Protected>`. `FRONTEND-AUTHZ-PATTERN.md` and `Protected.tsx:24–27` say team gating is in-page. Increment 4 must not invent team route guards.

### 4.5 Typed `href` (path lives on the ref)

Hardcoded `/team/…` and `/admin…` strings **outside** `router.tsx` and tests are a **floor of ≥33**. This RFC's committed PRs convert on the order of **a handful** in the navbars they touch (3a: primary links + Back; 4: settings entries) and leave **~30** sites (ChatList, AgentCard, HomeNavPanel, marketplace cards, `TeamSettingsMembersMenu.tsx:75` `navigate("/team/personal/agents")`, …) as they are. Do not read §4.5 as a full `href()` sweep.

```ts
export function pageRef<Id extends string, Path extends string>(
  id: Id,
  path: Path,
): PageRef<Id, Path>;

export function href<Id extends string, Path extends string>(
  ref: PageRef<Id, Path>,
  params: PathParams<Path>, // derived from `:param` segments
): string;
```

Params cannot disagree with the path. `remountOn` is a compile-time check against those segments. No `declare module` augmentation — that cycle (`catalog → page.module → href → catalog`) never forms. `path` is stored **absolute** (`/team/:teamId/agents`) so `placementForPath` can `matchRoutes` a flat list.

`tsconfig.json` has `"strict": false` — `href(ref, null)` type-checks. `href` **runtime-guards** a missing/empty params object.

Chrome hosts never name a path. Query strings (`?session=`) stay call-site suffixes in v1. A placement's landing is its first visible nav item by `order` — not a `defaultForPlacement` flag.

### 4.6 What stays shell vs what implements the interface

**Not discovered, not catalog-gated** (must render when auth/bootstrap has failed):

| Surface | Why |
| --- | --- |
| `GcuGuard` / `BootstrapGuard` | Wrap `RouterProvider`; replace the whole tree (`App.tsx`) |
| `ComingSoon` | Whitelist rejection (`src/pages/`, not `rework/components/pages/`) |
| `PageUnauthorized` (`router.tsx:50` import alias `Unauthorized`) | Denial target of `Protected` |
| `PageError` (`*`) | Catch-all |
| `MainLayout`, ChatList, team banner, `HomeNavPanel` team switcher, `UserProfile` | Chrome organisms, not screens |
| `Protected` | Platform-gate adapter |

`GcuPage` / `BootstrapPage` / `ComingSoon` / `PageUnauthorized` **implement** `definePage` via an explicit `shellModules` list so every page implements the interface. Guards keep importing the **components** directly. A `shellModules` entry named `Unauthorized` will not resolve.

**Index redirects stay shell policy, expressed over the catalog** — they are not pages:

- `/` → **not** a placement landing. `HomeIndexRoute` waits for bootstrap then `/team/${activeTeam.id}/agents` (`router.tsx:66–69`). First-visible-by-order cannot replace this: it needs `activeTeam`, not a nav list.
- `/admin` → first visible admin nav entry by `order` (admin sees teams; observer sees analytics). **If none visible → `/unauthorized`** (today `AdminIndexRoute` line 83). Unstated until this pass.
- `/team/:teamId` → first visible team primary nav entry (today: agents)
- `/team/:teamId/settings` → first visible settings child (today: members)
- `/help` → lang (help module may supply the index redirect)

**User** `/settings` is `UserSettingsPage` (`router.tsx:304–306`). It is **not** the team-settings members redirect.

`placementForPath` uses `matchRoutes` on the **assembled** tree (registry paths are nested under `path: "/"` + `MainLayout`). Unmatched paths have no placement — do not fall through to TEAM (today `Sidebar.tsx:30` does; `/dev/*` is the casualty). Return `{ placement, group }` so `/team/:id/usage` can show the settings menu. `MainNavBar.tsx:59,66,83` uses the same prefixes for **active state** (#2298 exception) — PR 5, if ever done, must update both Sidebar and MainNavBar.

`src/pages/TaskPlayground.tsx` is outside the `components/pages/**` glob. Keep it as an explicit `shellModules` / router leftover; do not claim glob covers it.

### 4.7 What a new page looks like

```
rework/components/pages/RagsWorkflowsPage/
  page.module.ts
  RagsWorkflowsPage.tsx
```

No router, no navbar, no Sidebar, no `catalog.ts` edit. Body composes existing organisms and generated hooks.

### 4.8 Product composition (later, not the mechanism)

A bootstrap allowlist (`visible_pages: [...]`) is a **render-time catalog filter**, not a compose-time omit — same reason as flags (§4.4). Applied once at `createBrowserRouter` it would freeze on the first `undefined` bootstrap. Out of this RFC either way.

Out of this RFC's committed PRs so the interface ships with **zero** control-plane contract change. **Flag ≠ allowlist** (§4.4).

### 4.9 Destination: two libraries, not three

Do **not** create `libs/` in increment 1. Freeze folder seams so a late extract is a **file move**.

The first draft mapped three backend names onto three frontend packages. That is the wrong analog:

- `fred-core` is **not** a design system — it already depends on FastAPI, Keycloak, SQLAlchemy. Mapping `fred-ui = fred-core` invites the same junk drawer.
- `fred-runtime` is reusable because **many pods** share an execution host and swap agents. Second UIs do not share Fred’s chrome and swap pages. They want buttons + route algebra. They bring their own auth, store, and layout.
- Prefer `@fred/ui` as the design-system working title. `apps/frontend/package.json` is `"name": "fred-ui"` but `"private": true` and there is no workspace root — no collision today. The name is hygiene for a future publish, not a current blocker.

**Keep two packages. Reject `fred-frontend-shell`.** Publishing Keycloak + RTK + MainLayout + Sidebar is the SPA under another name. A RAGs app that imports it has forked Fred.

| Package (working title) | Contents | Peers | Must not contain |
| --- | --- | --- | --- |
| **`@fred/page-sdk`** | `definePage`, `pageRef`, `href`, `composePageCatalog`, contribution interfaces, generic `PageGate<Pred>` (`all`/`any`/`not` + injected pred) | TypeScript + React types | Vite `import.meta.glob`, Keycloak, RTK, generated clients, Fred pages, `TeamCapabilities`, `FrontendFeatureFlags`, `IconType`, closed `PagePlacement` union |
| **`@fred/ui`** | `src/styles/*` tokens + store-free atoms + only molecules that take **local** props | `react`, optionally `react-i18next` | Organisms, layouts, `UserProfile`, any `slices/**` import, Keycloak, store, pages, locale JSON |

**Folder seam from increment 1** (so extract is a move):

```
rework/core/pages/            # future @fred/page-sdk — generic only
  types.ts
  definePage.ts
  pageRef.ts
  href.ts
  composePageCatalog.ts
  evaluateGate.ts             # all/any/not + (pred => allow|deny|unknown)
  pages.purity.test.ts

rework/core/pages/host/       # STAYS in apps/frontend forever
  discover.ts                 # import.meta.glob
  buildRoutes.ts
  fredGates.ts
  fredPlacements.ts
  shellModules.ts
  catalog.ts
```

**What cannot enter `@fred/ui` today** (coupling audit): `UserProfile` (Keycloak), `DocumentLibraryScopePicker` (KF hooks), `DocRow` / `TaskIndicator` / `TaskDetailPopover` / `AttachmentChips` (`useSelector`), any molecule with `import type` from `*OpenApi`, almost every organism (`ChatList`, `DocumentUploadDrawer`, `TaskActivity`, `TeamSettingsPanel/*`, `DocumentViewer`). `ResourceExplorer` is presentational enough to consider later. Tokens live in `apps/frontend/src/styles/`, not under `shared/`. Extract also has to deal with `@use "src/index.scss"` (`Button.module.scss:2` — Vite alias), `@font-face` in `src/styles/index.css`, and `Icon` `url(/images/icons/…)`. `@fred/ui` would ship fonts and a public-asset contract — another reason it is not this RFC.

**i18n:** `react-i18next` is a peer. `src/i18n.ts` + `locales/*.json` stay in the app. Do not rewrite atoms to injected labels in v1.

**What a second project imports, by milestone**

| After | Import | They still own |
| --- | --- | --- |
| PRs 1–6 (in-app only) | nothing published | entire SPA |
| First `libs/` PR (`@fred/page-sdk`) | `definePage`, `href`, `composePageCatalog` | router, auth, store, chrome, i18n init |
| Optional later (`@fred/ui`) | `Button`, `DataTable`, tokens CSS | the same host |
| Never | `MainLayout`, `Protected`, Keycloak `baseQuery` as a package | — |

**Purity tests** (copy `libs/fred-sdk/tests/test_sdk_purity.py` as a **source** import scan — there is no `no-restricted-imports` in frontend ESLint today):

1. `rework/core/pages/**` except `host/` must not import `common/store`, `common/router`, `security/KeycloakService`, `slices/*`, `components/pages/*`, `@hooks/*`, `teamCapabilities`, `FrontendFeatureFlags`, `IconType`.
2. `evaluateGate.ts` must not contain the strings `"platform"` / `"team"` / `"flag"`.
3. After `@fred/ui` exists: atoms/molecules in that package must not import store, Keycloak, or `slices/*`.

**What we still do not do in the first PRs**

- Create empty `libs/` stubs “to reserve the name.”
- A second Vite app, Module Federation, or `apps/rags-frontend`.
- A new `src/shared/`.
- Replace React Router with TanStack.
- Publish npm. Workspace vs publish waits until a real second consumer exists.

---

## 5. Alternatives considered

| Alternative | Why rejected |
| --- | --- |
| **Flat `FredPageModule` bag (first draft of this RFC)** | God object. Usage falsifies a single `gate`. Hosts will grow `if (module.x)`. |
| **Add `pages?` on `CapabilityUiPlugin`** | Makes every route look like an agent feature. Silent-skip / session-active-cap gating is wrong for URLs. Reasoning already showed this category error. `sessionProbes` already grew a fifth chat registry. |
| **Second type `UiSurfacePlugin` beside capabilities** | Two plugin systems. Contradicts “not a different mechanism.” One `definePage`, two folders that produce it. |
| **Hand-edited `catalog.ts` (capability-index analog)** | Fine for 3 plugins. Recreates the hotspot at 25+ pages. |
| **Class hierarchy (`extends FredPage`)** | Backend capabilities are classes because they have `tools()` / `middleware()`. Frontend plugins are plain objects. Pages have no methods to override. |
| **Module Federation / second app** | Needs store + Keycloak + i18n + bootstrap extracted. `#2307` / `#2296` deferred. One SPA, compile-time glob. |
| **File-based `src/routes/` / replace React Router** | Would relocate the entire `pages/` tree. |
| **Feature-flag matrix as the SKU** | Flags hide pixels. Rail entries are not flag-gated. Two unused flag surfaces already exist. |
| **Lift every page body into organisms first** | Scope inversion. Lift `DocumentWorkspace` when a second page needs it. |
| **Promote settings to new public URLs in v1** | UX change. Nested **child routes** under the same `/settings/:section` paths are not a URL change. |
| **Ten-PR programme (standalone + libs in this RFC)** | Consolidation. Committed work is 0, 1, 2, 3a, 3b, 4, 6. |
| **Team `<Protected>` on routes** | Contradicts `FRONTEND-AUTHZ-PATTERN.md`. |
| **Throw in production `createBrowserRouter` on duplicate id** | Fail in CI. Do not crash the SPA. |
| **Amend the HTML capability deck** | Deck is a slide show; “plugin” there already means chat slots. |
| **Wait until SI ships on swift (#2307’s wording)** | The *packaging extract* waits. The *in-SPA interface* unblocks every new page including SI. |
| **Three libs including `fred-frontend-shell` (third draft of this RFC)** | That package would pull Keycloak + RTK + MainLayout + Sidebar — the product minus page bodies. Second UIs want algebra + buttons, not Fred chrome. |
| **Put Fred `PageGate` / `PagePlacement` / `IconType` in `core/pages/`** | 25+ `page.module.ts` files would import Fred types; extracting a generic SDK later is a rewrite. |

---

## 6. Impact on existing contracts

| Surface | Committed PRs | Product-mode (out of this RFC) |
| --- | --- | --- |
| Runtime / control-plane frozen contracts | none | dated note in §3.1 + a new Contract Note — not “§8” |
| `FRONTEND_CODING_GUIDELINES.md` | add: a new page is `definePage` in `page.module.ts` | — |
| `FRONTEND-AUTHZ-PATTERN.md` | **amend** — settings already redirects (`TeamSettingsPage.tsx:48`); fix the stale `src/components/Protected.tsx` path. Team gates stay off `<Protected>` | — |
| `AUTHORING.md` + `add-fred-capability` | one paragraph: a capability management page is a page module, not a 6th plugin field; also document today’s missing steps (plugin index + `store.tsx`) | — |
| `FORKING_GUIDE.md` | a new *screen* is a page module upstream, not a fork patch | — |
| HTML capability deck | **do not amend** | — |
| URLs | preserve every current path | allowlist may 404 hidden modules |

---

## 7. Non-goals

- Shipping RAGs / SI / slim-ingest pages in this RFC’s PRs (they are consumers, own issues).
- Re-scoping `#2307`.
- Creating or publishing `@fred/page-sdk` / `@fred/ui` **in this RFC's PRs**. Destination remains §4.9. Extract is a **new** RFC when a second consumer exists — not a deferred row here.
- Redesigning evaluation’s inner `useState` wizard into routes.
- Temporal-in-activity design.
- Fixing `update-evaluation-api` (own issue; do not add new targets to `update-all-apis` until it is removed or repaired).
- Plugin-local i18n (increment after the host works).
- Changing ReBAC or `Protected`.
- Killing the `store.tsx` capability-API hotspot in a page increment (that is an `apis` field on `CapabilityUiPlugin`, later).
- Migrating marketplace / help / rail / standalone chrome in this RFC. Team primary **is** in (PR 3).

---

## 8. Open questions

1. **Author name** on disk.
2. **Product-mode in the same GitHub issue?** Recommendation: **no** — follow-up. (No issue is opened until the developer asks.)
3. **`import.meta.glob` from increment 1?** Recommendation: **yes** (flipped from the first draft). The capability index is the wrong analog. Help markdown already globs.
4. **Help:** stay a 4-row host-rail entry that `window.open`s? Recommendation: **yes**.
5. **Team landing** is first visible primary nav entry by `order` (today: agents)? Recommendation: **yes**.
6. **Capability-enabled management pages:** add a Fred pred in `host/fredGates.ts` only when the first such page exists (YAGNI until then).
7. **Lib names / publish:** **`@fred/page-sdk` + `@fred/ui`**. Drop `fred-frontend-shell`. Scope and publish wait until a real second consumer exists.
8. **Scope A or B (§9)?** **Decided: B**, then **split PR 3** into 3a (navbar primary) and 3b (chat remount). The 18 commits on `TeamContentNavbar` are **not** mostly the primary list — see §9.

---

## 9. Implementation sequence (after implementation is confirmed)

**PR 0 is not optional** — every later fitness column is decorative until vitest is on the frontend CI matrix.

**Committed: scope B, with PR 3 split.** PRs 0, 1, 2, **3a**, **3b**, 4, 6.

Last 90 days: `router.tsx` **22** commits, `TeamContentNavbar.tsx` **18**. Do **not** say this RFC “retires both hotspots.” Of those 18, the primary nav list is a small slice (branding nickname/icon `#1842` / `#1871`). Settings entries (`#2123`, `#2162`) are PR 4. The banner/role/header block is the plurality and stays hand-wired chrome — **retired by neither 3a nor 4**. `#2301`'s 86 changed lines in this file (`39+`/`47−`) are all banner/header churn (shield glyph removed, `bannerStyle` dropped, container renamed to `mainNavPanel`, `#2298` panel header) — zero of them touch `navigationItems` / `settingsItems` / agents / resources / prompts. The banner bucket is ~6 of 18; the primary list stays at 2–3.

B1–B7 land in PRs 0–1. Rail/standalone, store `apis`, `DocumentWorkspace` lift, and `libs/` extract stay **out of this RFC**.

| PR | Size | What | Done when | Fitness test that must go red |
| --- | --- | --- | --- | --- |
| **0** | S | Add `check: test` that runs **`make test` verbatim** (no extra flags) to `frontend-code-quality` in `.github/workflows/Check-pending-requests.yml`. Today that matrix is only `type-check` and `format-check` (`:186–190`). Measured 2026-08-18 on this tree: **137 files / 1,340 tests passed** (1 file, 2 tests skipped), **~40s** local on vitest 4.1.7. `make test` is `npm run test:coverage` — CI adds coverage + cold `npm ci` on top of that 40s; still S. | A failing frontend unit test fails the PR check | A thrown-away `it.fails` is red on CI. **Mandatory:** this is the guard for vitest 4.1.7 exiting 0 when a reporter fails to load (`ERR_LOAD_URL`, zero tests run). |
| **1** | M | Generic `core/pages/*` + `host/` (glob, `buildRoutes`, bound `definePage`, tri-state gates). One fake `page.module.ts`. `composePageCatalog` **and** `buildRoutes` return `{ …, errors }`. Parent-prefix check on every absolute child (settings layout is the dangerous parent). Extend `router.test.tsx` with a **sorted path inventory**. | Fake page appears in routes + nav without `router.tsx` naming it. A deliberately illegal settings child is dropped and recorded; `createBrowserRouter` is not called with it. Inventory matches today's `routes` export | Purity: `core/pages/**` except `host/` imports store / Keycloak / slices / pages / `IconType`. `evaluateGate.ts` contains `"platform"`. Inventory snapshot ≠ `collectPaths(routes)`. A fixture with a typo'd absolute settings child appears in `errors` and not in `routes` |
| **2** | M | Migrate **admin** (7 pages + kea URL-only). `AdminNavbar` = `navItems("admin")`. Host-only `badge` for task count. | Stub admin page = `page.module.ts` only. Inventory still green | `AdminNavbar` matching `/admin/teams` as a string literal |
| **3a** | M | Team **primary list + Back `href` only**. Agents, resources, prompts (`t(...)`). Usage stays a sibling **nav** item (settings group) if it is already a one-liner here; do not remount chat. Banner, ChatList, settings-mode swap stay chrome. Land **before** PR 4; do not parallelize — both edit `TeamContentNavbar`. | Primary list generated. Inventory still green | `` `/team/${teamId}/agents` `` in `TeamContentNavbar` only |
| **3b** | L | Chat route + `remountOn: ["agentInstanceId"]`. Separate risk class: composer state mid-conversation. ChatList / AgentCard URLs stay hardcoded. | Managed-chat URL still remounts on agent change. Inventory still green | Remount key missing / chat path literal only in this PR's page module |
| **4** | M | Settings as **child routes** of a settings layout (same URLs + unknown-section catch → members). One gate table. Usage stays a sibling module (URL open, nav gated). Team ctx `unknown` until both readiness predicates **on collaborative teams only**. No team `<Protected>` | Navbar and page cannot disagree. Usage URL 200s; nav hidden when not elevated | Adding team `<Protected>` in `buildRoutes` fails. Redirecting on `unknown` fails |
| **6** | S | `FRONTEND_CODING_GUIDELINES.md` + `FRONTEND-AUTHZ-PATTERN.md` path/redirect amendment + skill one-liner | New *admin, settings, or team-primary* page implements the interface | — |

**Explicitly not in this RFC:** standalone / rail / `placementForPath` for `/dev` (old 5); `apis` on `CapabilityUiPlugin` (old 7); lift `DocumentWorkspace` (old 8); create `libs/` (old 9–10). §4.9 remains the library *destination* so increment 1 does not paint the extract into a corner. `libs/fred-frontend-shell` stays rejected.

---

## 10. Tracking

- This file is the tracking design artefact.
- A GitHub issue is **not** opened until the developer asks. Do **not** reuse `#2307` (SI CRUD).
- When SI rebases from `mvp/rags-support`, it becomes a `definePage` consumer (flag on **nav only**, route stays `<Protected requires="admin">`).

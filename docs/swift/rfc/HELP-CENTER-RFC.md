# RFC — In-App Help Center (Wiki-Style User Documentation)

**Status:** In progress — HELP-01.A (shell) + HELP-01.B (search) + HELP-01.C (content) implemented 2026-07-31/08-02. **Content is a first draft — see "Content maturity" below.**
**Author:** Maxime Daragon (drafted with Claude Code)
**Date:** 2026-07-31
**Area:** `frontend` (v1 is frontend-only — no backend change)
**Tracks:** `HELP-01`

> **⚠️ Content maturity — first draft, review by iteration (2026-08-02).**
> The Help Center **mechanism** (routing, rendering, search, anchors, i18n,
> mermaid) is functional, but the **written content is an explicit first draft**
> and is not to be treated as final or authoritative. It was produced quickly to
> establish structure, tone, and coverage; it still needs to be reviewed and
> refined **iteratively**:
>
> - factual review against the real product/code by a domain owner (the
>   Architecture section is grounded in the frozen contracts, but the rest is
>   best-effort and may drift as the product changes);
> - editorial/tone pass and terminology consistency (fr/en parity);
> - the ~21 `![TODO]` screenshot placeholders are unfilled;
> - some sections are deliberately thin and will be expanded (and possibly new
>   sections added) in later passes.
>
> Treat every page as a starting point, not a finished reference. Corrections
> are cheap: content is plain markdown under
> `apps/frontend/src/rework/features/helpCenter/content/` — anyone can edit a
> page without touching React code (see the `content/README.md`).

## 1. Problem

The platform has no user-facing documentation surface. New users have no
guided entry point ("what is a team, an agent, a prompt?"), existing users
have no reference for features, troubleshooting, or FAQ, and support
questions that a doc page would answer land on humans. The only related
affordance today is the optional `contactSupportLink` external link in the
profile menu (`UserProfile.tsx`).

## 2. Proposed change

A **Help Center**: a dedicated, wiki-style documentation page, opened in a
new browser tab from the profile menu, with its own shareable URL space.

### 2.1 Entry point

- New `MenuPopoverItem` in `UserProfile.tsx`, directly **below "Profil"**,
  icon `help` (outlined), label `rework.profileMenu.helpCenter`
  (fr "Centre d'aide" / en "Help Center").
- Opens in a **new tab** (`window.open("/help", "_blank", "noopener")`),
  same pattern as the existing `contactSupportLink` item.

### 2.2 Routing — shareable URLs

New top-level route family in `common/router.tsx`, **outside** the team
layout (the Help Center has its own full-page layout, no team rail):

```
/help                          → redirects to /help/<lang>/getting-started
/help/:lang                    → redirects to first section
/help/:lang/:sectionId         → section index page
/help/:lang/:sectionId/:pageId → article page
```

- `:lang` ∈ `fr | en` (the two locales already supported by i18next).
  Putting the language in the URL makes every shared link unambiguous.
- Deep links to a heading use URL fragments: `/help/fr/features/agents#créer-un-agent`.
- The route is authenticated like the rest of the app (same Keycloak guard):
  the Help Center describes a logged-in product and is not a public site.

### 2.3 Content model — markdown files in the repo (the core decision)

Every page is a **markdown file** checked into the frontend source tree.
The React app renders them; users never see the format.

```
apps/frontend/src/rework/features/helpCenter/content/
├── manifest.ts                # section order, ids, icons, i18n title keys
├── fr/
│   ├── getting-started/
│   │   ├── index.md           # section landing page
│   │   └── <page>.md
│   ├── features/…
│   ├── guides/…
│   ├── troubleshooting/…
│   ├── faq/…
│   ├── architecture/…
│   └── changelog/…
├── en/                        # mirror tree, same file names
└── assets/                    # images, shared by both languages
```

- Each `.md` file starts with a small **frontmatter** block:
  `title`, `order`, optional `description` (used by search results).
- Files are loaded with Vite's `import.meta.glob` — lazy per page for
  rendering, eager raw for the search index (see §2.6). Adding a page =
  adding a file; **no code change, no registry edit**.
- The seven sections (fixed in v1, declared in `manifest.ts`):
  Getting started / Features / Guides & use cases / Troubleshooting /
  FAQ / Technical architecture / Changelog.
- A `README.md` in `content/` documents the authoring conventions
  (frontmatter, images, anchors, cross-links) so pages can be written or
  edited by hand without touching React code.

**Why files, not a database/CMS:** content is versioned with the code —
the docs shipped with v2.1.X describe v2.1.X; authoring goes through the
normal PR review; no new backend surface, storage, permissions, or editor
UI. An in-app editor for platform admins was considered and **deferred**
(§6).

### 2.4 Layout

Two-pane wiki layout, full viewport (no team sidebar):

- **Left sidebar** (background `surface-container`):
  - Section headers: height 32 px, font `label-medium`, color
    `on-surface-retreat`.
  - Page items: reuse `NavigationMenuItem` (same component as the team
    navigation rail — NavLink-based, active-state handling for free).
  - `Divider` between sections.
- **Right pane**: the rendered article.
  - **Breadcrumb** at the top: reuse the existing
    `shared/molecules/Breadcrumb` (same component as team resources).
  - Article body: rendered by the existing
    `shared/molecules/MarkdownRenderer`, extended (or thinly wrapped as
    `HelpMarkdown`) with heading anchors (§2.5) and image resolution from
    `content/assets/`.

### 2.5 Cross-cutting features

| Feature                | Design                                                                                                                                                                                                                                                                                                                                                          |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Global search**      | Client-side. A lazy-built index over all pages of the current language (frontmatter `title`/`description` + headings + body text, weighted in that order). Search field in the Help Center header; results list page title + section + matching snippet; selecting a result navigates to the page (and heading anchor when the match is a heading). No backend. |
| **Breadcrumb**         | `Help Center › <Section> › <Page>`, existing `Breadcrumb` molecule.                                                                                                                                                                                                                                                                                             |
| **Language switch**    | Toggle in the Help Center header — swaps `:lang` in the URL **and** calls `i18n.changeLanguage` (keeps chrome and content consistent). If the target page doesn't exist in the other language, fall back to the section index.                                                                                                                                  |
| **Share page link**    | Icon button (`content_copy` → `check` feedback) copying the canonical URL — same pattern as `PromptViewDialog`'s copy button.                                                                                                                                                                                                                                   |
| **Share heading link** | Every `h2`/`h3` gets a stable slug id; hovering shows a link icon that copies `<page-url>#<slug>`. On load, the page scrolls to `location.hash`.                                                                                                                                                                                                                |

### 2.6 Search index & performance

- Article files are **lazy-loaded** per route (Vite code-splits each `.md`).
- The search index is built **on first focus of the search field** from
  `import.meta.glob(..., { query: "?raw", import: "default" })`, then cached
  for the session. Expected corpus is tens of pages / a few hundred KB —
  no measurable impact on app startup (the Help Center bundle is itself
  lazy-loaded behind its route).

## 3. Alternatives considered

1. **DB-backed content + admin editor UI (mini-CMS)** — rejected for v1:
   multiplies scope (control-plane storage + CRUD API + REBAC + markdown
   editor + image upload + per-language management + versioning) and
   decouples doc version from app version. Kept as a possible v2 (§6).
2. **External doc site (static site generator, separate deployment)** —
   rejected: loses in-app integration (auth, theming, language sync with
   the app, deep links from future in-app "?" affordances), adds a
   deployment artifact.
3. **Reusing `contactSupportLink`-style external URL per customer** —
   rejected: not versioned with the product, empty by default.

## 4. Impact on existing contracts

- **None on backend contracts** — v1 touches no API. `RUNTIME-EXECUTION-CONTRACT.md`
  and `CONTROL-PLANE-PRODUCT-CONTRACT.md` unaffected.
- Frontend: new lazy route family under `/help`, one new item in
  `UserProfile.tsx`, new `features/helpCenter/` folder. Reuses
  `NavigationMenuItem`, `Breadcrumb`, `MarkdownRenderer`, `MenuPopoverItem`,
  `Icon`, i18next.
- `docs/swift/ux/COMPONENT-UX.md`: add Help Center entries when implemented.

## 5. Delivery plan

1. **HELP-01.A — Shell**: route family, layout (sidebar + article pane),
   manifest, profile-menu entry, breadcrumb, language switch, share-link
   buttons, heading anchors. Ships with placeholder pages.
2. **HELP-01.B — Search**: client-side index + search UI.
3. **HELP-01.C — Content**: the actual pages, section by section, from the
   agreed content plan (authored via outline → draft → review workflow;
   screenshots supplied by the developer against `TODO` placeholders).

## 6. Deferred / future work

- **Admin in-app editor** (platform_admin edits pages/sections from the UI):
  would require a control-plane content store + API + editor; only worth an
  RFC of its own if non-developers must maintain content.
- **Changelog auto-feed** from `docs/releases/` release notes.
- Public (unauthenticated) exposure of the Help Center.
- Contextual "?" links from app screens to specific help pages (cheap once
  URLs are stable — candidate for HELP-02).

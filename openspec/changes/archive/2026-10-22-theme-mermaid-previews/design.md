## Context

See [proposal.md](proposal.md) for motivation and scope. At base `39c13c8f5`, `MermaidBlock.tsx` statically imports Mermaid, initializes its stock light/dark theme, tries raw source and then `sanitizeMermaidForParsing`, and shares the resulting SVG between inline and enlarged views. `MarkdownRenderer` also serves Help Center and other Markdown surfaces; its tests currently stub MermaidBlock. `useIsDark` observes mode only, not the selected UI theme.

Fred already has complete theme tokens, local fonts, DOMPurify usage and per-component CSS modules. The evaluated beautiful-mermaid 1.1.3 exposes CSS-variable colors and six diagram families, but emits document-wide SVG styles, fixed internal IDs and Google Fonts imports. Its parser does not accept every syntax accepted by Mermaid, including the existing one-line `graph TD; A-->B` test example.

## Goals / Non-Goals

**Goals:** Keep the replacement within the shared molecule and a small co-located rendering adapter; preserve the existing component API and Markdown routing.

**Non-Goals:** No separate viewer route, palette picker, new theme tokens, worker framework, backend changes, new pan/zoom controls or export features. Existing `mindmap` JSON rendering stays separate.

## Decisions

### Use beautiful-mermaid by default with a compatibility path

Add beautiful-mermaid and load rendering engines on demand from the existing effect, with cancellation for superseded source. Keep layout work outside React's render function. The local adapter owns renderer selection and output preparation; avoid a general plugin registry.

Try the original source with the preferred renderer when compatible, then with official Mermaid when unsupported or rendering fails. Only after raw-source attempts fail, reuse the existing syntax repair and retry. A conservative syntax gate also routes late/revised node or participant labels, unsupported ER cardinalities and combined ER key constraints to official Mermaid, because the preferred parser silently loses information in those cases. Cover supported constructs with actual renderer fixtures. Keep Mermaid's strict security behavior and serialize its global initialization with each render.

Removing Mermaid entirely would regress diagram families and existing syntax. Adding a second user-selectable renderer would duplicate UI and leave existing consumers on the old path.

### Bind renderer defaults to Fred tokens

| Diagram role                    | Existing token             |
| ------------------------------- | -------------------------- |
| Background                      | `--surface-container`      |
| Main labels                     | `--on-surface`             |
| Secondary labels and connectors | `--on-surface-retreat`     |
| Accent and arrowheads           | `--primary`                |
| Node surfaces                   | `--surface-container-high` |
| Node borders                    | `--outline-variant`        |
| Font                            | `--font-family-base`       |

Use CSS-variable references in beautiful-mermaid so color changes follow the cascade. For Mermaid's compatibility configuration, resolve effective token values and refresh when theme or mode changes. Recompute layout when the active font changes. Renderer-controlled defaults must not depend on library theme presets; explicitly authored diagram styling remains content.

Preserve the existing body/header surface hierarchy, copy behavior and FullPageModal. Both views use the same rendering policy and token mapping.

### Prepare SVG at the shared boundary

Declare beautiful-mermaid, DOMPurify and css-tree as direct dependencies. Parse CSS to remove remote font rules, scope selectors and animations, and rewrite references without changing path data. Use Fred's local font tokens. Prefix internal IDs and local or absolute same-document references separately for each inline or enlarged view. Scope the inert template before sanitizing so legitimate IDs such as `title` survive DOM clobber protection. Enable DOMPurify's documented HTML integration point only within these SVGs to retain Mermaid's foreignObject labels while sanitizing their HTML. Do not install global SVG/text styles or change Markdown sanitization.

Retain the SVG's natural minimum width with horizontal scrolling on narrow screens so labels stay legible. The enlarged view overrides Mermaid's generated maximum width. Preserve an open modal while theme rendering refreshes, with focus entering its close button and returning to the enlargement trigger.

### Validate the replacement on existing surfaces

Add co-located fixtures for the six supported families, a semicolon header, pie/Gantt compatibility, repaired labels and invalid/untrusted input. Test the real preferred renderer and SVG preparation, then component behavior for copy, modal, cancellation, theme updates and simultaneous diagrams. Validate the actual shared MarkdownRenderer in the browser, including a narrow viewport and a deployment theme override. Trace chat/Help Center callers and record any unverified authenticated routes. No additional product demo page is needed. Keep the existing COMPONENT-UX.md example as the reproducible usage sample.

## Risks / Trade-offs

- Incomplete Mermaid compatibility: route unsupported constructs to official Mermaid and require regression fixtures for observed gaps.
- More frontend bytes while both engines remain: load engines on demand and verify both development serving and the production build.
- SVG style/reference leakage or a sanitizer stripping useful geometry: test multiple views, malicious labels and representative actual output in a browser-faithful DOM.
- Font-dependent label sizing and contrast: visually verify all three shipped themes in both modes and a deployment override; adjust token use within the existing design system.

## Migration Plan

Normal frontend deployment activates the replacement; no data or configuration migration is required. Record `impact: none` in the PR migration note. Roll back by deploying the previous frontend image. Obtain scope confirmation before implementation; after verification and independent review, reconcile tasks and sync/archive this change.

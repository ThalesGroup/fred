## Context

See proposal.md for motivation and scope. The producer already copies an explicit allowlist into disposable `.generated` inputs and exposes adapters from `ui/src/index.tsx`. Canonical KpiStatCard and tables use react-i18next; tables use OptionModel. InlineDrawer uses usePaneResize, which uses the React-only useLocalStorageState hook. Toast directly imports the large chat clipboard utility. Existing archive requirements explicitly defer several requested components; this delta removes that restriction for the reviewed surface.

## Goals / Non-Goals

**Goals:** Keep one maintained implementation, preserve FRED behavior, and expose closed neutral declarations with existing scoped styles and Material Symbols boundaries.

**Non-Goals:** New packaging architecture, publication tooling changes, application migration, or domain-specific controls. Existing ten-export tests remain as regression coverage; new coverage extends them.

## Decisions

- Refactor canonical sources in place. Export prop interfaces and required generic/table types; add root adapters only where icon narrowing is needed, following the existing Icon/Button pattern. Do not copy maintained implementations into the package.
- Replace translation hooks in KPI/table primitives with typed label props and neutral defaults. Count/page-dependent labels use typed formatters. Update FRED call sites to pass existing translation results or formatters; use only small application wrappers where they materially avoid duplicating translation wiring.
- Preserve application-only custom icons in canonical PageEmptyState; narrow its generated package input to MaterialIconType using the existing disposable-copy adapter pattern.
- Replace OptionModel with the existing neutral SelectOption contract and narrow packaged icon fields to Material Symbols. Keep sorting, selection, and client/server pagination semantics unchanged.
- Allowlist usePaneResize and its React-only useLocalStorageState dependency as internal inputs, resolving their canonical aliases through the build pipeline. This preserves resize and persistence instead of dropping a supported drawer feature. Exercise restricted storage access in focused verification; fix only what is necessary for independent drawer use.
- Inject a typed copy callback through ToastProvider and direct Toast props; consumers own copying, and FRED passes its existing writeRichClipboard action. Add configurable copy/dismiss labels. Do not package chat serialization machinery. When no action is supplied, omit the copy control.
- Move the evaluation pill's visual treatment into StatusBadge, reuse existing semantic tokens, and retain evaluation's domain-to-tone mapping in its current owner. Remove only the superseded pill styles.
- Extend the allowlist, build/declaration checks, archive expected exports, fixture imports/type-negative checks, browser tests, and CI-input evidence together. Internal hooks and support components stay private.

## Risks / Trade-offs

- [Translation wiring changes many callers] → Locate all affected imports and preserve translation keys, format arguments, and existing tests.
- [New aliases/transitive dependencies escape the package] → Explicitly allowlist dependencies and verify the actual tarball's declaration/runtime closure in the isolated consumer.
- [Drawer/storage or toast positioning assumes the FRED shell] → Exercise these controls inside themed consumer roots, including blocked storage and multiple instances.
- [Badge extraction changes evaluation appearance] → Reuse current pill styles and verify all tones in both themes.
- [Release fixtures hardcode alpha.2] → Update selected UI candidate references and generated lockfiles; preserve historical published evidence and unrelated token/SDK versions.

## Migration Plan

Update canonical components and FRED consumers together, then prepare the UI-only alpha.3 candidate and package documentation. Run required regression and packed-consumer gates before committing implementation blocks and opening the draft PR. Publication remains a separately authorized protected workflow operation. Consumer adoption belongs to the follow-up issue; rollback of the code change restores alpha.2 behavior without overwriting any published coordinate.

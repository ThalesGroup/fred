## Why

The standalone evaluation application cannot reproduce FRED's evaluation screens using the ten components published in `@fred-oss/ui@0.1.0-alpha.2`. Issue [#2887](https://github.com/ThalesGroup/fred/issues/2887) requires the missing canonical components in alpha.3 with neutral public contracts.

## What Changes

- Export TextArea, Switch, ProgressBar, IndicatorDot, Disclosure, Breadcrumb, PageHeader, SelectableCard, FileDropzone, ServiceNotice, and PageEmptyState from the existing package root.
- Neutralize and export KpiStatCard, DataTable, TablePagination, InlineDrawer, Toast, and ToastProvider, including the provider's useToast hook and the types needed to consume them.
- Add a token-based StatusBadge atom with five tones and migrate evaluation StatusPill to it.
- Preserve FRED translations and interactions through caller-supplied labels and application-owned clipboard injection; retain drawer resizing through its existing neutral hook dependency chain.
- Extend archive validators, isolated consumer type checks, and browser smoke to cover the complete surface in both themes. Prepare UI version `0.1.0-alpha.3` and release documentation without publishing.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-package-archives`: Extend the reviewed neutral UI surface and its canonical-source, declaration, theme, and interaction evidence.

## Impact

- Canonical atoms/molecules and their FRED consumers under `apps/frontend/src/rework/`; evaluation StatusPill delegates to StatusBadge.
- `libs/frontend/ui/src/index.tsx`, the canonical input allowlist, build/archive validators and tests, React consumer fixture, and browser smoke harness under `libs/frontend/`.
- UI manifest/changelog/README, producer lockfile and affected fixture release coordinates; existing protected release machinery remains authoritative.
- Extend the existing archive capability rather than the active release-foundation or independent-release changes: those govern publication tooling, a separate outcome.
- Excludes task-specific badges/progress, ingestion StatusChip, ConfirmationDialog, charts, evaluation application migration/removal, and actual npm publication.

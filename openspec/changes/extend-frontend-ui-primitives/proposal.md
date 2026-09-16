## Why

The published `@fred-oss/ui` foundation exposes five primitives, but neutral React applications still need reusable selection, confirmation, hints, removable labels, and native checkboxes. These five canonical FRED components currently rely on application translations, models, or body portals, so they cannot simply be exported as-is.

## What Changes

- Add `Dialog`, `Select`, `Chip`, `Tooltip`, and `Checkbox` plus reviewed public prop and option types to the existing root export; retain the five existing exports and styles contract.
- Correct canonical application boundaries and accessibility, with a thin translated FRED Dialog wrapper, a generic Select option contract, and internally owned portals that retain a consumer-owned `.fred-ui` theme.
- Generate from an expanded explicit canonical allowlist; extend archive, declaration, icon, CSS, isolated-consumer, browser, and CI-input validation without weakening design-token, SDK, or existing UI guarantees.
- Select an unused UI-only prerelease, synchronize UI metadata/lockfiles, and document the new API. Preparation and local tests are not publication or registry-verification evidence.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-package-archives`: extend the reviewed UI export, styling, accessibility, archive, isolated-consumer, and browser contract for exactly five additional primitives while preserving all other package guarantees.

## Impact

Canonical shared components and internal Menu/MenuItem/Portal/viewport helpers under `apps/frontend/src/rework/components/shared`; `libs/frontend/ui` package generation and metadata; producer/archive/consumer/browser/CI tests; UI and component documentation. No RAGS, iframe SDK, token-package, registry, or application-host changes. The governing [frontend packaging RFC](../../../docs/swift/FRED-FRONTEND-PACKAGING-RFC.md) remains open for later work.

Tracking: [ThalesGroup/fred#2695](https://github.com/ThalesGroup/fred/issues/2695).

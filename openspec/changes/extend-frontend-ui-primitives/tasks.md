## 1. Prerequisites and compatibility

- [x] 1.1 Record exact branch/status/stashes, component caller inventory, and dependency graph; verify no affected application caller or shared type behavior is silently removed.
- [x] 1.2 Check npm exact UI versions and repository/workflow attempt history for the next alpha coordinate; record read-only evidence that the chosen version is unused and unattempted.
- [x] 1.3 Create or link focused tracking without reusing closed foundation/release issues; verify reference in proposal.

## 2. Canonical behavior

- [x] 2.1 Extract application-neutral Dialog primitive and translated FRED wrapper, preserving action props; verify existing Dialog callers and tests.
- [x] 2.2 Implement Dialog initial/contained/restored focus, title, dismissal and nested Select compatibility; verify canonical keyboard regressions.
- [x] 2.3 Introduce generic SelectOption/SelectProps and configurable empty text without OptionModel in the package; verify application and generic type tests.
- [x] 2.4 Preserve Select navigation, disabled options, naming, and Escape priority in Dialog; verify canonical interaction tests.
- [x] 2.5 Make Chip removal name safe/configurable and retain slots/tones; verify canonical interaction test.
- [x] 2.6 Add Tooltip Escape dismissal and preserve hover/focus/placement/description; verify canonical tests.
- [x] 2.7 Export Checkbox props and retain native/ref/controlled/uncontrolled/indeterminate behavior; verify canonical tests.
- [x] 2.8 Implement bounded internal portal/root strategy for all three overlays and safe cleanup; verify multiple-overlay, light/dark, nested, and legacy-FRED tests.

## 3. UI archive

- [x] 3.1 Expand explicit canonical source/style allowlist and bounded adapters for internal icons/aliases/models; verify exact build-source graph and no duplicate maintained implementation.
- [x] 3.2 Export exactly ten components and reviewed public types from root; verify closed declarations, peer externalization, and no internal subpath exports.
- [x] 3.3 Extend UI archive file/declaration/style/license/icon and reference checks without weakening existing negatives; verify actual packed archive positive and mutation tests, including rejection of JavaScript-only declaration targets and acceptance of valid `.d.ts` targets.
- [x] 3.4 Synchronize UI-only version metadata, producer lockfile, disposable consumer lock resolution, and changelog under pinned toolchain; verify release-contract/version-history/changelog checks and unchanged token/SDK coordinates.

## 4. Independent consumers and CI

- [x] 4.1 Extend the installed React consumer with all ten components and positive/negative public type checks; verify offline install, typecheck, and production build from actual tarballs.
- [x] 4.2 Extend browser smoke for Dialog, Select, Chip, Tooltip, Checkbox, theme/portal/focus/assets and no external requests in separate fresh light and dark contexts; verify separately provisioned Chromium and smoke execution without installation.
- [x] 4.3 Exercise UI-only transfer and consumer/browser validation against independently rechecked published token baseline; verify no historical CI ZIP, network, workspace, or checkout fallback in offline phase.
- [x] 4.4 Extend package-input and CI-selection coverage for every newly consumed canonical/style/helper/metadata input; verify focused tests and producer-wide regression selection remains separate.

## 5. Documentation and completion

- [x] 5.1 Update UI README, compatibility/component docs and factual changelog, correcting touched stale status text; verify links and examples against public types.
- [x] 5.2 Run producer release-contract/release tests, code quality, units, archive negatives, isolated consumers, browser, and UI-only gates with separate provisioning; record exact commands/results.
- [x] 5.3 Run affected application quality/build/canonical and host regressions under application toolchain; record exact commands/results.
- [x] 5.4 Run strict OpenSpec validation, disposable semantic composition, and git diff --check; record results without syncing/archiving unrelated changes.
- [x] 5.5 Obtain independent implementation review, resolve all in-scope findings, and leave the diff uncommitted with four stashes preserved; record findings and remaining publication prerequisites.

## Acceptance evidence

The exact local commands, toolchains, results, compatibility inventory, npm/workflow version check, independent review findings, UI-only transfer readiness, and disposable specification composition are recorded in [design.md](design.md#implementation-evidence-local-not-publication). Checkmarks represent implemented local requirements, not GitHub workflow execution, OIDC publication, or public-registry verification. Those operations remain outside this change and require a reviewed commit and manual maintainer action.

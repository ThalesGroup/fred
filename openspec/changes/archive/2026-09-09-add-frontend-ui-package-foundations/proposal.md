## Why

FRED has proven that `@fred/design-tokens` can be packed and consumed without a
source checkout, but external React applications still have no similarly verified
component artifact. This change establishes the smallest useful `@fred/ui` surface
from the existing FRED implementation while preserving the package archive and
application boundaries defined by the
[`FRED-FRONTEND-PACKAGING-RFC.md`](../../../../docs/swift/FRED-FRONTEND-PACKAGING-RFC.md).

Implementation tracking: [ThalesGroup/fred#2590](https://github.com/ThalesGroup/fred/issues/2590).

## What Changes

- Add an individual `@fred/ui` workspace member with named exports for `Button`,
  `IconButton`, `Icon`, `TextInput`, and `Spinner`, plus their explicitly reviewed
  prop and visual types. `TextArea`, `Checkbox`, `Switch`, `Chip`,
  `PageEmptyState`, overlays, and the wider component catalog remain deferred.
- Generate ESM JavaScript, TypeScript declarations, and an explicit
  `@fred/ui/styles.css` export from an allowlist of canonical files under
  `apps/frontend`. No second maintained component implementation is introduced,
  and FRED is not migrated to a registry dependency in this change.
- Correct the selected canonical components where their current internal contract
  is unsuitable for publication: export public prop types; narrow button sizes
  without changing the shared `ComponentSize`; restore `IconButton` focus styling
  and `className` composition; define icon accessibility; correct `TextInput`
  label, description, counter, native form-reset synchronization, ref, and native-prop
  behavior; and allow
  consumer-supplied `Spinner` status text.
- Limit the public icon contract to Material Symbols Outlined. Make exact binary
  provenance, the approved hash, glyph support, and complete license/notice content
  blocking archive inputs; do not guess or replace the canonical asset.
- Require consumers to install compatible React, React DOM, and
  `@fred/design-tokens` peers. Externalize React, React DOM, every subpath, and both
  JSX runtimes, and preserve explicit, optional Geist font loading.
- Compile all required component styles and the package-owned icon asset into a
  bounded archive. Scope shared base behavior to a consumer-owned `.fred-ui` root
  and exclude document- or shell-wide effects.
- Extend the existing package producer, archive validator, isolated-consumer,
  browser, Makefile, and CI-selection contracts for a second archive while keeping
  every design-token acceptance and negative test effective. Archive validation
  structurally proves selector containment and requires runtime JavaScript references
  to resolve to executable packaged modules independently of declaration closure.
- Add an isolated React consumer that installs both tarballs outside FRED, then
  type-checks, builds, and exercises all exports without workspace links or access
  to producer sources. Provision lockfile-pinned registry dependencies and browsers
  separately from offline validation and local-only browser execution.
- Document the producer and consumer boundary and the component corrections. Keep
  iframe SDK work, protocol/authentication changes, registry publication, FRED
  registry adoption, and RAGS changes outside this change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-package-archives`: extend the existing self-contained archive,
  isolated-consumer, browser-evidence, application-agnostic, and CI-selection
  requirements to the first React UI archive without weakening the shipped
  design-token contract.

## Impact

- The producer workspace under `libs/frontend/` gains the `ui` member, build and
  declaration configuration, Material Symbols license inputs, package-specific
  validation, and a private React consumer fixture.
- Selected canonical component files, styles, shared visual types, and their tests
  under `apps/frontend/src/rework/components/shared/` change to provide the reviewed
  public contract. The application remains the canonical owner and must retain its
  existing rendering and call-site behavior.
- `apps/frontend/src/styles/index.css`, the canonical Outlined font binary, the
  frontend manifest/lockfile React baseline, root/package orchestration, and the
  pull-request workflow become explicit UI-package validation inputs.
- The producer gains build-time React, TypeScript, Sass, and library-build tooling;
  the packed UI artifact has no bundled React and no application-state, routing,
  authentication, translation-catalog, backend-model, iframe, or RAGS dependency.
- Package and producer READMEs plus `docs/swift/ux/COMPONENT-UX.md` describe shipped
  behavior. The broader packaging RFC remains open for deferred components, SDK,
  release, migration, and external adoption work.

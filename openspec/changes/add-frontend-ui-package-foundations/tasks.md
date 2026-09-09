This checklist covers only the bounded `@fred/ui` package foundation described by
this change. A checkbox is complete only when its stated evidence exists. Implementation
is tracked by [ThalesGroup/fred#2590](https://github.com/ThalesGroup/fred/issues/2590).

## 1. Compatibility and asset evidence

- [ ] 1.1 Inventory every `Button` and `IconButton` size caller and every direct or
      transitive `IconCategory`, `IconType`, `isCustomIcon`, `toIconType`, cast, and
      dynamically supplied icon-name caller; record which values are validated versus
      trusted, and verify the inventory supports button-specific sizes and an
      Outlined-only package API without removing application behavior.
- [ ] 1.2 Establish the exact upstream source/version and redistribution obligations of
      the canonical Material Symbols Outlined binary, record the canonical SHA-256,
      complete license, and required notices under `libs/frontend/ui/`, and stop this
      change as blocked if evidence cannot establish them without guessing or replacing
      the asset.
- [ ] 1.3 Add a lockfile-pinned font inspection step and reviewed public glyph inventory;
      verify every exposed material icon name exists in the canonical binary, the packed
      binary matches its approved hash, and unsupported names fail validation.

## 2. Canonical component contract corrections

- [ ] 2.1 Refactor the canonical Icon module into one Outlined material primitive plus
      any application compatibility wrapper required by task 1.1; verify controls own
      their names, decorative icons add no accessible text, informative icons use only
      caller-supplied names, and current dynamic application callers retain tested
      behavior.
- [ ] 2.2 Export the reviewed component prop and visual types and introduce a
      button-specific `2xs | small | medium` type without narrowing shared
      `ComponentSize`; verify TypeScript rejects unsupported Button/IconButton sizes and
      existing frontend callers still type-check.
- [ ] 2.3 Merge caller `className` with IconButton's generated classes and repair its
      visible focus outline; add direct regressions proving caller and generated
      size/color/variant classes remain effective plus keyboard focus, loading,
      `aria-busy`, disabled, and badge behavior.
- [ ] 2.4 Correct TextInput effective ID and label association, merged help/error
      descriptions, invalid state, caller refs/handlers/native attributes, and
      controlled/uncontrolled character counting; add direct tests for caller IDs and
      refs, merged `aria-describedby`, disabled errors, native prop overrides, controlled
      values, default values, and subsequent edits.
- [ ] 2.5 Export Spinner props and add caller-supplied status text while retaining the
      `Loading` default and decorative mode; extend its direct tests to verify all three
      accessible-name cases.
- [ ] 2.6 Run the focused canonical component and affected-caller tests after the source
      corrections; verify no deferred component, application state, router,
      authentication, translation catalog, backend model, iframe, or RAGS dependency
      enters the selected source graph.

## 3. UI workspace member and build

- [ ] 3.1 Add `ui` to the private producer workspaces and update the producer manifest,
      lockfile, formatting/lint configuration, and Make targets with pinned compatible
      React 19.2.4, React DOM 19.2.4, TypeScript 5.9.3, Sass, library-build,
      declaration, and font-inspection tooling; verify `npm ci` selects and installs the
      individual members reproducibly.
- [ ] 3.2 Add the bounded `libs/frontend/ui/package.json`, public barrel, README, FRED
      license, third-party notices, and approved Material Symbols license inputs; verify
      only the root ESM/declaration entry and `./styles.css` are public, CSS is marked
      side-effectful, and the member remains independently publishable from the private
      workspace root.
- [ ] 3.3 Extend `scripts/package-inputs.mjs` with an ordered UI allowlist covering every
      selected canonical component, module style, shared type, Sass support file, icon
      declaration, font binary, React baseline manifest/lockfile, and license input;
      verify build and CI contracts consume the same inventory.
- [ ] 3.4 Implement clean UI generation/build for ESM JavaScript and a closed declaration
      graph; externalize React, React DOM, all subpaths, and both JSX runtimes, retain the
      actual build module graph as evidence, and verify generated outputs contain no
      source alias, checkout path, local link, bundled React module, or undeclared bare
      import.
- [ ] 3.5 Compile every selected CSS Module/Sass input and generated Outlined font face
      into `dist/styles.css`, with package-relative font URLs and required base behavior
      beneath `.fred-ui`; verify the CSS has no import, Geist copy, external URL,
      unscoped base selector, document selector, or shell scrolling/selection/layout
      mutation.
- [ ] 3.6 Add build tests for deterministic clean output, exact named exports and public
      types, declaration closure, source ordering, scoped CSS, peer ranges, build-graph
      externalization, font copying, and missing or unexpected canonical inputs; verify
      all mutations use disposable fixtures rather than application sources.

## 4. Archive validation

- [ ] 4.1 Refactor the current archive validator into shared safety checks and separate
      design-token/UI contracts; run the existing generator and archive test suite and
      verify every design-token positive and negative case retains its current meaning.
- [ ] 4.2 Implement the UI tarball contract over actual `npm pack --json` output,
      checking exact files and exports, ESM/declaration/CSS reference closure, peers and
      bare imports, CSS/asset closure, source/link bans, build evidence, font/glyph hash,
      and complete license/notice content; verify the valid archive reports all required
      evidence.
- [ ] 4.3 Add disposable negative archives for absent or escaping exports, missing JS or
      declarations, missing CSS/font/glyph/license/notice, unexpected files, invalid
      peers, bundled or undeclared modules, FRED aliases/paths, workspace/file/link
      protocols, CSS imports/external URLs/unscoped shell rules, and truncated or
      modified license content; verify each fails for the expected contract reason.
- [ ] 4.4 Add explicit per-member and combined pack-check commands and retained evidence;
      verify npm never packs the private root and both actual tarballs pass their own
      contract before any consumer test starts.

## 5. Isolated React consumer and browser behavior

- [ ] 5.1 Add a private, domain-neutral React consumer fixture with a committed lockfile
      for React 19.2.4, React DOM 19.2.4, TypeScript, and its production bundler plus an
      explicit dependency-provisioning target; verify provisioning may populate the
      producer cache but validation and browser targets never install or download
      prerequisites.
- [ ] 5.2 Stage only the fixture and both validated tarballs in a new OS temporary
      directory outside FRED, clear workspace/package environment, install from the
      prepared cache in offline mode, type-check every component/prop/type, and build
      production output; verify one consumer-owned React installation, no links, and no
      checkout or producer dependency resolution.
- [ ] 5.3 Add isolated-consumer negative tests for missing peers or prerequisites,
      workspace/symlink/source fallback, omitted explicit UI CSS, unresolved declarations
      or assets, and network-dependent installation; verify failures occur without
      weakening offline acceptance.
- [ ] 5.4 Extend the separately provisioned Playwright harness and staged consumer pages
      to render every public component in both themes and exercise Tab/Enter/Space,
      caller/generated classes, accessible names, informative/decorative icons,
      TextInput errors, disabled controls, IconButton loading, and default/custom/
      decorative Spinner states; verify the behavioral assertions pass in Chromium.
- [ ] 5.5 Add fresh-context asset checks for rendered Outlined glyphs, tokens/UI without
      Geist, and explicit packaged Geist opt-in; verify all stylesheet/font requests are
      local and successful, no unexpected font loads, and every failed/non-2xx,
      non-loopback, `file:`, checkout-path, or external-font-service request fails the
      smoke test.
- [ ] 5.6 Assert before and after UI style import that document/root overflow, selection,
      sizing, and theme ownership remain consumer-controlled; verify required box and
      shape behavior applies only beneath `.fred-ui` and no selected component creates a
      portal.

## 6. Repository integration and documentation

- [ ] 6.1 Extend `libs/frontend/Makefile`, scripts, and the root quality/test project
      integration with separate provisioning, build, per-member pack, dual-consumer,
      and browser commands; verify routine validation is offline after setup and existing
      target meanings remain compatible.
- [ ] 6.2 Extend `.github/workflows/Check-pending-requests.yml` and the tested path-filter
      contract for every new producer, canonical TSX/style/type/Sass, icon declaration,
      Material asset, React manifest/lockfile, license/notice, fixture, metadata, setup,
      and orchestration input; verify each category selects frontend-package validation
      and an unrelated application-only change may skip it.
- [ ] 6.3 Update `libs/frontend/README.md` and add `libs/frontend/ui/README.md` for
      canonical ownership, public imports/types, peer installation, `.fred-ui`, icon
      limits, optional Geist, provisioning, offline acceptance, and package/non-package
      boundaries; verify links point to the existing RFC rather than duplicating it.
- [ ] 6.4 Update `docs/swift/ux/COMPONENT-UX.md` for only the Icon, Button/IconButton,
      TextInput, and Spinner behavior actually corrected; verify deferred component,
      SDK, release, migration, and adopter documentation is not claimed as shipped.

## 7. Verification and review

- [ ] 7.1 In `libs/frontend`, run `make code-quality` and `make test`; verify producer
      lint/format and all design-token/UI positive and negative unit tests pass offline.
- [ ] 7.2 Run both actual archive pack checks and the neutral and React isolated-consumer
      targets; verify retained evidence records exact inventories, hashes, peer/import
      closure, offline installation, type checking, builds, one React runtime, and zero
      checkout links or references.
- [ ] 7.3 Provision the pinned browser only through the setup target, then run all browser
      smoke checks with non-loopback access denied; verify retained evidence covers both
      themes, every component and required state, Material/optional Geist behavior, and
      only successful local requests.
- [ ] 7.4 In `apps/frontend`, run `make code-quality`, `make build`, `make test`, and the
      focused component/caller regressions; verify the canonical corrections preserve
      the FRED application while protocol, request, path, host-page, and proxy tests stay
      green.
- [ ] 7.5 Run strict OpenSpec validation and `git diff --check`; verify no package or
      application implementation requirement remains unevidenced before handoff.
- [ ] 7.6 Obtain an independent implementation review of the complete diff, resolve every
      in-scope finding, and verify deferred components, overlays, iframe/auth/protocol,
      publication, FRED registry adoption, RAGS, issue closure, and OpenSpec archival
      remain outside this change.

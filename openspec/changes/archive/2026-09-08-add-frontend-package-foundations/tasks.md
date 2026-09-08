This checklist covers only the design-token package foundation and packed-archive
validation described by this change. UI components and icons, the iframe SDK, package
publication, FRED consumption, and external-adopter work belong in later GitHub issues
and OpenSpec changes rather than this checklist.

## 1. Producer workspace and asset provenance

- [x] 1.1 Verify the origin and applicable license/notice obligations of both canonical
      Geist font files, record the evidence in the package's third-party notice files,
      and fail the implementation review if the required texts cannot be established.
- [x] 1.2 Create `libs/frontend/package.json`, `package-lock.json`, and `Makefile` with
      Node `22.13.0`/npm `10.9.2` metadata, `private: true` on the workspace root, and
      package-targeted quality/test/pack commands; verify npm selects the member rather
      than packing the root.
- [x] 1.3 Add lockfile-pinned `@playwright/test` and an explicit Chromium-provisioning
      target to the producer workspace; verify ordinary test and smoke targets use an
      installed browser and never trigger dependency installation or browser download.

## 2. Design-token package generation

- [x] 2.1 Add the `libs/frontend/design-tokens/` manifest, README, license/notice
      inventory, and disposable-output configuration with only `./tokens.css` and
      `./fonts.css` public exports; verify the manifest has a bounded file list, CSS
      side effects, no runtime dependency, and no workspace/local-file reference.
- [x] 2.2 Implement the package generator from the reviewed canonical CSS allowlist and
      canonical Geist rules/assets, without maintained source copies; verify a clean
      rebuild produces both stylesheets and fonts and contains no shell-level selectors,
      Material Symbols, custom icons, aliases, or checkout paths.
- [x] 2.3 Add focused generator tests for source ordering, preserved light/dark tokens,
      separated optional fonts, rewritten package-relative URLs, missing/ambiguous Geist
      sources, and clean rebuild reproducibility; verify the tests pass offline.

## 3. Packed-archive and isolated-consumer gates

- [x] 3.1 Add a reusable archive validator under `libs/frontend/scripts/` that inspects
      the `npm pack --json` tarball rather than the build directory; verify it checks the
      export targets, exact packed inventory, dependency protocols, text references,
      CSS asset closure, and required license/notice files.
- [x] 3.2 Add positive and negative validator fixtures/tests for missing font/image/icon
      URLs, escaping or absent exports, unexpected files, absent notices, undeclared
      dependencies, FRED aliases/paths, and workspace or `file:` references; verify each
      invalid archive fails for the expected reason.
- [x] 3.3 Add the domain-neutral consumer fixture under `libs/frontend/fixtures/` and a
      test that stages only the fixture and tarball in a new directory outside the FRED
      checkout, clears workspace resolution, installs offline without links, imports both
      public stylesheets, builds standalone output, and verifies theme selectors and
      packaged Geist assets are present without any FRED path.
- [x] 3.4 Add a separate real-browser smoke harness over the staged consumer output with
      tokens-only and opt-in-font pages; verify representative light/dark computed color,
      spacing, radius, and typography styles and successful regular/italic Geist loading.
- [x] 3.5 Record browser requests in fresh contexts with caches and service workers
      disabled; verify the tokens-only page makes no font request and both pages reject
      `file:` URLs, checkout paths, non-loopback assets, and external font services.

## 4. Repository integration and documentation

- [x] 4.1 Add `libs/frontend` to the root `Makefile` quality/test project lists and wire
      distinct frontend-package validation into
      `.github/workflows/Check-pending-requests.yml`; verify the job runs quality, tests,
      pack, offline consumer, and browser smoke after a separate browser setup step.
- [x] 4.2 Define and test the CI selection contract for `libs/frontend/**`, every CSS file
      in the generator allowlist, the canonical Geist declarations and binaries,
      applicable license/notice inputs, and relevant root/workflow/setup orchestration;
      verify each category selects the package job while an unrelated application-only
      change does not.
- [x] 4.3 Document dependency and browser provisioning separately from offline archive
      installation/build and smoke execution, plus producer commands, canonical inputs,
      archive acceptance, and workspace
      root versus member publication semantics in `libs/frontend/README.md`, document
      consumer imports in the package README, and add only a short index link in
      `docs/swift/README.md`; reference the existing frontend packaging RFC instead of
      copying it, and leave the RFC open for its unimplemented packages and adoption.

## 5. Verification and handoff

- [x] 5.1 Run `make code-quality`, `make test`, the explicit pack check, and the isolated
      consumer check in `libs/frontend`; verify all pass from clean generated output and
      retain the resulting archive inventory and offline execution log as review
      evidence.
- [x] 5.2 Provision the pinned browser through the explicit setup target, then run the
      browser smoke with external network access denied; retain light/dark computed-style,
      font-loading, tokens-only no-font-request, and local-only request evidence.
- [x] 5.3 Run the existing frontend application protocol, request, path, host-page, and
      proxy tests plus `apps/frontend` code quality; verify this package-only slice did
      not change protocol `"1"`, origin/source validation, or host-owned authentication.
- [x] 5.4 Run strict OpenSpec validation and an independent review of the implementation
      diff; verify application sources, iframe/auth code, publication workflows, and
      RAGS remain untouched before handing later sequencing back to GitHub Issues.

## 6. Review hardening follow-up

- [x] 6.1 Reject CSS imports case-insensitively during canonical generation and packed
      archive validation, add lowercase/mixed/uppercase negative fixtures for both
      surfaces, and make browser smoke fail on request failures or unsuccessful HTTP
      responses.
- [x] 6.2 Enforce one shared reviewed token-CSS structure for generator and archive
      validation, preserving current canonical tokens, theme selectors, spectrum
      property registration, and forced-colors override while rejecting ordinary shell
      declarations and unreviewed selectors in disposable fixtures.
- [x] 6.3 Verify the complete packed Apache and Geist OFL license files against approved
      SHA-256 digests and add archive mutations proving truncation and modification of
      either license fail validation.
- [x] 6.4 Run producer quality/tests, archive validation, isolated-consumer and browser
      gates, plus the existing frontend protocol, request, path, host-page, and proxy
      regression checks; retain updated review evidence.
- [x] 6.5 Run strict OpenSpec validation and independent implementation review, resolve
      all in-scope findings, and verify RAGS, application sources, iframe/auth code,
      publication, and migration remain unchanged.

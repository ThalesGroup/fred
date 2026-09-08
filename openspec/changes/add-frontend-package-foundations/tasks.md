This checklist covers only the design-token package foundation and packed-archive
validation described by this change. UI components and icons, the iframe SDK, package
publication, FRED consumption, and external-adopter work belong in later GitHub issues
and OpenSpec changes rather than this checklist.

## 1. Producer workspace and asset provenance

- [ ] 1.1 Verify the origin and applicable license/notice obligations of both canonical
      Geist font files, record the evidence in the package's third-party notice files,
      and fail the implementation review if the required texts cannot be established.
- [ ] 1.2 Create `libs/frontend/package.json`, `package-lock.json`, and `Makefile` with
      Node `22.13.0`/npm `10.9.2` metadata, `private: true` on the workspace root, and
      package-targeted quality/test/pack commands; verify npm selects the member rather
      than packing the root.

## 2. Design-token package generation

- [ ] 2.1 Add the `libs/frontend/design-tokens/` manifest, README, license/notice
      inventory, and disposable-output configuration with only `./tokens.css` and
      `./fonts.css` public exports; verify the manifest has a bounded file list, CSS
      side effects, no runtime dependency, and no workspace/local-file reference.
- [ ] 2.2 Implement the package generator from the reviewed canonical CSS allowlist and
      canonical Geist rules/assets, without maintained source copies; verify a clean
      rebuild produces both stylesheets and fonts and contains no shell-level selectors,
      Material Symbols, custom icons, aliases, or checkout paths.
- [ ] 2.3 Add focused generator tests for source ordering, preserved light/dark tokens,
      separated optional fonts, rewritten package-relative URLs, missing/ambiguous Geist
      sources, and clean rebuild reproducibility; verify the tests pass offline.

## 3. Packed-archive and isolated-consumer gates

- [ ] 3.1 Add a reusable archive validator under `libs/frontend/scripts/` that inspects
      the `npm pack --json` tarball rather than the build directory; verify it checks the
      export targets, exact packed inventory, dependency protocols, text references,
      CSS asset closure, and required license/notice files.
- [ ] 3.2 Add positive and negative validator fixtures/tests for missing font/image/icon
      URLs, escaping or absent exports, unexpected files, absent notices, undeclared
      dependencies, FRED aliases/paths, and workspace or `file:` references; verify each
      invalid archive fails for the expected reason.
- [ ] 3.3 Add the domain-neutral consumer fixture under `libs/frontend/fixtures/` and a
      test that stages only the fixture and tarball in a new directory outside the FRED
      checkout, clears workspace resolution, installs offline without links, imports both
      public stylesheets, builds standalone output, and verifies both themes and packaged
      Geist assets resolve without any FRED path.

## 4. Repository integration and documentation

- [ ] 4.1 Add `libs/frontend` to the root `Makefile` quality/test project lists and add a
      distinct `libs/frontend/**` filter and frontend-package job to
      `.github/workflows/Check-pending-requests.yml`; verify unrelated application-only
      changes do not select the package job and package changes run all producer gates.
- [ ] 4.2 Document producer commands, canonical inputs, archive acceptance, and workspace
      root versus member publication semantics in `libs/frontend/README.md`, document
      consumer imports in the package README, and add only a short index link in
      `docs/swift/README.md`; reference the existing frontend packaging RFC instead of
      copying it, and leave the RFC open for its unimplemented packages and adoption.

## 5. Verification and handoff

- [ ] 5.1 Run `make code-quality`, `make test`, the explicit pack check, and the isolated
      consumer check in `libs/frontend`; verify all pass from clean generated output and
      retain the resulting archive inventory as review evidence.
- [ ] 5.2 Run the existing frontend application protocol, request, path, host-page, and
      proxy tests plus `apps/frontend` code quality; verify this package-only slice did
      not change protocol `"1"`, origin/source validation, or host-owned authentication.
- [ ] 5.3 Run strict OpenSpec validation and an independent review of the implementation
      diff; verify application sources, iframe/auth code, publication workflows, and
      RAGS remain untouched before handing later sequencing back to GitHub Issues.

# FRED frontend package producer

This private npm workspace builds distributable frontend packages from canonical
FRED sources. The current bounded slice produces only `@fred/design-tokens`; the
broader package architecture and sequencing remain in the
[frontend packaging RFC](../../docs/swift/FRED-FRONTEND-PACKAGING-RFC.md).

## Workspace and publication boundary

`private: true` applies to this workspace root and prevents treating its
orchestration manifest as a package. It does not make workspace members private
or configure their eventual registry, access policy, version, credentials, or
publication workflow. This change does not publish anything.

The design-token member generates disposable output from canonical files under
`apps/frontend/src/styles/` and `apps/frontend/src/assets/fonts/`. Do not copy
those sources into a second maintained tree. The ordered source inventory and CI
contract live together in `scripts/package-inputs.mjs`.

## Provisioning

Use the repository Node `22.13.0` and npm `10.9.2` baseline:

```sh
make install
make browser-install
```

`make install` installs the lockfile-pinned producer dependencies. The browser
target separately provisions Playwright's pinned Chromium and its system
dependencies. These are setup operations and may contact their package sources;
no validation target installs or downloads them.

## Offline validation

After provisioning, run:

```sh
make code-quality
make test
make pack-check
make isolated-consumer
make browser-smoke
```

- `make test` runs offline generator, archive, filter-selection, and isolated
  consumer tests.
- `make pack-check` validates the files in the actual `npm pack` tarball,
  including exports, CSS asset closure, dependency protocols, source-path
  leakage, and license/notice material.
- `make isolated-consumer` copies only the tarball and neutral fixture to a new
  OS temporary directory, installs with npm offline and without save, lock, or
  scripts, then builds standalone output without workspace links.
- `make browser-smoke` repeats that staging and uses the already installed
  Chromium against a loopback-only server. Fresh contexts verify light/dark
  computed styles, explicit regular/italic Geist loading, no tokens-only font
  requests, and no non-loopback or FRED-checkout asset requests.

Machine-readable review evidence is retained under `target/review-evidence/`.
Generated package files, tarballs, installed dependencies, browsers, and evidence
are disposable and ignored by Git.

## Package inputs and notices

The package consumes the token stylesheets declared in
`scripts/package-inputs.mjs`, the two Geist `@font-face` rules in the canonical
application `index.css`, the matching Geist binaries, the repository Apache-2.0
license, and the audited Geist OFL input. Any change to one of those inputs
selects the frontend-package CI job. An unrelated application-only change may
skip it.

Geist provenance, source hashes, copyright, and redistribution terms are recorded
in `design-tokens/THIRD_PARTY_NOTICES.md`; the complete OFL text is packed with
the font assets. A font hash change deliberately fails generation until that
audit is updated.

UI components and icons, the iframe SDK, registry publication, FRED package
consumption, and external adopter integration are outside this workspace slice.

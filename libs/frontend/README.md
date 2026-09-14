# FRED frontend package producer

This private npm workspace builds distributable frontend packages from canonical
FRED sources. It produces the implemented `@fred/design-tokens`, bounded `@fred/ui`, and
framework-independent `@fred/iframe-sdk` archive foundations; the broader package architecture and sequencing remain in the
[frontend packaging RFC](../../docs/swift/FRED-FRONTEND-PACKAGING-RFC.md).

## Workspace and publication boundary

`private: true` applies to this workspace root and prevents treating its
orchestration manifest as a package. It does not make workspace members private
or configure their eventual registry, access policy, version, credentials, or
publication workflow. This change does not publish anything.

The members generate disposable output from canonical files under
`apps/frontend/src/styles/` and `apps/frontend/src/assets/fonts/`. Do not copy
those sources into a second maintained tree. The ordered source inventory and CI
contract live together in `scripts/package-inputs.mjs`.

The UI member additionally consumes an explicit allowlist of five canonical React
components and their direct styles. Its public adapter narrows icons to Material
Symbols Outlined without removing FRED's application-only custom-icon compatibility.
The iframe SDK member copies the transport-neutral canonical protocol module from
`apps/frontend/src/rework/features/applications/applicationProtocol.ts` into disposable
build input and combines it with the allowlisted child client. FRED's host, request,
authorization, routing, and authentication code is not package input.

## Provisioning

Use the repository Node `22.13.0` and npm `10.9.2` baseline:

```sh
make install
npm --prefix ../../apps/frontend ci
make consumer-provision
make browser-install
```

`make install` installs the lockfile-pinned producer dependencies.
The separate frontend install provisions the lockfile-pinned test framework used by the direct
packed-SDK/production-host compatibility gate; the gate itself performs no installation.
`make consumer-provision` downloads the isolated React fixture and neutral iframe SDK
fixture's lockfile-pinned dependencies into separate dedicated caches. The browser
target separately provisions Playwright's pinned Chromium and system dependencies.
These setup operations may contact their package sources.

## Offline validation

After provisioning, run:

```sh
make code-quality
make test
make pack-check
make isolated-consumer
make host-integration
make browser-smoke
```

- `make test` runs offline generator, archive, filter-selection, and isolated
  consumer tests.
- `make pack-check` validates the files in all three actual `npm pack` tarballs,
  including exports, import-free token structure, CSS asset closure, dependency
  protocols, source-path leakage, and complete license/notice content. The iframe SDK
  validator parses JavaScript and declarations with the TypeScript compiler API, keeps
  runtime and declaration resolution separate, rejects computed runtime imports and
  parser failures, and checks every executable file with Node's parse-only native ESM
  grammar validation. Runtime specifiers must name exact executable files under native ESM
  rules (no extension or directory-index inference). Generation records runtime references
  through the same syntax-aware scanner.
- `make isolated-consumer` validates the neutral token consumer, a React consumer, and
  a framework-neutral iframe SDK consumer in fresh OS temporary directories. The
  consumers install actual tarballs and pinned dependencies only from prepared caches,
  type-check, and build without workspace links or FRED's dependency tree. The SDK
  fixture imports both public entry points and has no React or other FRED dependency.
  Missing cache data fails actionably.
- `make host-integration` validates and extracts the actual SDK tarball, then runs it against
  the production `TeamApplicationHostPage` message handler through the repository's frontend
  test framework. It covers context, routes and intents, response correlation and errors,
  capacity, and stale frame/team teardown. Raw protocol host tests retain legacy-client
  compatibility, while the separate cross-origin harness retains real browser-origin evidence.
- `make browser-smoke` performs no dependency install or browser provisioning. It uses
  the already staged consumer output and installed Chromium against loopback-only
  servers. Fresh contexts verify light/dark
  computed styles, explicit regular/italic Geist loading, no tokens-only font
  requests, every public UI component, keyboard/accessibility/error/loading behavior,
  local Material glyph rendering, successful stylesheet/resource responses, and no
  non-loopback or FRED-checkout asset requests. Separate loopback host, child, and
  attacker origins also exercise the packed SDK's admission, route, request, error,
  timeout, cancellation, disposal, and frame-replacement behavior.

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

The current UI archive, its public imports, `.fred-ui` ownership rule, peers, icon
limits, and optional Geist use are documented in [ui/README.md](ui/README.md). The
iframe client contract and its deliberately buffered transport are documented in
[iframe-sdk/README.md](iframe-sdk/README.md). Deferred components and overlays,
theme/live-locale protocol extensions, registry publication, FRED package consumption,
and external adopter integration remain outside these archive foundations.

Coordinate-independent release-contract, evidence, and registry-verification tooling is
documented in [RELEASE.md](RELEASE.md). Its fixture and proposed contracts do not confirm npm
scope ownership or authorize publication.

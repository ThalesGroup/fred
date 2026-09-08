## Why

The frontend packaging RFC requires proof that a registry-style artifact is complete
before FRED extracts React components or the iframe SDK. Today no frontend package
workspace or archive-level consumer check exists, and the application stylesheet mixes
reusable tokens and fonts with shell-only global rules.

This first independently reviewable slice establishes the design-token package boundary
and proves its packed artifact can be consumed without a FRED checkout. The broader
architecture and sequencing remain in
[`docs/swift/FRED-FRONTEND-PACKAGING-RFC.md`](../../../docs/swift/FRED-FRONTEND-PACKAGING-RFC.md).

## What Changes

- Add a private npm workspace root under `libs/frontend/`. Its `private: true` setting
  prevents publishing the workspace root; it does not make individual packages private
  or decide their eventual publication configuration.
- Add the first publishable package foundation, provisionally named
  `@fred/design-tokens`, with explicit token and optional Geist-font stylesheet exports.
  Package generation may read the existing canonical FRED CSS and font assets but must
  not create manually maintained duplicate sources.
- Produce a bounded npm tarball containing every file its public exports require,
  including CSS, fonts, license material, and applicable third-party notices.
- Add deterministic archive validation and a neutral isolated consumer that installs the
  tarball and build using only files and dependencies available outside the FRED
  checkout. Workspace links, local `file:` dependencies, source aliases, and fallback
  access to repository files are forbidden.
- Add package-foundation quality and CI entry points so archive validation is a required
  check when the producer workspace changes. Publication credentials and release jobs
  remain out of scope.
- Preserve the existing iframe protocol, authenticated request broker, application host,
  and external-consumer ownership boundary without modification.

## Capabilities

### New Capabilities

- `frontend-package-archives`: defines the self-contained design-token archive and the
  isolated installation/build evidence required before frontend packages can be treated
  as distributable artifacts.

### Modified Capabilities

None.

## Impact

- New producer and validation surface under `libs/frontend/`, including the workspace
  manifest and lockfile, design-token package metadata/build inputs, archive checks, and
  neutral consumer fixture.
- Pull-request validation will recognize `libs/frontend/**` and run its package quality,
  tests, pack, and isolated-consumer gates.
- The implementation reads current canonical token CSS and Geist assets from
  `apps/frontend/src/styles/` and `apps/frontend/src/assets/fonts/`; those application
  sources are not copied or otherwise changed by this slice.
- Package registry publication, npm scope ownership, React UI extraction, icons required
  only by future UI exports, iframe SDK extraction, protocol/theme changes, FRED package
  consumption, and RAGS adoption are deferred to later tracked changes.
- No backend, OpenAPI, authentication, authorization, iframe wire, or deployment
  behavior changes.

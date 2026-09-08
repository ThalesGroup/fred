## Context

See `proposal.md` for motivation and
[`docs/swift/FRED-FRONTEND-PACKAGING-RFC.md`](../../../docs/swift/FRED-FRONTEND-PACKAGING-RFC.md)
for the broader package and external-application architecture.

FRED currently has one private application package at `apps/frontend/` and no
JavaScript workspace under `libs/`. Its reusable token definitions are separate CSS
files under `apps/frontend/src/styles/`, but `index.css` also owns Geist and Material
Symbols font faces, semantic helper selectors, and shell-wide `html`, `body`, selection,
and scrollbar rules. Geist binaries live under `apps/frontend/src/assets/fonts/`.

The current host already implements protocol `"1"`, exact origin/source validation, a
15-second handshake timeout, bounded proxied requests, and a host-owned Keycloak bearer
flow. This change has no reason to touch that boundary. It needs only a CSS package and
strong evidence that the installed artifact is independent of the producer checkout.

## Goals / Non-Goals

**Goals:**

- Establish a small npm producer workspace following the repository's Node `22.13.0`
  baseline, with npm `10.9.2` recorded as the reproducible package-manager baseline.
- Build one real design-token tarball from current canonical sources without creating a
  second maintained token or font source tree.
- Make archive completeness and isolated consumption executable gates rather than a
  reviewer checklist.
- Add real-browser evidence for theme styles, opt-in fonts, tokens-only behavior, and
  local-only asset loading without weakening the dependency-free neutral consumer.
- Provide the same `make code-quality` and `make test` entry points as other repository
  projects and integrate them into existing pull-request change detection.

**Non-Goals:**

- Extracting React components, Material Symbols or custom icons, or any other UI package
  content. Future UI archives will be subject to the same asset validator.
- Extracting the iframe protocol or child SDK; changing protocol `"1"`, context, theme,
  locale, navigation, request proxying, authentication, or authorization.
- Publishing to a registry, creating npm credentials, selecting permanent package
  versions, or configuring trusted publishing and provenance.
- Making FRED consume a registry package, moving canonical frontend sources, or changing
  the frontend Docker build.
- Inspecting or changing RAGS. The fixture is intentionally domain-neutral.

## Decisions

### D1 — Use a private workspace root and independent package manifests

Create `libs/frontend/package.json` as a private npm workspace root with a committed
lockfile and the repository-standard quality/test commands. `private: true` protects
that orchestration root from publication; it does not propagate a publication policy to
workspace members. Build, pack, and validation scripts select the design-token package
explicitly and refuse the root as a release target.

The initial package uses the RFC's provisional `@fred/design-tokens` identity and a
non-release development version so archive behavior can be tested. Its final npm scope,
stable version, access, registry, and publisher settings remain release decisions; they
are not inferred from the workspace root.

Alternative: add npm workspaces to `apps/frontend` or the repository root. Rejected for
this slice because it would couple the application lockfile and build to package
production before the archive boundary has been proven.

### D2 — Generate package output from an explicit canonical-source allowlist

The package build reads an ordered allowlist of the existing reusable styles: color
ramps, light/dark semantic colors, state colors, light/dark shadows, spacing, radius,
motion, gradients, and typography. It emits a self-contained `tokens.css` while
preserving declarations and theme selectors. It does not consume `index.css` wholesale,
because doing so would publish its shell and document-root rules.

The optional `fonts.css` is generated from the canonical Geist `@font-face` declarations
in the existing style entry, with URLs rewritten to package-relative copies of the two
canonical Geist binaries. Use a CSS parser for extraction and URL validation rather
than a text-regex contract. Material Symbols fonts and custom icons are omitted because
no icon component is exported in this slice.

Generated output is disposable and excluded from source control. Package-specific build
instructions and license records are maintained under `libs/frontend/`; token CSS,
font-face definitions, and font binaries are not manually copied there. This temporary
producer-to-application source dependency is explicit. A later migration may move the
canonical files after FRED can consume a published package without changing the archive
contract.

Alternative: copy the current styles and fonts into the package. Rejected because two
maintained sources would drift before FRED migrates. Alternative: move the sources now.
Rejected because it would add application and Docker changes to a foundation-only slice.

### D3 — Keep public exports and packed files narrow

The package exposes only `./tokens.css` and `./fonts.css`. Its manifest uses an explicit
`exports` map and bounded `files` list, and marks CSS as side-effectful. The tarball also
contains its README, the FRED Apache license, a third-party notice inventory, and the
license texts required for the packaged Geist assets.

Before accepting an archive, validation expands the tarball and checks:

- the package identity is an individual workspace member, not the private root;
- every exported target exists and remains inside the package;
- the actual file list matches the allowed public/metadata inventory;
- every local CSS `url(...)` resolves to a packed file;
- dependency fields contain no `workspace:`, `file:`, or undeclared runtime dependency;
- text outputs contain no FRED aliases, repository-relative source references, absolute
  checkout paths, or links back to the workspace; and
- required license and notice entries are present for every packaged asset family.

The asset-license inventory is a blocking implementation audit: the implementer must
establish the source and applicable text for both Geist files rather than guessing from
the repository-level license. A missing or uncertain notice fails validation.

Alternative: validate the workspace build directory. Rejected because npm's actual pack
rules can omit required files or include unintended ones.

### D4 — Test the installed tarball outside the workspace

`npm pack --json` produces the only package input accepted by the consumer check. The
test copies that tarball and a small committed, domain-neutral fixture into a newly
created temporary directory outside the repository, clears workspace-related npm/Node
environment, installs the tarball in offline mode, and rejects linked package entries or
paths back to the checkout.

The fixture imports both public stylesheet entry points and produces a standalone output
directory using a dependency-free Node build step. Static checks verify that both theme
selectors and packaged Geist assets reach that output, which contains only fixture files
and installed-package assets. Keeping this first consumer free of React and external
build dependencies demonstrates the tokens-only contract and keeps archive installation
and build offline after producer dependencies are provisioned.

Alternative: use npm workspace links or test only FRED's Vite build. Rejected because
both can hide absent exports and assets. Alternative: require Docker for the unit test.
Rejected because staging only the tarball and fixture, combined with path/link scanning,
provides the required isolation without adding a container-runtime dependency to
`make test`.

### D5 — Add separate real-browser evidence over staged consumer output

Add a small Playwright smoke harness with lockfile-pinned `@playwright/test` and Chromium
to the package-validation workspace because the application's current Vitest
`happy-dom`/`jsdom` tooling cannot prove computed CSS, actual font loading, or browser
network behavior. Use the repository's Node baseline, a local static server, and pages
built by the isolated consumer rather than serving package sources from the checkout.

The harness opens two fresh browser contexts with caches and service workers disabled:

- a tokens-only page that switches between supported light and dark themes and asserts
  representative computed color, spacing, radius, and typography values while recording
  zero font requests; and
- an opt-in typography page that imports `fonts.css`, applies the Geist families, waits
  on the Font Loading API, and proves the regular and italic package-owned resources load
  successfully.

Request recording rejects `file:` URLs, checkout-path references, non-loopback requests,
and external font-service origins. This both detects accidental producer access and
ensures the browser result is backed only by the staged installed archive.

Dependency installation and `playwright install chromium` browser acquisition are
explicit provisioning operations and may use their normal package/browser sources. The
smoke target never installs or downloads a browser; after provisioning it runs with
network egress denied except for the loopback static server. CI represents these as
separate setup and execution steps, and local documentation does the same.

Alternative: rely on `happy-dom`, `jsdom`, or CSS text inspection. Rejected because they
cannot demonstrate browser font fetches and computed style behavior. Alternative: put a
browser bundler into the neutral fixture. Rejected because it would compromise the
fixture's dependency-free archive proof; the browser harness is producer-owned test
tooling and observes only the fixture's standalone output.

### D6 — Reuse repository quality and select every package-validation input

Provide `libs/frontend/Makefile` targets for build, type/format checks, tests, packing,
the isolated archive check, explicit browser provisioning, and the browser smoke. Add
`libs/frontend` to the root quality/test project lists. Extend the existing
`Check-pending-requests.yml` path filter with a distinct frontend-packages output and job
that runs the producer gates with the pinned Node/npm baseline.

The filter includes `libs/frontend/**`; every canonical token stylesheet in the D2
allowlist; `apps/frontend/src/styles/index.css`, from which Geist declarations are read;
the two canonical Geist binaries; the root `LICENSE`; and the root Makefile, workflow,
and any setup/action files that orchestrate this validation. A filter-contract test uses
representative changed-file sets to prove each input category selects the job and an
unrelated application-only change does not. Keeping the CSS list synchronized with the
generator allowlist is part of the test contract, so adding or removing a consumed input
without changing the filter fails validation. Do not create a publication workflow in
this change.

This keeps frontend-package validation separate from the application, Python package,
and Docker jobs while reusing the repository's existing pull-request workflow instead
of adding another orchestration surface. Application frontend checks may still run for
canonical application inputs according to their existing broad filter; the package job
is selected independently from its actual producer inputs.

### D7 — Document the shipped boundary next to its owner

Add `libs/frontend/README.md` for producer commands, canonical-source inputs, archive
acceptance, and the distinction between workspace privacy and member publication. Add a
short package README for consumer imports and link the producer documentation from the
main Swift documentation index after implementation.

The README points to the frontend packaging RFC for future packages and sequencing; it
does not reproduce the RFC. The RFC remains open because UI, SDK, publication, FRED
migration, and external-adopter work are unimplemented.

## Risks / Trade-offs

- **Canonical CSS changes can unintentionally widen the package.** → Build from a
  reviewed file allowlist, assert the absence of shell selectors, and test both themes.
- **Generated font CSS can become inconsistent with the application entry.** → Parse the
  canonical rules on every build and fail when the expected Geist faces or source files
  are absent or ambiguous.
- **The Geist asset provenance or notice obligation may not be recoverable from the
  checkout.** → Treat license identification as a blocking task; do not ship the asset
  or accept the archive until the applicable text is verified and packed.
- **A temporary build-time dependency on `apps/frontend` is less clean than final source
  ownership under `libs/frontend`.** → Keep the dependency one-way and allowlisted, emit
  no checkout paths, and defer ownership transfer until FRED can consume a released
  package without dual-maintained sources.
- **A synthetic consumer cannot prove compatibility with every bundler.** → Limit this
  slice's claim to standards-based CSS/archive independence and real-browser CSS/font
  behavior; add bundler and React matrices with the UI package rather than pulling them
  into this foundation.
- **Browser dependencies can blur the offline archive guarantee.** → Keep them in the
  producer validation workspace, provision them explicitly before execution, retain a
  dependency-free consumer, and reject every non-loopback request during the smoke run.
- **CI path filters can drift from generated inputs.** → Test representative input
  categories and compare the consumed CSS/asset allowlists with the filter contract.

## Migration Plan

1. Add the private producer workspace, reproducible toolchain metadata, and standard
   Make targets without changing `apps/frontend`.
2. Add the design-token package generator and complete the Geist license/notice audit.
3. Add archive inspection tests, negative fixtures, and the isolated neutral consumer.
4. Add the separately provisioned browser smoke harness over staged consumer output.
5. Wire all producer inputs into root and pull-request validation, then run quality,
   test, pack, isolated-consumer, and browser-smoke gates.
6. Document the implemented package boundary and record strict OpenSpec validation.

No runtime deployment or data migration occurs. Rollback removes the producer workspace
and its root/CI wiring; FRED continues using its unchanged canonical styles and host.

## Open Questions

- Which organization-controlled npm scope, registry access policy, publication owners,
  and stable/prerelease version will be used? These decisions are intentionally deferred
  until a later publication change and do not affect this archive's completeness or
  isolated-consumer requirements.

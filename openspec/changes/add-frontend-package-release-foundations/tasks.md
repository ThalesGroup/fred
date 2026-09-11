## 1. Release contract foundation (coordinate-independent)

- [x] 1.1 Record the audited hard-coded package names, development versions, UI token peer,
  consumer graph assertions, manifest metadata gaps, npm-generated producer member links,
  disposable consumer tarball references, and reusable archive/consumer helpers; verify the
  inventory covers all three packers, validators, tests, fixtures, manifests,
  `libs/frontend/package-lock.json`, offline install paths, and production-host integration
  without changing application sources.
- [x] 1.2 Add a versioned release-contract schema and parser under `libs/frontend/release/`
  for exact toolchain pins, decision status, independent coordinates, manifest metadata,
  dependencies/peers, exports, files, and intended dist-tag; verify unit tests accept a complete
  fixture contract and reject missing, extra, malformed, ranged, tagged, local, workspace, and
  contradictory values.
- [x] 1.3 Encode Node `24.21.0` and npm `11.19.0` as exact release-production pins with links
  to the official version and npm requirement sources; verify tests reject floating pins and
  that changing a pin invalidates candidate evidence.
- [x] 1.4 Add explicit proposed and test-fixture states without presenting them as approved
  release coordinates; verify candidate-evidence creation fails actionably when the selected
  contract is not maintainer-confirmed and that relabelling a fixture without replacing all
  fixture-only decisions cannot authorize it.
- [x] 1.5 Centralize selected-coordinate and expected-manifest access for all three members;
  verify tests prove callers cannot derive their expectations from a packed manifest.

## 2. Maintainer coordinate and bootstrap gate

- [ ] 2.1 Obtain and record maintainer confirmation of the organization-controlled npm scope,
  final package names, independently selected initial versions, public registry/access policy,
  and intended dist-tag; verify the confirmed contract is reviewable and does not treat the
  provisional `@fred/*`, `0.1.0-alpha.1`, or `next` values as pre-authorized.
- [ ] 2.2 Obtain and record named package/public-API, SDK wire-compatibility, release, and npm
  publishing owners plus the distinct bootstrap actor/credential identity and exact future
  Trusted Publishing source repository and GitHub workflow identity; verify unconfirmed
  identities remain explicit gates and no credential, registry mutation, or publishing workflow
  is added by this task.
- [ ] 2.3 Verify the approved npm organization/account permission model can create each package
  if it does not exist and document the separate bootstrap path; verify the record does not
  assume a package-scoped credential or staged publishing can create a brand-new package.
- [ ] 2.4 Record the maintainer choice between later direct and staged publishing, recommending
  staged review after bootstrap; verify the decision cites the exact Node/npm, existing-package,
  access, and 2FA prerequisites and remains separate from publication authorization.

## 3. Release-ready member metadata and lockfile

- [x] 3.1 Keep `libs/frontend/package.json` private and excluded from member release selection;
  verify positive and negative tests enumerate exactly the three selected members and reject a
  publishable root or accidental fourth package.
- [ ] 3.2 Synchronize the design-token, UI, and iframe SDK manifests with the confirmed independent
  coordinates and required description, license, repository directory, homepage/bugs, engines,
  files, exports, types, and side-effects metadata; verify contract comparison catches mutations
  to every required field while preserving existing public exports and packaged assets.
- [ ] 3.3 Synchronize UI's selected design-token peer and preserve the tested React and React DOM
  peer contract; verify manifest tests reject an unselected token version, bundled React runtime,
  local protocol, or undeclared runtime dependency.
- [ ] 3.4 Regenerate `libs/frontend/package-lock.json` only with the repository-pinned release
  toolchain and verify all member names, exact versions, and peer edges match the confirmed
  contract; permit npm-generated `link: true` records only for the three explicitly declared
  workspace members resolving to their contained member directories.
- [x] 3.5 Verify the root and member manifests remain distinct: root privacy neither marks members
  private nor supplies registry/publication approval, and member release metadata does not make
  the root packable.
- [x] 3.6 Add positive producer-lockfile tests for the three declared npm member links and negative
  tests for undeclared links, wrong name-to-directory mappings, absolute or escaping targets, and
  symlink escapes; verify every packed member manifest still rejects `workspace:`, `file:`,
  `link:`, directory, checkout-source, and other local dependency references.

## 4. Candidate packing, archive validation, and immutable evidence

- [x] 4.1 Parameterize all three pack scripts with the explicit selected contract and remove
  hard-coded development coordinate assumptions; verify each packer selects only its expected
  member and rejects npm output for a different name or version.
- [x] 4.2 Extend the token, UI, and SDK archive validators to compare actual packed metadata,
  dependencies, exports, files, assets, licenses/notices, and executable/declaration references
  against the selected release contract before running every existing package-specific gate;
  verify positive candidate fixtures and targeted negative metadata mutations.
- [x] 4.3 Preserve all existing token import/structure/license, UI CSS scope/asset/React
  externalization, and SDK runtime/declaration/protocol negative tests; verify their complete
  current suites pass unchanged with selected candidate coordinates.
- [x] 4.4 Implement a clean-checkout release-candidate command that checks exact Node/npm versions,
  builds and packs each member once, and reuses those same tarballs for validation; verify dirty
  source state, wrong toolchain, unconfirmed coordinates, incomplete archives, or a failed gate
  stops before approved evidence is written.
- [x] 4.5 Generate one schema-versioned candidate evidence record containing the clean source
  commit, UTC time, selected contract, exact producer and application-test Node/npm toolchains,
  package
  coordinates, archive filenames, byte lengths, independently computed SRI SHA-512 values, and
  explicit expected provenance repository, commit, authorized Trusted Publishing workflow
  identity, and artifact digest; verify the record covers all three archives and all required
  gates without deriving expectations from a downloaded attestation.
- [x] 4.6 Add integrity and immutability regression tests that truncate, modify, replace, or rebuild
  a recorded archive; verify prior evidence is rejected and cannot authorize later use of changed
  bytes.
- [ ] 4.7 Retain the three exact tarballs and evidence as one commit-addressed disposable/CI
  candidate artifact; verify a retrieval check recomputes every SHA-512 before declaring the set
  usable and that expiration requires a fresh candidate run.

## 5. Candidate-aware isolated and compatibility consumers

- [x] 5.1 Parameterize the neutral token, isolated React, and neutral iframe SDK consumer
  orchestration with selected exact coordinates while reusing their existing fixtures; verify
  generated disposable manifests/imports and dependency-graph assertions contain no
  `0.0.0-development`, workspace link, directory dependency, unverified local file, or FRED
  source path while permitting only integrity-verified candidate-tarball references.
- [x] 5.2 Update lockfile-pinned provisioning for the selected candidate graphs; verify it may
  contact package sources only during provisioning and fails actionably when an exact dependency
  or browser prerequisite cannot be prepared.
- [x] 5.3 Install the actual token, UI, and SDK candidate tarballs from prepared caches into fresh
  locations outside FRED with networking disabled; permit npm's generated `file:` references to
  those copied `.tgz` files only after resolving them as contained regular files and matching
  candidate SHA-512, and verify type checks and production builds pass without the FRED checkout
  or producer/application `node_modules`.
- [x] 5.4 Run the existing browser harness against the candidate token/UI archives and verify both
  themes, optional Geist, Material Symbols, component behavior, local-only successful assets,
  and no dependency installation or browser bootstrap during smoke execution.
- [x] 5.5 Run the packed candidate SDK against the cross-origin browser and FRED production-host
  compatibility harnesses; verify protocol `"1"`, legacy behavior, origin/window admission,
  request lifecycle, host authority, and iframe/proxy/authentication regressions remain green;
  verify the host/test runner uses `apps/frontend` dependencies while the SDK entry comes only
  from the integrity-verified archive.
- [x] 5.6 Add positive tests for npm-generated disposable manifest/lockfile `file:` references to
  the exact staged candidate tarballs and negative tests for directory targets, a different or
  modified tarball, symlinks, workspace links, checkout paths, and reused FRED dependency trees;
  verify only the evidence-matched archive references pass.

## 6. Exact public-registry verifier (no publication)

- [x] 6.1 Add a registry-verification command requiring the approved public registry, candidate
  evidence, and three exact name-at-version coordinates; verify it rejects tags, ranges, missing
  packages, unexpected registries, local tarballs, file/workspace specs, and omitted integrity.
- [x] 6.2 Resolve and download each exact registry package in a fresh temporary area, compare
  registry metadata and downloaded bytes with recorded SHA-512, cryptographically verify
  provenance against the explicit expected certificate URI and issuer, then compare its artifact
  digest, source repository, source commit, and publishing
  workflow identity with expectations already bound to the release contract and candidate
  evidence; verify signature validity and intended-release identity are reported as separate
  gates.
- [x] 6.3 Build clean registry-only versions of the token, React UI, and iframe SDK consumers from
  the downloaded exact versions; verify tests fail rather than falling back to candidate tarballs,
  workspace sources, FRED dependencies, or mutable dist-tags.
- [x] 6.4 Label controlled/local verifier results as `registry-verifier-tooling` and reserve
  `public-registry-verification` for a real run against genuinely published exact packages;
  verify local success cannot produce or imitate the public-registry evidence type.
- [x] 6.5 Document the exact future post-publication invocation and expected evidence without
  executing it; verify the runbook states that successful genuine registry verification remains
  unavailable until separately authorized publication occurs.
- [x] 6.6 Add negative provenance fixtures that remain cryptographically valid while independently
  changing the source repository, source commit, authorized workflow identity, or attested
  artifact digest; verify each fails the expected-identity comparison and that missing/unconfirmed
  expected identities and mismatched certificate policies fail closed rather than being copied
  from the attestation.

## 7. Toolchain-aware CI and selection

- [x] 7.1 Add Makefile/npm entry points for contract checks, candidate generation, evidence
  verification, and registry-verifier tooling tests; verify none authenticates, changes registry
  settings, publishes, or invokes the genuine public-registry verification by default.
- [x] 7.2 Add a release-readiness CI path using exactly Node `24.21.0` and npm `11.19.0` for
  producer candidate work; verify the command fails on version drift and retains all existing
  producer quality, unit, archive, and negative gates.
- [ ] 7.3 Keep FRED application and production-host tests under their separately controlled
  application toolchain and pass only hash-verified candidate archives/evidence between jobs;
  verify the host and its runner use the application's own dependencies, the SDK under test comes
  from the verified archive or exact registry installation, and neither environment resolves the
  other's installed dependency tree.
- [x] 7.4 Extend `scripts/package-inputs.mjs`, workflow path filters, and CI-selection tests for
  every release contract, member manifest/lockfile, toolchain pin, evidence schema/helper,
  registry-verifier fixture, runbook, and orchestration input; verify relevant changes select
  release readiness plus existing archive regressions while unrelated application files may skip
  the package jobs.
- [x] 7.5 Verify existing canonical CSS/component/protocol/host, asset, license, React baseline,
  consumer, browser, and orchestration inputs retain their prior package and application-job
  selection behavior.

## 8. Release documentation and RFC alignment

- [x] 8.1 Add a compact `libs/frontend/` release runbook covering decision gates, exact toolchains,
  candidate creation, evidence retention, bootstrap, later Trusted Publishing configuration,
  optional staging, dependency-first publication, genuine registry verification, recovery, and
  rollback; document the distinct producer-workspace, candidate-tarball, published-manifest, and
  registry-consumer dependency boundaries plus separate bootstrap and Trusted Publishing
  identities, and verify every command is clearly classified as implemented repository readiness,
  future maintainer action, or separately authorized publication.
- [x] 8.2 Update the existing package producer/member documentation for selected coordinates,
  candidate validation, immutable archives, and verifier-tooling limitations; verify the package
  READMEs remain the source for shipped behavior and examples remain application-agnostic.
- [x] 8.3 Correct only the sequencing/status text in
  `docs/swift/FRED-FRONTEND-PACKAGING-RFC.md` to split readiness, publication plus genuine registry
  verification, and later FRED adoption; verify theme/live-locale, SDK ownership transfer,
  publication, stable release, FRED/RAGS adoption, and broader catalog work remain open.
- [x] 8.4 Document dependency order and immutable recovery: design tokens before UI, SDK
  independently, no FRED adoption before verified prereleases, a changed SDK artifact released
  before protocol-ownership adoption, and rollback through prior versions/lockfiles/images rather
  than overwritten package bytes.

## 9. Completion evidence and review

- [ ] 9.1 Run the producer formatting/lint, unit, contract, candidate archive, and complete existing
  positive/negative package suites with the exact release toolchain; record exact commands,
  versions, archive names, SHA-512 values, and results.
- [ ] 9.2 Provision dependencies and browsers separately, then run offline isolated token/UI/SDK
  consumers and browser smoke against the exact candidate bytes; record commands and prove no
  network, workspace, source-checkout, or missing-prerequisite fallback.
- [x] 9.3 Run the FRED application quality, production build, affected component tests,
  production-host SDK integration, iframe/proxy/authentication, and CI-selection regression gates
  under the separately controlled application tooling; record exact commands and results.
- [x] 9.4 Run registry-verifier controlled positive/negative tests and confirm no genuine
  public-registry success is claimed before publication; include signature-invalid and
  validly-signed wrong-repository/commit/workflow/digest cases and record the distinction in
  completion evidence.
- [x] 9.5 Run `openspec validate add-frontend-package-release-foundations --strict`, applicable
  repository-wide OpenSpec validation, and `git diff --check`; verify all pass and all change
  artifacts remain consistent with the implementation.
- [x] 9.6 Obtain the repository-required independent implementation review of metadata contracts,
  boundary-aware workspace/tarball references, archive immutability, provenance signature and
  expected-identity binding, offline/registry isolation, toolchain separation, security failure
  modes, and documentation; resolve every in-scope finding and record any genuinely external
  maintainer gate without weakening acceptance criteria.

## 10. Confirmed release-validation corrections

- [x] 10.1 Correct the real npm registry adapter to consume raw `dist.attestations.url`
  metadata, validate and re-root only the allowed exact-coordinate endpoint onto the approved
  registry, and continue through npm signature audit, Sigstore verification, and independent
  digest/repository/commit/workflow comparison; verify controlled adapter-level tests accept the
  representative npm shape and reject missing, malformed, disallowed, and coordinate-mismatched
  URLs without mocking an already normalized registry result.
- [x] 10.2 Replace basename-only offline lock acceptance with complete package-identity,
  manifest/lock consistency, contained realpath, non-symlink regular-file, archive-integrity,
  lock-integrity, version, and root/nested dependency-field validation; verify same-basename
  escapes, npm-decoded traversal/separator ambiguity, query/fragment forms, additional different
  bytes, directory and symlink targets, unmatched nested/local dependencies, and mismatched
  integrity fail before `npm ci`, while approved candidate tarballs and private producer workspace
  links retain their separate valid boundaries.
- [x] 10.3 Require every offline candidate declaration and resolution to use exactly
  `file:<approved-record-filename>`; reproduce and reject npm-normalized tilde and actual-tab
  spellings plus other noncanonical forms before dependency installation; classify and reject
  case-insensitive, leading-whitespace `git+file:` checkout dependencies across offline and
  published/archive boundaries; retain exact generated consumer references and all containment,
  realpath, file-type, identity, version, and archive-integrity checks.
- [x] 10.4 Separate declaration validation from package-resolution validation and require every
  direct or nested local package-resolution entry to contain valid SRI SHA-512 integrity exactly
  matching candidate evidence; verify missing, null, empty, malformed, and mismatched values fail
  before dependency installation while declarations without integrity remain valid.

## Coordinate-independent phase evidence (2026-09-11)

- Tracking: [ThalesGroup/fred#2630](https://github.com/ThalesGroup/fred/issues/2630).
- `npm run release:check`, `npm run release:test` (31 tests), and the complete producer suite
  (225 tests) validate the
  explicit fixture/proposed states, exact release pins, all four dependency boundaries,
  same-byte candidate handling, controlled cryptographic/provenance failures, and strict
  separation between tooling and public-registry evidence.
- `npm run pack:check`, `npm run test:consumer`, `npm run test:host-integration`, and
  `npm run test:browser` pass with the development fixture contract. These are fixture/archive
  regression results, not approved candidate or genuine registry evidence.
- `npm --prefix apps/frontend run lint`, `format`, `build`, and `test` pass under the existing
  application-owned toolchain; no application source or dependency was changed.
- Independent review identified and verified corrections for Sigstore workflow-certificate
  policy binding, fixture-to-approved promotion prevention, exact application Node/npm evidence,
  genuine registry browser/host execution, and public-evidence labelling. Final re-review found
  no remaining in-scope correctness or security issue.
- Follow-up review corrections reproduce the npm endpoint bug against raw
  `dist.attestations.url` metadata and the same-basename offline-lock bypass before their fixes.
  Focused tests then verify npm/pacote-compatible registry re-rooting plus attestation URL
  failures, and complete local-reference identity/realpath/bytes/integrity validation before
  offline dependency installation.
- Independent follow-up review reproduced a percent-encoded `file:` traversal that npm resolves
  differently from a literal filesystem path. The narrow offline archive contract now rejects
  percent encoding, query strings, fragments, and backslashes, with encoded traversal and
  separator regressions proving validation cannot authorize different installer bytes.
- Tasks 2.1-2.4, 3.2-3.4, 4.7, 7.3, 9.1, and 9.2 remain gated on maintainer-confirmed scope,
  coordinates, owners, bootstrap authority, registry policy, and publishing workflow identity.
  No provisional contract may satisfy them.

## Confirmed-correction evidence (2026-09-11)

- The focused regression commands initially failed four cases: raw npm-shaped metadata reported
  the attestation URL missing, while same-basename escaping and directory local lock entries did
  not reject, and npm-decoded traversal was accepted. After correction it passes 18/18 tests,
  including the npm adapter, provenance
  continuation, URL failure modes, local-reference identity/realpath/bytes/version/integrity,
  root/nested fields, and validation-before-install ordering.
- `npm run release:check`, `npm run release:test` (38 tests), `npm run lint`, `npm run format`,
  and `npm test` (232 tests) pass with Node `22.13.0` and npm `10.9.2`.
- `npm run pack:check` validates the actual development token, UI, and iframe SDK archives;
  separately provisioned caches then support `npm run test:consumer` entirely offline.
  `npm run test:host-integration` and the pre-provisioned `npm run test:browser` pass, with the
  browser evidence reporting zero dependency installations, browser provisioning, or external
  requests during smoke execution.
- These remain fixture/development results. Node `24.21.0` and npm `11.19.0` are not installed in
  this checkout, and no confirmed coordinates or authorized identities exist, so tasks 9.1 and
  9.2 remain correctly unchecked rather than being satisfied by development evidence.

## Final offline-validation correction evidence (2026-09-11)

- Before correction, the focused boundary suite passed 9/14 tests and failed five: literal-path
  validation accepted tilde, actual-tab, and dot-segment references that npm normalizes
  differently; a direct package resolution without integrity was accepted; and the invalid-
  integrity regression observed the old undifferentiated lock-integrity error. The corrected
  focused boundary suite passes 14/14 and exercises direct and nested missing integrity,
  null/empty/malformed/mismatched values, declarations without integrity, and callback ordering.
- Independent review then reproduced acceptance of a `git+file:` checkout dependency. The shared
  local-reference classifier now rejects plain, mixed-case, and leading-whitespace local Git
  references across offline graphs, published manifests, and token/UI/SDK archive validation.
  Final independent re-review found no remaining correctness or security issue.
- With Node `22.13.0` and npm `10.9.2`, `npm run release:check`, `npm run release:test` (45 tests),
  `npm run lint`, `npm run format`, and `npm test` (241 tests) pass. `npm run pack:check` validates
  all three development archives, and separately provisioned caches support the offline token,
  UI, and SDK consumers. Production-host integration passes 4/4 tests; pre-provisioned browser
  smoke records zero dependency installations, browser provisioning, and external requests.
- These are fixture/development results, not exact-release-toolchain candidate or genuine public-
  registry evidence. Tasks 2.1-2.4, 3.2-3.4, 4.7, 7.3, 9.1, and 9.2 remain gated and unchecked.

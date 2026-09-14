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

- [x] 2.1 Obtain and record maintainer confirmation of the organization-controlled npm scope,
  final package names, independently selected initial versions, public registry/access policy,
  and intended dist-tag; verify the confirmed contract is reviewable and does not treat the
  formerly provisional coordinates or policy as pre-authorized.
- [ ] 2.2 Obtain and record named package/public-API, SDK wire-compatibility, release, and npm
  publishing owners plus the distinct bootstrap actor/credential identity and exact future
  Trusted Publishing source repository and GitHub workflow identity; verify unconfirmed
  identities remain explicit gates and the guarded workflow cannot receive a credential or mutate
  the registry during its default preparation path.
- [x] 2.3 Verify the approved npm organization/account permission model can create each package
  if it does not exist and document the separate bootstrap path; verify the record does not
  assume a package-scoped credential or staged publishing can create a brand-new package.
- [ ] 2.4 Record the maintainer choice between later direct and staged publishing, recommending
  staged review after bootstrap; verify the decision cites the exact Node/npm, existing-package,
  access, and 2FA prerequisites and remains separate from publication authorization.

## 3. Release-ready member metadata and lockfile

- [x] 3.1 Keep `libs/frontend/package.json` private and excluded from member release selection;
  verify positive and negative tests enumerate exactly the three selected members and reject a
  publishable root or accidental fourth package.
- [x] 3.2 Synchronize the design-token, UI, and iframe SDK manifests with the confirmed independent
  coordinates and required description, license, repository directory, homepage/bugs, engines,
  files, exports, types, and side-effects metadata; verify contract comparison catches mutations
  to every required field while preserving existing public exports and packaged assets.
- [x] 3.3 Synchronize UI's selected design-token peer and preserve the tested React and React DOM
  peer contract; verify manifest tests reject an unselected token version, bundled React runtime,
  local protocol, or undeclared runtime dependency.
- [x] 3.4 Regenerate `libs/frontend/package-lock.json` only with the repository-pinned release
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
  source state, wrong toolchain, incomplete maintainer decisions, incomplete archives, or a failed gate
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
- [x] 10.5 Make the release-readiness CI job provision its own isolated-consumer cache in a
  distinct network-capable step after producer dependency installation and before
  consumer-dependent tests; add a workflow-contract regression that proves the exact command,
  working directory, and ordering while preserving offline validation.

## 11. Fixture archive transfer across release and application toolchains

- [x] 11.1 Add strict fixture-transfer creation and verification helpers that bind the development
  fixture contract, checked-out source commit, observed producer Node/npm versions, exact
  three-package coordinates/files/lengths/SHA-512 values, and repository/workflow/run/attempt
  identity; reject malformed metadata and any missing, additional, substituted, non-regular, or
  modified transfer file before a consumer callback can run.
- [x] 11.2 Generate one designated transfer set from exactly one validated pack per role under the
  release toolchain; keep intermediate metadata explicitly limited to producer archive validation,
  copy no credentials/dependency trees/caches/checkout content, and distinguish this set from
  disposable archives produced by regression tests.
- [x] 11.3 Add a receiver orchestrator that verifies the downloaded transfer against the receiver's
  independently selected commit, fixture-contract digest, and same workflow run/attempt, then
  supplies only explicit archive paths and integrities to the existing isolated token, React UI,
  iframe SDK, browser, and production-host helpers without repacking or `target/archives` fallback.
- [x] 11.4 Write final `fixture-candidate-evidence` only after every receiver gate succeeds, binding
  the transfer metadata digest/artifact identity, exact archive records, independently observed
  application Node/npm versions, and downstream results; prove failure leaves no success record
  and neither fixture evidence kind can enter approved/public evidence paths.
- [x] 11.5 Wire the release-readiness and application-toolchain package jobs as a same-run
  producer/receiver chain with exact artifact naming, seven-day retention, explicit upload and
  download failure behavior, separate dependency/browser provisioning, and final evidence
  retention; transfer neither caches nor installed dependencies.
- [x] 11.6 Extend release, transfer, evidence, CI-selection, and negative regression tests for exact
  byte reuse, file/identity/integrity/run mismatches, callback ordering, no local fallback, no
  evidence on gate failure, fixture non-promotion, job dependencies, artifact selection,
  provisioning order, and relevant versus unrelated input selection.
- [x] 11.7 Add Makefile/npm entry points and release-runbook instructions for fixture transfer,
  retrieval, local producer/receiver rehearsal, retention, evidence relationships, failure
  recovery, and the remaining manual verification of GitHub upload/download after push.
- [x] 11.8 Run the complete producer, archive, isolated-consumer, browser, host, application where
  affected, strict OpenSpec, and diff checks; perform a separate-directory local transfer rehearsal
  with actual tarballs and obtain independent review. Keep tasks 4.7, 7.3, 9.1, and 9.2 plus all
  other maintainer-gated work unchecked because fixture evidence cannot satisfy them.

## 12. First `@fred-oss` release preparation

- [x] 12.1 Record the selected npm organization, three exact prerelease coordinates, public
  registry/access, `next` tag, bootstrap account and supplied organization-owner confirmation in
  the proposed contract; keep package API, SDK protocol, release, enduring publishing ownership,
  and later direct-versus-staged policy unresolved and fail approved evidence while they are
  incomplete.
- [x] 12.2 Synchronize member manifests, the UI token peer, generic consumer imports, package
  documentation, and the producer lockfile to the selected `@fred-oss/*@0.1.0-alpha.1`
  coordinates under exact Node `24.21.0` and npm `11.19.0`; preserve root privacy, React peers,
  canonical sources, public exports, assets, licenses, and fixture-only evidence classification.
- [x] 12.3 Extend the immutable transfer boundary for approved candidates and add controlled
  bootstrap-publication tests that require a complete contract, exact same-run bytes/evidence,
  repository/commit/ref/workflow/bootstrap identity, all-version absence preflight, provenance,
  expected-repository source-dependency selection, dependency-safe order, per-package integrity
  checks, and explicit reconciliation of ambiguous or partial publication failures.
- [x] 12.4 Add a manual-only, `swift`-restricted workflow that defaults to preparation, separates
  release and application toolchains, uses `npm-publish` and `NPM_BOOTSTRAP_TOKEN` only for the
  explicitly selected publishing step, reverifies without rebuilding, and runs genuine
  secret-free registry verification only after publication; verify its contract and CI selection.
- [x] 12.5 Document exact GitHub environment/secret setup, first-package bootstrap, subsequent
  Trusted Publishing setup, token revocation, immutable recovery, and the distinction between
  controlled tests, approved candidates, actual publication, and genuine registry evidence;
  retain broader RFC release/adoption work as open.
- [ ] 12.6 On committed `swift` after named owners and later policy are confirmed, run the guarded
  preparation path and retain one approved release-candidate artifact with GitHub repository,
  commit, workflow/run, dual-toolchain, archive, and complete downstream evidence.
- [ ] 12.7 After separate publication authorization and protected-environment approval, bootstrap
  the three previously absent versions from those exact bytes, verify emitted provenance and
  public registry integrity/consumers, then configure each existing package's Trusted Publisher
  and revoke the temporary token without overwriting or rebuilding any version.

## 13. Release-verification hardening

- [x] 13.1 Reproduce npm's lockfile-only installed-tree failure with the application Node/npm
  toolchain, then require exact contract/evidence/registry/archive checks and registry-lock graph
  validation before `npm ci --ignore-scripts`; prove the exact non-linked installed package tree
  exists before mandatory npm signature and Sigstore verification.
- [x] 13.2 Add positive and negative registry-verifier regressions using actual npm CLI
  installed-tree behavior, including lock-only versus installed roots, pre-install candidate
  integrity rejection, pre-install local-fallback rejection, and transitive FRED graph integrity.
- [x] 13.3 Give the post-publication registry-verification job one explicit
  `PLAYWRIGHT_BROWSERS_PATH` for provisioning and validation; add workflow and prerequisite
  regressions proving the verifier rejects missing or differently resolved Chromium without
  downloading a browser.
- [x] 13.4 Update the release runbook and active OpenSpec artifacts, run the focused and complete
  release/package/application gates under their prescribed toolchains, run strict OpenSpec and
  diff validation, and obtain independent review without producing public-registry evidence.

## Fixture archive-transfer evidence (2026-09-11)

- Work started from merge commit `a1b29c45403af496f1a6421e29ae131b802c90d1` on
  `feat/frontend-package-release-candidates` and continues to track
  [ThalesGroup/fred#2630](https://github.com/ThalesGroup/fred/issues/2630). The proposed contract
  remains `proposed`; the transfer uses the development fixture contract and produces no
  publication or public-registry evidence.
- Separate network-capable provisioning used `make consumer-provision`; the pre-provisioned
  repository Chromium at `target/playwright` was selected explicitly during offline validation.
  The first sandboxed provisioning attempt could not resolve the npm registry and was rerun with
  authorized network access; validation itself retained no network fallback.
- Under exact producer Node `24.21.0` and npm `11.19.0`, `npm run release:check` passes,
  `npm run release:test` passes 65/65 controlled tests, `npm run lint` and `npm run format` pass,
  the complete `npm test` producer suite passes 263/263 tests, and `npm run pack:check` validates
  all three development archives and existing negative guarantees.
- A separate-directory rehearsal created the transfer under `/private/tmp` with the exact release
  toolchain, copied only `fixture-transfer.json` plus the three tarballs to a receiver directory,
  and validated it under independently observed application Node `22.13.0` and npm `10.9.2`.
  The checkout was truthfully recorded as dirty because this review leaves changes uncommitted.
  The receiver passed the offline token, React UI, and iframe SDK consumers, local-only browser
  smoke, and the production-host integration (4/4 tests), then wrote only
  `fixture-candidate-evidence` with the transfer metadata digest and downstream results.
- The designated archive records were
  `fred-design-tokens-0.0.0-development.tgz`
  (`sha512-Ah/MK0RQHpAEnW/wZR69mHRQId+W5w4aBKPZCfZvG/42LHXGPwO80K87Asu77tuZNbe108cT0g8fQKLpSrIr7w==`),
  `fred-ui-0.0.0-development.tgz`
  (`sha512-Zv1I+XQx9Ndukm0/0JAZT2ypqFQiwn+ZHxRq9y9F1yAoD7GCyGauvlgLbchbe1ETu1FD2Ozn+Z0lV8GQQpdvAQ==`),
  and `fred-iframe-sdk-0.0.0-development.tgz`
  (`sha512-PS6OmcYwcklAprkCtNiHdZLrVAU+L+LCZe3yfXDrwiLf/5pA/tdYA99GSaM0gUIB6k9jS+Ux+YWP3RVHdCjddg==`).
- Existing development commands `make isolated-consumer`, `make host-integration`, and
  `make browser-smoke` also pass; browser evidence records zero dependency installations,
  browser provisioning, or external requests during execution. Changed inputs require no broader
  application suite beyond the packed-SDK production-host gate and workflow/selection regressions.
- Independent review reproduced and resolved two issues: downstream mutation could initially be
  re-baselined into final evidence, and output cleanup did not initially protect broad paths.
  Post-gate byte/metadata verification plus exact final-record comparison now prevent mutation,
  while canonical, location-independent output guards reject filesystem, home, repository,
  workspace, producer-target, and symlink roots before deletion. Focused final transfer and CI
  tests pass 34/34; final re-review found no remaining in-scope issue.
- Local checks cannot prove GitHub's remote artifact service upload/download behavior. After the
  manual push, reviewers must confirm the exact same-run artifact name, seven-day retention,
  download, and final-evidence upload. This remote check cannot upgrade fixture evidence or
  complete maintainer-gated tasks 4.7, 7.3, 9.1, or 9.2.
- Tasks 2.1-2.4, 3.2-3.4, 4.7, 7.3, 9.1, and 9.2 remain unchecked: they still require confirmed
  package coordinates, owners, bootstrap authority, registry/release policy, workflow identity,
  and later approved-candidate execution.

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

## Release-readiness consumer-provisioning correction evidence (2026-09-11)

- GitHub Actions run `34612396682`, job `103305995127`, installed Node `24.21.0` and npm
  `11.19.0`, installed producer dependencies, passed release-contract validation and all 45
  controlled release-tooling tests, then failed the 241-test producer suite at 240/241 because
  `target/iframe-sdk-consumer-cache` was absent.
- The workflow-contract regression failed before correction because the release-readiness job had
  no `make consumer-provision` step. It now verifies that the exact command runs from
  `libs/frontend` after producer installation and before `make code-quality test pack-check`.
- Separate `make consumer-provision` succeeds, followed by the release checks, the complete
  producer/archive suite, offline isolated consumers, production-host integration, and
  pre-provisioned browser smoke. Browser evidence reports zero dependency installations, browser
  provisioning, or external requests during smoke execution.
- The original maintainer-gated tasks 2.1-2.4, 3.2-3.4, 4.7, 7.3, 9.1, and 9.2 remain unchecked;
  this CI prerequisite correction does not produce approved candidate or public-registry evidence.

## First `@fred-oss` release-preparation evidence (2026-09-14)

- Work started clean at `1cffc1e002242211430d853c0b4a3b068139dbbd` on
  `feat/frontend-package-first-release`. Maintainers selected npm organization `fred-oss`, all
  three `@fred-oss/*@0.1.0-alpha.1` coordinates, public npm access, `next`, bootstrap account
  `marc.fawaz`, and supplied authenticated organization-owner confirmation. No token value was
  requested, read, printed, or stored. Named product/release/enduring-publisher owners and later
  direct-versus-staged policy remain incomplete, so the contract remains `proposed`.
- The producer lockfile was regenerated with exact Node `24.21.0` and npm `11.19.0` using
  `npm install --package-lock-only --ignore-scripts --no-audit --no-fund`. Under that toolchain,
  `npm run release:check`, `npm run release:test` (77/77), `make code-quality`, `npm test`
  (279/279 producer tests), and `make pack-check` for all three archive validators pass.
- The final exact-toolchain run reproduced npm `11.19.0` rejecting the older
  `npm exec -- tsc` build invocation. UI and SDK generation now invoke the lockfile-installed
  TypeScript compiler through the active Node executable, with no install or network fallback;
  the exact Node `24.21.0` / npm `11.19.0` 279-test suite then passed.
- The selected-coordinate archive regression bytes are
  `fred-oss-design-tokens-0.1.0-alpha.1.tgz`
  (`sha512-+3UeYRe4Qhgtx+U1T/QQqu9172N+7c+DbuSo8G/2mvp5nbrjgLJj1VDdcOv4AYsuaYEvpNzERHo7Z6GTFNenqw==`),
  `fred-oss-ui-0.1.0-alpha.1.tgz`
  (`sha512-+BmE1ASoIDN8HYDugYCd8gzykHcspH7LxQuM5m4HjQWMoVErR99L1OU+bcp2ICN1AkvUoOwfNbtpU9eFp5ln8A==`),
  and `fred-oss-iframe-sdk-0.1.0-alpha.1.tgz`
  (`sha512-FG0y07SN6I+iNzKxJGMC1RYeJeGHCitbRBob7jr7iGMW5AcMt1pfoIJm//UK/cMq0E1QC2sE+hWpF2VsPwsz6w==`).
  They are disposable archive-regression output from a dirty planning checkout, not approved
  candidate evidence and not eligible for publication.
- Network-capable `make consumer-provision` and `make browser-install` ran separately. Exact
  release-toolchain `make isolated-consumer` passed for token, UI, and SDK archives in fresh
  consumers with npm offline mode. `make browser-smoke` passed with pre-provisioned Chromium,
  zero dependency installations, zero browser provisioning, zero external requests, local 200
  responses, both themes, optional Geist, Material Symbols, reset behavior, and cross-origin SDK
  checks. The sandboxed browser attempt failed only because loopback binding was denied and the
  same local-only command passed with authorized host execution.
- Under application Node `22.13.0` and npm `10.9.2`, `make host-integration` passes 4/4 packed-SDK
  production-host tests. `make code-quality build test` in `apps/frontend` passes its type,
  format, lint, production build, proxy smoke, and 2198/2198 executed tests (six additional tests
  skipped by the existing suite). npm reports existing dependency engine warnings for packages
  requiring newer Node 22 patch releases; the application command still passes and application
  tooling remains separately controlled.
- The guarded workflow and controlled helper tests prove default no-publish behavior, secret
  isolation, exact identity/byte verification, all-version absence preflight, design-token-before-
  UI ordering, per-package integrity, expected-repository commit selection, and registry
  reconciliation after ambiguous publish failures. Verified `fred-oss` ownership is bound to all
  selected package namespaces, and RFC edits now select release-readiness CI. Independent final
  review found no remaining correctness, security, or scope finding. These checks do not prove a
  GitHub environment approval, provenance emission, npm package creation, or public-registry
  verification. Tasks 4.7, 7.3, 9.1, 9.2, 12.6, and 12.7 remain unchecked pending committed
  source, the remaining maintainer decisions, a real workflow run, and separate publication
  authorization.

## Release-verification hardening evidence (2026-09-14)

- With application Node `22.13.0` and npm `10.9.2`, a disposable exact-registry dependency with
  only `package-lock.json` reproduced `npm ls`'s missing dependency and `npm audit signatures`
  failed with `found no dependencies to audit that were installed from a supported registry`.
  After `npm ci --ignore-scripts`, `npm ls` resolved the exact registry URL and the same audit
  reported one verified registry signature. The original workflow parse also showed no
  `PLAYWRIGHT_BROWSERS_PATH` for the public-registry job.
- The resolver now validates the contract-bound registry, coordinate, downloaded archive SHA-512,
  and complete FRED lock graph before `npm ci --ignore-scripts --no-audit --no-fund`. Before the
  mandatory npm signature audit and unchanged Sigstore/identity checks, it uses actual `npm ls`
  behavior plus link, real-path, and installed-manifest checks to prove the package is installed
  inside the disposable root. Negative tests reject candidate-integrity and local-lock fallback
  before installation plus transitive FRED graph drift.
- The public-registry job now shares `PLAYWRIGHT_BROWSERS_PATH=target/playwright` across its
  separate provisioning and verification steps. The verifier rejects a missing directory,
  missing executable, differently resolved path, or escaping symlink before registry lookup and
  contains no browser installation path. The actual pre-provisioned Chromium executable resolves
  inside that directory.
- Under exact producer Node `24.21.0` and npm `11.19.0`, the focused resolver/boundary/browser/
  workflow suite passes 54/54, `npm run release:check`, `npm run release:test` (81/81), `npm run
  lint`, `npm run format`, the complete producer suite (285/285), and all three archive checks
  pass. Separately provisioned consumer caches then support all three offline isolated consumers;
  separately provisioned Chromium supports browser smoke with zero dependency installations,
  browser provisioning, or external requests during execution.
- Under application Node `22.13.0` and npm `10.9.2`, production-host integration passes 4/4,
  application quality and production build pass, and the frontend suite executes 2198/2198 tests
  successfully with six existing skips. The existing dependency engine warnings for newer Node
  22 patch releases remain unchanged.
- Strict OpenSpec validation and `git diff --check` pass. Independent review found no correctness,
  security, scope, test, or documentation finding. These controlled and local checks are not a
  genuine public-registry verification; tasks 2.2, 2.4, 4.7, 7.3, 9.1, 9.2, 12.6, and 12.7
  remain gated on the remaining maintainer decisions, committed source, a real GitHub run,
  publication, and separately authorized registry verification.

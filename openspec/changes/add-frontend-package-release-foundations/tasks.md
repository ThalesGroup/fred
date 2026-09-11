## 1. Release contract foundation (coordinate-independent)

- [ ] 1.1 Record the audited hard-coded package names, development versions, UI token peer,
  consumer graph assertions, manifest metadata gaps, and reusable archive/consumer helpers;
  verify the inventory covers all three packers, validators, tests, fixtures, manifests, and
  `libs/frontend/package-lock.json` without changing application sources.
- [ ] 1.2 Add a versioned release-contract schema and parser under `libs/frontend/release/`
  for exact toolchain pins, decision status, independent coordinates, manifest metadata,
  dependencies/peers, exports, files, and intended dist-tag; verify unit tests accept a complete
  fixture contract and reject missing, extra, malformed, ranged, tagged, local, workspace, and
  contradictory values.
- [ ] 1.3 Encode Node `24.21.0` and npm `11.19.0` as exact release-production pins with links
  to the official version and npm requirement sources; verify tests reject floating pins and
  that changing a pin invalidates candidate evidence.
- [ ] 1.4 Add explicit proposed and test-fixture states without presenting them as approved
  release coordinates; verify candidate-evidence creation fails actionably when the selected
  contract is not maintainer-confirmed.
- [ ] 1.5 Centralize selected-coordinate and expected-manifest access for all three members;
  verify tests prove callers cannot derive their expectations from a packed manifest.

## 2. Maintainer coordinate and bootstrap gate

- [ ] 2.1 Obtain and record maintainer confirmation of the organization-controlled npm scope,
  final package names, independently selected initial versions, public registry/access policy,
  and intended dist-tag; verify the confirmed contract is reviewable and does not treat the
  provisional `@fred/*`, `0.1.0-alpha.1`, or `next` values as pre-authorized.
- [ ] 2.2 Obtain and record named package/public-API, SDK wire-compatibility, release, and npm
  publishing owners plus the exact future GitHub workflow identity; verify no credential,
  registry mutation, or publishing workflow is added by this task.
- [ ] 2.3 Verify the approved npm organization/account permission model can create each package
  if it does not exist and document the separate bootstrap path; verify the record does not
  assume a package-scoped credential or staged publishing can create a brand-new package.
- [ ] 2.4 Record the maintainer choice between later direct and staged publishing, recommending
  staged review after bootstrap; verify the decision cites the exact Node/npm, existing-package,
  access, and 2FA prerequisites and remains separate from publication authorization.

## 3. Release-ready member metadata and lockfile

- [ ] 3.1 Keep `libs/frontend/package.json` private and excluded from member release selection;
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
  contract with no `workspace:`, `file:`, or link release dependency.
- [ ] 3.5 Verify the root and member manifests remain distinct: root privacy neither marks members
  private nor supplies registry/publication approval, and member release metadata does not make
  the root packable.

## 4. Candidate packing, archive validation, and immutable evidence

- [ ] 4.1 Parameterize all three pack scripts with the explicit selected contract and remove
  hard-coded development coordinate assumptions; verify each packer selects only its expected
  member and rejects npm output for a different name or version.
- [ ] 4.2 Extend the token, UI, and SDK archive validators to compare actual packed metadata,
  dependencies, exports, files, assets, licenses/notices, and executable/declaration references
  against the selected release contract before running every existing package-specific gate;
  verify positive candidate fixtures and targeted negative metadata mutations.
- [ ] 4.3 Preserve all existing token import/structure/license, UI CSS scope/asset/React
  externalization, and SDK runtime/declaration/protocol negative tests; verify their complete
  current suites pass unchanged with selected candidate coordinates.
- [ ] 4.4 Implement a clean-checkout release-candidate command that checks exact Node/npm versions,
  builds and packs each member once, and reuses those same tarballs for validation; verify dirty
  source state, wrong toolchain, unconfirmed coordinates, incomplete archives, or a failed gate
  stops before approved evidence is written.
- [ ] 4.5 Generate one schema-versioned candidate evidence record containing the clean source
  commit, UTC time, selected contract, exact producer and application-test toolchains, package
  coordinates, archive filenames, byte lengths, and independently computed SRI SHA-512 values;
  verify the record covers all three archives and all required gates.
- [ ] 4.6 Add integrity and immutability regression tests that truncate, modify, replace, or rebuild
  a recorded archive; verify prior evidence is rejected and cannot authorize later use of changed
  bytes.
- [ ] 4.7 Retain the three exact tarballs and evidence as one commit-addressed disposable/CI
  candidate artifact; verify a retrieval check recomputes every SHA-512 before declaring the set
  usable and that expiration requires a fresh candidate run.

## 5. Candidate-aware isolated and compatibility consumers

- [ ] 5.1 Parameterize the neutral token, isolated React, and neutral iframe SDK consumer
  orchestration with selected exact coordinates while reusing their existing fixtures; verify
  generated disposable manifests/imports and dependency-graph assertions contain no
  `0.0.0-development`, workspace link, local file dependency, or FRED source path.
- [ ] 5.2 Update lockfile-pinned provisioning for the selected candidate graphs; verify it may
  contact package sources only during provisioning and fails actionably when an exact dependency
  or browser prerequisite cannot be prepared.
- [ ] 5.3 Install the actual token, UI, and SDK candidate tarballs from prepared caches into fresh
  locations outside FRED with networking disabled; verify type checks and production builds pass
  without the FRED checkout or producer/application `node_modules`.
- [ ] 5.4 Run the existing browser harness against the candidate token/UI archives and verify both
  themes, optional Geist, Material Symbols, component behavior, local-only successful assets,
  and no dependency installation or browser bootstrap during smoke execution.
- [ ] 5.5 Run the packed candidate SDK against the cross-origin browser and FRED production-host
  compatibility harnesses; verify protocol `"1"`, legacy behavior, origin/window admission,
  request lifecycle, host authority, and iframe/proxy/authentication regressions remain green.

## 6. Exact public-registry verifier (no publication)

- [ ] 6.1 Add a registry-verification command requiring the approved public registry, candidate
  evidence, and three exact name-at-version coordinates; verify it rejects tags, ranges, missing
  packages, unexpected registries, local tarballs, file/workspace specs, and omitted integrity.
- [ ] 6.2 Resolve and download each exact registry package in a fresh temporary area, compare
  registry metadata and downloaded bytes with recorded SHA-512, and require npm-verifiable
  provenance and matching repository identity; verify controlled tests cover success plus missing,
  malformed, mismatched, and unverifiable results.
- [ ] 6.3 Build clean registry-only versions of the token, React UI, and iframe SDK consumers from
  the downloaded exact versions; verify tests fail rather than falling back to candidate tarballs,
  workspace sources, FRED dependencies, or mutable dist-tags.
- [ ] 6.4 Label controlled/local verifier results as `registry-verifier-tooling` and reserve
  `public-registry-verification` for a real run against genuinely published exact packages;
  verify local success cannot produce or imitate the public-registry evidence type.
- [ ] 6.5 Document the exact future post-publication invocation and expected evidence without
  executing it; verify the runbook states that successful genuine registry verification remains
  unavailable until separately authorized publication occurs.

## 7. Toolchain-aware CI and selection

- [ ] 7.1 Add Makefile/npm entry points for contract checks, candidate generation, evidence
  verification, and registry-verifier tooling tests; verify none authenticates, changes registry
  settings, publishes, or invokes the genuine public-registry verification by default.
- [ ] 7.2 Add a release-readiness CI path using exactly Node `24.21.0` and npm `11.19.0` for
  producer candidate work; verify the command fails on version drift and retains all existing
  producer quality, unit, archive, and negative gates.
- [ ] 7.3 Keep FRED application and production-host tests under their separately controlled
  application toolchain and pass only hash-verified candidate archives/evidence between jobs;
  verify neither environment resolves the other's installed dependency tree.
- [ ] 7.4 Extend `scripts/package-inputs.mjs`, workflow path filters, and CI-selection tests for
  every release contract, member manifest/lockfile, toolchain pin, evidence schema/helper,
  registry-verifier fixture, runbook, and orchestration input; verify relevant changes select
  release readiness plus existing archive regressions while unrelated application files may skip
  the package jobs.
- [ ] 7.5 Verify existing canonical CSS/component/protocol/host, asset, license, React baseline,
  consumer, browser, and orchestration inputs retain their prior package and application-job
  selection behavior.

## 8. Release documentation and RFC alignment

- [ ] 8.1 Add a compact `libs/frontend/` release runbook covering decision gates, exact toolchains,
  candidate creation, evidence retention, bootstrap, later Trusted Publishing configuration,
  optional staging, dependency-first publication, genuine registry verification, recovery, and
  rollback; verify every command is clearly classified as implemented repository readiness,
  future maintainer action, or separately authorized publication.
- [ ] 8.2 Update the existing package producer/member documentation for selected coordinates,
  candidate validation, immutable archives, and verifier-tooling limitations; verify the package
  READMEs remain the source for shipped behavior and examples remain application-agnostic.
- [ ] 8.3 Correct only the sequencing/status text in
  `docs/swift/FRED-FRONTEND-PACKAGING-RFC.md` to split readiness, publication plus genuine registry
  verification, and later FRED adoption; verify theme/live-locale, SDK ownership transfer,
  publication, stable release, FRED/RAGS adoption, and broader catalog work remain open.
- [ ] 8.4 Document dependency order and immutable recovery: design tokens before UI, SDK
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
- [ ] 9.3 Run the FRED application quality, production build, affected component tests,
  production-host SDK integration, iframe/proxy/authentication, and CI-selection regression gates
  under the separately controlled application tooling; record exact commands and results.
- [ ] 9.4 Run registry-verifier controlled positive/negative tests and confirm no genuine
  public-registry success is claimed before publication; record the distinction in completion
  evidence.
- [ ] 9.5 Run `openspec validate add-frontend-package-release-foundations --strict`, applicable
  repository-wide OpenSpec validation, and `git diff --check`; verify all pass and all change
  artifacts remain consistent with the implementation.
- [ ] 9.6 Obtain the repository-required independent implementation review of metadata contracts,
  archive immutability, offline/registry isolation, toolchain separation, security failure modes,
  and documentation; resolve every in-scope finding and record any genuinely external maintainer
  gate without weakening acceptance criteria.

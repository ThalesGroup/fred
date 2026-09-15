## 1. Predecessor alignment and manifest authority

- [ ] 1.1 Confirm the synchronized main, active predecessor task 12.7, and implemented retirement delta; document predecessor → retirement → this-change sync/archive order and verify no incident requirement is restored in a disposable semantic sync.
- [ ] 1.2 Add one schema-checked registered-package inventory for the three contained producer members, with stable IDs and explicit build/validator/consumer profiles; verify unknown, duplicate, root, and escaping registrations fail in controlled tests.
- [ ] 1.3 Replace the three-required-role and copied `expectedManifest` fields in the live release-contract/schema/parser with inventory-driven manifest reads; verify all three committed manifests and published metadata still pass current positive tests and a mismatched name/version/export fails.
- [ ] 1.4 Introduce one reviewed release-policy input/schema for scope, repository, branch, registry, workflow filename, environment, access/tag, provenance issuer, owners, and exact producer toolchain; verify conflicting manifest or archive metadata fails before packing.
- [ ] 1.5 Add per-member changelog/version review checks without automatic bumping; verify a selected matching entry is accepted and missing/mismatched/unreviewed entries block publication in controlled tests.
- [ ] 1.6 Preserve the private producer root, declared contained npm workspace links, and separate application pins while removing duplicated manifest copies; verify producer-lockfile boundary and exact Node/npm tests, including rejected unexpected links and published local references.
- [ ] 1.7 Update fixture contracts/tests to the inventory/policy model with an explicit nonapproved state; verify fixture/proposed evidence cannot authorize genuine publication or registry success and existing development commands remain green.

## 2. Selection and compatible dependency baselines

- [ ] 2.1 Implement duplicate-free selected-ID parsing shared by CLI/workflow, with deterministic ordering; verify empty, duplicate, unknown, and private-root selections fail before pack or publish.
- [ ] 2.2 Parameterize the existing packers/candidate validators to produce release candidates only for selected members while retaining package-specific archive/license/asset/reference checks; verify SDK-only, token-only, UI-only, and combined archive sets plus existing token/UI/SDK negative suites.
- [ ] 2.3 Add a reviewed exact prior-release compatibility ledger/reference and import the validated alpha.1 token baseline without modifying historical evidence; verify its registry coordinate, SHA-512, provenance identity, and record reference, and fail on missing/altered/expired evidence.
- [ ] 2.4 Resolve UI's actual committed token peer range against selected token bytes or the approved exact prior baseline; verify UI-only passes with compatible tokens, incompatible/unapproved baselines fail, and combined tokens publish before UI.
- [ ] 2.5 Keep SDK selection independent of token/UI while separating selected publication members from compatibility-only installs; verify SDK-only neutral consumer, cross-origin browser, host regressions, and no UI/token publish command or UI browser prerequisite.
- [ ] 2.6 Preserve source-isolated offline consumer `file:` tarball references and strict registry-only exact resolution as distinct boundaries; verify allowed integrity-verified candidate links and rejection of directories, workspace/checkout fallback, or reused FRED dependency trees.

## 3. Generated candidate record and immutable transfer

- [ ] 3.1 Add an inventory-driven release-record schema/generator recording reviewed source commit, selected/compatibility coordinates and manifest ranges, policy digest, expected provenance, observed producer/application Node/npm, gate results, and actual selected filenames/lengths/SHA-512; verify exact record fields and no hard-coded three-role requirement in unit tests.
- [ ] 3.2 Reuse candidate/archive validation and generate the record from the same packed bytes; verify altered archive bytes, missing license/asset/export, wrong coordinate, and stale/incomplete/fixture records fail before approval.
- [ ] 3.3 Parameterize immutable evidence/fixture-transfer and application-toolchain transfer for selected archives; verify original record digest, GitHub origin run/attempt, artifact ID/API identity, ZIP SHA-256, and archive integrities before/after compatibility without rebuilding.
- [ ] 3.4 Add bound, separate actual per-package publication and verifier outcome identities without mutating candidate fields; verify different commit/run/attempt values remain truthful and spoofed or mismatched identity is rejected.
- [ ] 3.5 Make original artifact selection explicit across new dispatches and failed-job reruns instead of deriving it from current `run_attempt`; verify an attempt-two verifier retrieves the pinned attempt-one artifact and rejects another ID/digest or expired artifact.

## 4. Ordinary workflow and direct publishing boundary

- [ ] 4.1 Extend the existing `.github/workflows/Publish-frontend-packages.yml` with validated `prepare-only`, `publish`, and `verify` manual inputs, preserving the filename, `workflow_dispatch`, committed-`swift` guard, and default preparation; verify YAML/workflow-contract tests reject push publication and obsolete modes.
- [ ] 4.2 Reuse current producer/application preparation and provisioning under separate toolchains for selected packages; verify a `prepare-only` workflow-contract simulation schedules candidate and compatibility jobs but no environment approval, registry mutation, publishing credential, or `id-token: write`.
- [ ] 4.3 Add one protected `npm-publish` publication job using the exact transferred tarballs and direct GitHub-hosted npm OIDC, with `id-token: write` limited to that job and no bootstrap secret; verify prepare/verify/PR jobs cannot schedule or read publishing authority.
- [ ] 4.4 Add per-package exact direct Trusted Publisher preflight and runbook prerequisites for existing packages, workflow filename/repository/environment/direct-publish permission; verify missing/staged-only settings block mutation and tests never treat `npm whoami` or dry-run as proof of OIDC success.
- [ ] 4.5 Check record/source/policy/manifests and reverification of original archive bytes immediately before each publish command; verify stale source, fixture evidence, missing artifact, changed tarball, or unapproved version/changelog prevents publication.
- [ ] 4.6 Implement selected dependency publication ordering and immediate exact-version identity/integrity/provenance verification; verify selected tokens complete before UI and a failed token check prevents UI publication.
- [ ] 4.7 Add a read-only `verify` operation that retrieves explicit retained evidence and schedules only provisioning, exact registry verification, clean consumers/browser/host as applicable; verify no pack, publish, `npm-publish` approval, bootstrap secret, or OIDC write path is reachable.

## 5. Read-only reconciliation and public-registry guarantees

- [ ] 5.1 Parameterize exact-version preflight into absent/matching/unsafe states with approved name/version/SHA-512 and cryptographic provenance comparisons; verify malformed, unauthorized, or mismatched existing versions fail before another publish command.
- [ ] 5.2 Add bounded temporary-404 read-only exact-version/package-wide visibility retries, with immediate auth/malformed/integrity/identity failures; verify initial 404 then valid, exhausted 404, and mismatch regressions without automatic republishing.
- [ ] 5.3 Implement explicit partial-release continuation from original record plus actual prior outcomes, requiring fresh protected approval and publishing only absent exact versions; verify matching versions are skipped, unsafe versions stop all progression, and no GitHub execution identity is spoofed.
- [ ] 5.4 Make independent verification repeatable against the same retained record even when all selected packages already exist; verify current verifier commit/run/attempt differs from each package's historical publishing identity and changed/missing bytes fail.
- [ ] 5.5 Parameterize `registry-verifier.mjs` for selected packages plus approved exact compatibility-only dependencies; verify no local tarball/workspace/checkout/tag fallback and correct installed nonlinked dependency tree before mandatory `npm audit signatures`.
- [ ] 5.6 Retain mandatory downloaded SHA-512, npm signatures, Sigstore certificate verification and independent expected digest/repository/actual publication commit/workflow/issuer checks; verify a validly signed wrong release is rejected for each identity field.
- [ ] 5.7 Run selected clean registry consumers, browser smoke, and production-host compatibility with network-capable cache/Chromium provisioning separate from offline installation/build/execution; verify SDK-only and UI-only matrices, local asset requests, and actionable missing-prerequisite failures.

## 6. Extensibility, CI, and documentation

- [ ] 6.1 Add a disposable fourth-package registration/profile fixture without creating or publishing a real package; verify selection, record schema and generic verifier accept it while missing specialized validator/consumer/creation/trust authorization blocks release.
- [ ] 6.2 Extend `package-inputs.mjs`, CI workflow selection, and workflow-contract tests for inventory/policy/changelogs/record/compatibility inputs, member manifests/lockfiles, canonical CSS/components/protocol, assets/notices, React and host inputs; verify positive affected-input and unrelated-application skip scenarios.
- [ ] 6.3 Preserve per-job consumer cache/Chromium provisioning before offline tests and exact producer/application toolchain pins; verify CI-contract regressions fail if selected jobs depend on another job's filesystem or download during validation.
- [ ] 6.4 Document reviewed manual version/changelog PR, package selection, release-record/artifact inputs, one approval, partial/retry procedure, actual retention setting, exact trust setup, direct-versus-stage permission, fourth-package initial creation, and rollback in `libs/frontend/RELEASE.md`; verify links/commands against implemented CLI and preserve historical appendix unchanged.
- [ ] 6.5 Update producer/consumer docs and only the RFC's release sequencing statements affected by routine publication; verify no duplicate RFC, no FRED/RAGS adoption claim, and all relative repository links resolve.

## 7. Integration evidence and close-out readiness

- [ ] 7.1 Run controlled release-contract/selection/record/publisher/verifier tests under Node 24.21.0/npm 11.19.0; record exact commands and results, clearly distinguishing fixtures from genuine public-registry/OIDC evidence.
- [ ] 7.2 Run producer lint/format/quality/unit, all existing token/UI/SDK positive and negative archive checks, offline isolated consumers, and browser smoke with separate provisioning; record exact commands/results and no weakened acceptance cases.
- [ ] 7.3 Run affected FRED application quality, production build, host/proxy/authentication/iframe regressions under its separate Node 22.13.0/npm 10.9.2 toolchain; record exact commands/results without migrating application sources.
- [ ] 7.4 Obtain the repository-required independent implementation review and resolve in-scope findings; verify review evidence and resolution are documented without marking an execution-dependent real publish successful from fixture tests.
- [ ] 7.5 Run `openspec validate add-frontend-independent-releases --strict`, a disposable post-retirement semantic-spec validation, and `git diff --check`; verify every delta requirement/scenario remains compatible with existing token/UI/SDK guarantees and no obsolete operation returns.
- [ ] 7.6 Before any later sync/archive, verify predecessor task 12.7 has its actual trust/revocation evidence or remains explicitly open, settle predecessor/retirement close-out in order, then use `openspec-sync-specs` to compare and incorporate this implemented delta without losing unaffected scenarios; verify resulting main-spec strict validation before archival.

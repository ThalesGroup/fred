## Context

See [proposal.md](proposal.md) for motivation. The existing private producer at
`libs/frontend/` builds `@fred-oss/design-tokens`, `@fred-oss/ui`, and
`@fred-oss/iframe-sdk` from canonical FRED sources and validates their actual tarballs in
isolated consumers. Maintainers selected independent version `0.1.0-alpha.1` for all three
members, the public npm registry, public access, and initial `next` tag. The root's
`private: true` is already enforced and is
an orchestration safeguard, not a member publication setting.

The inspected npm lockfile uses two intentionally different local-reference shapes.
`libs/frontend/package-lock.json` records the three declared workspace members as
`link: true` entries resolving to the contained `design-tokens`, `ui`, and `iframe-sdk`
directories. Separately, the React and SDK isolated-consumer scripts copy validated
tarballs into fresh temporary consumers and run `npm install --package-lock-only` on
those `.tgz` files before offline `npm ci`, so npm may record `file:` archive references
in disposable manifests and lockfiles. These expected representations are not equivalent
to a published local dependency or a directory/workspace fallback.

The production-host integration currently runs the host with
`apps/frontend/node_modules/.bin/vitest` and points it at an SDK entry extracted from the
validated tarball. The corrected plan preserves that split: application dependencies run
the host; verified archive or exact registry bytes supply the SDK under test.

The synchronized
[`frontend-package-archives` specification](../../specs/frontend-package-archives/spec.md)
is the existing behavioral contract. This change adds release readiness without
relaxing its token CSS, packaged asset/license, scoped UI CSS, React externalization,
runtime/declaration resolution, protocol-`"1"`, offline consumer, browser, or
production-host guarantees. The governing
[`FRED frontend packaging RFC`](../../../docs/swift/FRED-FRONTEND-PACKAGING-RFC.md)
continues to cover publication and adoption.

The repository currently pins Node `22.13.0` and npm `10.9.2` for the producer and
runs the combined package/application compatibility job on Node `22.13.0`. As verified
on 2026-09-11, npm's official documentation requires npm `11.5.1` or later and Node
`22.14.0` or later for Trusted Publishing, while staged publishing requires npm
`11.15.0` or later and Node `22.14.0` or later. The current Node 24 LTS archive lists
Node `24.21.0` with bundled npm `11.19.0`. This design selects those exact versions for
release production, not as an implicit migration of application-owned tooling:

- [npm Trusted Publishing](https://docs.npmjs.com/trusted-publishers/)
- [npm staged publishing](https://docs.npmjs.com/staged-publishing/)
- [official Node 24 archive](https://nodejs.org/en/download/archive/v24)

The maintainer supplied authenticated evidence that bootstrap account `marc.fawaz` has the
owner role in npm organization `fred-oss`, confirmed `marc.fawaz` for all four package API, SDK
protocol, release, and enduring npm-publishing owner roles, and selected direct Trusted
Publishing for subsequent releases. The GitHub release-reviewer identity is the distinct account
`marcfawaz`. The temporary granular token remains outside the repository and is neither an input
to builds/tests nor inspected by this change. Separately authorized bootstrap and recovery runs
have now published all three selected coordinates; genuine all-package registry verification
remains incomplete.

A repository administrator reports that the `npm-publish` environment is configured. A supplied
screenshot supports required reviewer `marcfawaz`, **Prevent self-review** disabled,
administrator bypass disabled, branch `swift` only with zero tags, and the existence of an
environment secret named `NPM_BOOTSTRAP_TOKEN`; the screenshot crops the environment name. This
is not independent API verification, token-content validation, environment approval, workflow
execution, or publication evidence. The maintainer will both initiate and approve releases;
allowing that self-review preserves rather than removes the required environment approval gate.

## Goals / Non-Goals

**Goals:**

- Make expected coordinates and release metadata one explicit input to all packing,
  archive, evidence, consumer, and registry-verification commands.
- Produce reviewable candidate tarballs and evidence that bind validation to immutable
  bytes from a clean source commit and an exact release toolchain.
- Keep candidate archive validation offline after provisioning, and make post-publication
  registry verification deliberately online, exact, and incapable of local fallback.
- Retain the current application compatibility baseline without forcing FRED application
  tests onto the release-production toolchain.
- Keep repository work testable while keeping external execution and publication tasks visibly
  gated.

**Non-Goals:**

- Creating npm organizations/packages, changing registry access, authenticating locally,
  triggering another workflow, or publishing another version.
- Migrating FRED to registry dependencies, transferring canonical SDK protocol ownership,
  removing temporary re-exports, or changing protocol `"1"`.
- Changing public package exports, expanding UI components, changing canonical assets,
  or weakening any archived validation guarantee.
- Changing RAGS or using its identity, routes, models, or repository as package input.
- Folding frontend package SemVer into FRED's application, image, chart, Python, or iframe
  protocol versioning.

## Decisions

### 1. Use a validated external release contract, not archive-declared expectations

A small machine-readable release contract under `libs/frontend/release/` will contain a
schema version, decision status, exact producer Node/npm pins, and one record per member:
name, exact version, required manifest metadata, dependencies/peers, expected public
exports, and intended dist-tag. Member order is design tokens, iframe SDK, then UI; the
SDK has no package dependency, while UI requires a selected compatible token peer.

All packers, validators, evidence generation, and consumers will receive this contract
explicitly. Common parsing and validation belongs in one release helper rather than
three new name/version branches. Archive validators will compare packed manifests to the
selected contract and then run their existing package-specific checks. They will never
derive the expected name, version, dependency range, exports, files, or release metadata
from the archive being judged.

Maintainers selected `@fred-oss/design-tokens`, `@fred-oss/ui`, and
`@fred-oss/iframe-sdk` at independent version `0.1.0-alpha.1`, public
`https://registry.npmjs.org/` access, and `next`. They also confirmed bootstrap account
`marc.fawaz` has organization-owner authority in `fred-oss`, named `marc.fawaz` as the package
API, SDK protocol, release, and enduring npm-publishing owner, and selected direct Trusted
Publishing for subsequent releases. The contract is therefore `maintainer-confirmed`. This
authorizes approved-candidate preparation only when every existing clean-source, exact-toolchain,
immutable-byte, dual-toolchain, and workflow gate passes; it does not authorize publication.

Alternatives rejected:

- Environment variables alone: too easy to omit, difficult to review, and do not provide
  one synchronized dependency contract.
- Reading expectations from each packed `package.json`: accepts precisely the metadata
  mistakes release validation is intended to catch.
- Applying the FRED application version to every package: conflates independent version
  axes and release cadences.

### 2. Keep the workspace private and make only member manifests release-ready

`libs/frontend/package.json` remains `private: true`; enumeration rejects the root and
expects exactly the three selected members. Confirmed member manifests gain consistent
release metadata such as repository directory, homepage/bugs, license, engines, and
bounded files/exports, without adding registry credentials. UI's React and React DOM peer
ranges remain those already validated unless separately reviewed, and its token peer must
match the selected release contract.

Published member manifests contain only release-safe semver dependency references and
reject `workspace:`, `file:`, `link:`, `git+file:`, directory, or source-checkout references. The
private producer lockfile is validated with a narrower boundary rule: npm-generated
`link: true` entries are allowed exactly for the members declared by the root workspace
manifest, provided every resolved target is the expected member directory inside
`libs/frontend/`. Any undeclared link, name/directory mismatch, symlink escape, absolute
checkout target, or other link is rejected. This preserves npm's legitimate workspace
model without permitting it to leak into a packed manifest.

The confirmed registry, public access, scope, and `next` policy are recorded in each member's
`publishConfig`; no credential is stored. npm-organization ownership did not imply ownership of
the package API or SDK protocol; those roles are now separately and explicitly assigned to
`marc.fawaz`. The confirmed direct policy applies to subsequent Trusted Publishing and does not
replace the guarded bootstrap path. Verified organization ownership is also a namespace boundary:
every selected member name must belong to the recorded `@fred-oss/` scope.

Alternative rejected: making the root publishable, because it is orchestration-only and
would create an accidental fourth package.

### 3. Generate one immutable candidate set and evidence record

A release-candidate command builds and packs all members once in a clean checkout using
Node `24.21.0` and npm `11.19.0`. It validates each tarball against the selected contract,
runs all existing positive and negative archive checks, and computes SHA-512 directly
from each completed file. One JSON evidence record contains:

- schema version, UTC creation time, clean source commit, and exact producer and
  application-test Node/npm versions;
- selected contract identity and decision status;
- exact package coordinate, archive filename, byte length, and SRI-formatted SHA-512;
- references/results for archive, isolated-consumer, browser, and host-compatibility gates.
- explicit expected provenance identity: source repository, source commit, authorized
  Trusted Publishing workflow identity, and each candidate artifact digest.

Disposable output remains under `libs/frontend/target/`; CI retains the three tarballs and
evidence together as a candidate artifact identified by commit. Any later manual or
workflow-driven publication must verify these hashes before using these exact tarballs.
Re-running `npm pack` creates a new candidate set even when source appears unchanged.

Alternative rejected: rebuilding during publication, because provenance of a source commit
does not prove that two independently built tarballs are byte-identical.

### 4. Split release production from application-owned compatibility tooling

The exact release toolchain is recorded in the release contract and checked by the
candidate command before it mutates `target/`. A dedicated release-readiness CI job uses
Node `24.21.0` with npm `11.19.0` for manifest synchronization checks, packing, archive
validation, and candidate evidence. Existing package quality and negative tests continue
to run as regression gates. Because GitHub Actions jobs do not share a filesystem, this job
provisions its own isolated-consumer dependency caches in a separate network-capable step after
installing producer dependencies and before any consumer-dependent tests. The tests continue to
install and validate archives offline and do not bootstrap a missing cache themselves.

Checks that execute FRED application tests remain in an environment provisioned from
`apps/frontend/package-lock.json` and the application's separately controlled Node/npm
baseline. They consume the already produced SDK tarball and its verified integrity, never
the release job's `node_modules`. The host and its test runner resolve only the application
installation; the SDK entry resolves only from the hash-verified extracted archive or,
during post-publication verification, the exact registry installation. The evidence record
names both environments. Updating application tooling remains separate work.

Alternative rejected: changing every frontend job to the release Node/npm pair, because
that would turn package readiness into an unreviewed application-toolchain migration.

### 4a. Rehearse the immutable job boundary with a fixture-only transfer

Before maintainers confirm registry coordinates, the release-readiness job produces one
designated transfer set using the development fixture contract and the exact release toolchain.
It packs and validates the three members once for this set, copies only those tarballs into a
dedicated transfer directory, and writes strict producer metadata containing the checked-out
commit, fixture-contract digest, observed Node/npm versions, exact package records, and GitHub
repository/workflow/run/attempt identity. The intermediate metadata kind is
`fixture-archive-transfer`: it attests only producer archive validation and explicitly records
that consumer, browser, and host gates have not yet run. The artifact name includes fixture,
source-commit, run, and attempt identity; retention is seven days. Credentials, dependency trees,
consumer caches, checkout files, and mutable `target/archives` output are excluded.
Before clearing prior output, the producer accepts only a dedicated descendant of its own
`target/` directory or a system temporary directory; filesystem, checkout, workspace, home, and
symlink output roots fail before deletion.

The application-toolchain package job depends on that producer job and downloads the exact named
artifact from the same workflow execution. It independently selects its checkout commit and
development fixture contract, verifies the transfer schema and exact four-file allowlist, checks
the run/attempt association, package coordinates, regular-file status, byte lengths, and SHA-512,
then supplies the verified paths and integrities explicitly to the existing token, React UI, SDK,
browser, and production-host helpers. Transfer validation uses a dedicated staged-consumer root;
it never invokes a packer, searches for a latest successful artifact, or falls back to
`target/archives`, package source, workspace links, or FRED's installed package tree. Producer and
receiver jobs provision their own lockfile-pinned caches, and the receiver provisions its own
browser before offline execution.

Only after every downstream gate succeeds does the receiver write the existing
`fixture-candidate-evidence` classification. That final record includes the producer metadata
digest and artifact identity, exact transferred archive records, independently observed
application Node/npm versions, and consumer/browser/host results. A failed or incomplete gate
removes or leaves absent the final record. The receiver re-verifies the immutable transfer
metadata digest, byte lengths, and SHA-512 values after the downstream gates and compares every
final package record with the original transfer record, so a gate cannot mutate and silently
re-baseline an archive. Neither intermediate nor final fixture evidence can be promoted into
approved candidate or public-registry evidence. This rehearsal therefore completes new
fixture-infrastructure tasks only; it does not satisfy maintainer-gated tasks 4.7, 7.3, 9.1, or
9.2.

Alternative rejected: rebuilding in the receiver and comparing package versions, because equal
coordinates do not prove equal tarball bytes and would leave the cross-toolchain boundary
untested.

### 4b. Reuse the transfer boundary for an approved first-release candidate

The manual first-release workflow extends the same transfer format with a distinct
`release-candidate-archive-transfer` classification available only to a fully
`maintainer-confirmed` contract. The release-toolchain job packs one designated set after its
fixture regressions, validates the three archives, and uploads only the transfer metadata and
tarballs. The application-toolchain job independently verifies those bytes, provisions its own
dependencies and browser, runs the offline consumers/browser/production-host gates, rechecks the
transfer after the gates, and only then adds `release-candidate-evidence` to the retained
commit/run-specific artifact. Fixture and proposed contracts cannot enter this path.

`.github/workflows/Publish-frontend-packages.yml` is manual-only, rejects refs other than
`refs/heads/swift`, and defaults to `prepare-only`. The `publish-bootstrap` choice reaches a
separate `npm-publish` environment job after candidate validation. The environment secret
`NPM_BOOTSTRAP_TOKEN` is referenced only by its single initial publishing step; checkouts,
installs, builds, tests, transfers, and registry verification never receive it. The publishing
step verifies the evidence and bytes again, checks the exact source/repository/workflow identity
and authenticated bootstrap account, and confirms all three versions are absent before the first
registry mutation. It publishes design tokens before UI and checks each registry integrity before
continuing; the SDK follows independently.

A version already present at preflight is treated as a partial or conflicting release and stops
the workflow. If a publish command fails after a possible mutation, the helper reconciles the
exact coordinate against the approved integrity: matching bytes are recorded as confirmed, while
a missing, mismatched, or unavailable registry result remains explicitly indeterminate. It never
claims that nothing was published from an ambiguous command failure. A failure after one publish
preserves logs/evidence and requires an explicit maintainer recovery decision; rerunning into an
existing coordinate or rebuilding under prior evidence is forbidden. Genuine registry
verification is a later job in the same explicitly
publishing run. It uses the application Node `22.13.0` / npm `10.9.2` baseline for clean-consumer,
browser, and production-host execution while verifying the exact registry-installed package
bytes; it does not silently move application evidence to the release-production toolchain. Local
tests cover workflow and publication control flow but cannot claim GitHub environment approval,
provenance emission, npm package creation, or registry success.

The bootstrap workflow uses token authentication only because these package coordinates do not
yet exist. After creation, maintainers configure the exact workflow and `npm-publish` environment
for direct Trusted Publishing, update the workflow to remove the bootstrap secret, validate a new
version, and revoke the temporary token. Selecting direct publishing does not implement this OIDC
transition. Staged publishing is not used for initial creation.

### 5. Parameterize the existing consumers; do not create release-only product fixtures

The neutral token consumer, isolated React consumer, iframe SDK consumer, browser harness,
and production-host compatibility gate remain the acceptance fixtures. Their orchestration
will take the selected names and exact versions and assert the resulting dependency graph.
Candidate validation stages the actual tarballs plus lockfile-pinned dependencies in fresh
directories outside FRED, then runs offline exactly as today. It rejects development
versions, directory dependencies, workspace links, source paths, dependency-tree reuse,
and network access.

The disposable consumer is allowed to name only its copied candidate `.tgz` files using
npm's generated `file:` manifest or lockfile representation. Before installation, the
orchestrator resolves each target without following an escape, requires it to be a regular
tarball file within the temporary consumer, and compares its SHA-512 with candidate evidence.
The generated manifest and lock are validated before `npm ci` or any build consumes the graph.
Every local reference in root or nested dependency fields and every local lock resolution must
map by package name to one approved evidence record, use exactly
`file:${approvedRecord.filename}`, resolve to a contained non-symlink regular file, and match the
recorded archive bytes. This is the form generated by the existing React and SDK consumers for
their staged `design-tokens.tgz`, `ui.tgz`, and `iframe-sdk.tgz` files. Alternative spellings are
rejected rather than interpreted by another path parser because npm expands or removes syntax
such as a leading tilde or embedded control characters. Dependency declarations legitimately
have no integrity field; every direct or nested local package-resolution entry must contain a
valid SRI SHA-512 value exactly matching candidate evidence. A matching basename alone is never
sufficient. A `file:` target to a directory, a different or additional file, a symlink, any
checkout path, an unapproved package identity, a nested unmatched dependency, or an archive whose
bytes or resolution integrity do not match is rejected. Local Git checkout dependencies are
classified as local and rejected before installation, including mixed-case or leading-whitespace
spellings that npm normalizes. Installed FRED packages
themselves must be ordinary extracted directories, not symlinks. Registry dependencies such as
React continue to resolve from the prepared cache during candidate validation.

Provisioning remains a distinct network-capable operation. Browser execution performs no
installation. Package renaming cannot be accomplished by blind string replacement inside
source fixtures; generated fixture manifests/import maps or narrowly substituted disposable
copies must retain generic examples and be checked against the contract.

Alternative rejected: adding a second set of release fixtures, which would allow archive
foundations and release acceptance to drift.

### 6. Make registry verification an exact post-publication operation

The registry verifier accepts all three exact coordinates and the candidate evidence file.
It requires the approved public registry explicitly, refuses tags/ranges and local specs,
downloads each exact version into a fresh OS temporary area, and verifies both registry
metadata and downloaded SHA-512 before installation. Registry-installed consumers accept
only exact registry versions and reject every tarball, directory, workspace, source-checkout,
or reused-dependency-tree fallback.

For each package, the resolver checks the contract-bound identity, exact version, approved
registry, downloaded archive bytes, and candidate SHA-512 before dependency installation. It
then generates a registry lockfile in the fresh disposable root, validates every resolved FRED
entry in that graph against the approved contract and candidate evidence, and only then runs
`npm ci --ignore-scripts`. Before `npm audit signatures`, the verifier uses npm's actual installed
tree plus the installed package manifest and real path to prove that the exact package is a
non-linked directory inside that disposable root. A lockfile-only directory is not audit input;
missing installation, local fallback, an escaping path, or any graph mismatch fails before
signature acceptance. Vulnerability-audit side effects are disabled during materialization so
the separately mandatory signature audit remains an explicit gate.

Provenance verification is two separate gates. First, the verifier cryptographically checks
the signature and attestation chain using the pinned supported tooling, requiring the signer
certificate SAN to equal the authorized GitHub workflow identity and its issuer to equal the
explicit expected GitHub Actions OIDC issuer. Second, it compares
the verified statement with values that were already bound to the approved release contract
and candidate evidence: the subject/artifact digest must equal the candidate tarball digest,
the source repository must equal the approved FRED repository identity, the source commit must
equal the candidate commit, and the publisher identity must equal the specifically authorized
Trusted Publishing workflow identity. Expected values are never populated from the downloaded
attestation. A correctly signed statement for another repository, commit, workflow, or artifact
is therefore rejected as the wrong release.
The commit comparison selects exactly one resolved dependency whose normalized URI identifies
the approved repository (including npm's `git+https://...@refs/...` form); unrelated commits,
missing matches, and ambiguous matches fail closed.

Provenance discovery follows npm's actual registry metadata contract: `npm view --json` exposes
the attestation endpoint at `dist.attestations.url`, while the sibling `provenance` object only
describes its predicate type. Matching npm/pacote's registry restriction, the verifier parses
the advertised absolute HTTP(S) URL, requires the npm attestation endpoint and exact coordinate,
then re-roots only its pathname onto the explicitly approved registry. Missing, malformed,
credential-bearing, non-HTTP(S), fragment-bearing, endpoint-mismatched, or coordinate-mismatched
values fail before provenance is fetched. Controlled adapter tests feed representative raw npm
metadata and continue through the same fetch and cryptographic-verification path used by the CLI;
they do not mock an already normalized `resolvePackage` result.

It then materializes clean versions of the existing consumers using exact registry
coordinates, creates/uses their registry-derived lock graphs, and runs the applicable
type-check, production build, browser, and host compatibility evidence without access to
local tarballs or FRED package sources. Failure to resolve a public package is a failure,
not permission to use a candidate archive.

Automated repository tests exercise argument validation, signature failure, validly signed but
identity-mismatched provenance, integrity success/failure, and fallback rejection against
controlled fixtures or a local test registry. Their evidence
is labelled `registry-verifier-tooling`; only a real run against exact published public
coordinates can produce `public-registry-verification` evidence.

The post-publication workflow provisions Chromium in `target/playwright` and sets
`PLAYWRIGHT_BROWSERS_PATH=target/playwright` for the complete public-registry verification job.
Before any registry lookup, the verifier requires that setting, confirms Playwright's selected
Chromium executable is contained in that directory, and confirms the executable exists. It
never installs or downloads a browser during verification; a missing or default-cache browser
fails with the provisioning command.

Alternative rejected: accepting `next` or another tag at verification time, because tags
are mutable and cannot identify the reviewed release.

### 7. Separate bootstrap, Trusted Publishing, staged policy, and publication

The compact runbook records four maintainer gates before the guarded publish path is authorized:

1. Confirm organization-controlled scope, package names, public-access/registry policy, exact
   coordinates, and named package API, SDK protocol, release, and enduring publishing owners.
2. Confirm and record the bootstrap actor with account or organization authority capable of
   creating brand-new scoped public packages. `marc.fawaz` and its verified `fred-oss` owner role
   satisfy this bootstrap-identity gate; the token remains an environment secret and is never
   repository data. Package-scoped credentials for nonexistent packages are not assumed to work.
3. Create each initial package through the separately approved bootstrap process. npm's
   staged publishing cannot create a brand-new package.
4. Configure the exact trusted publisher repository and workflow identity for each existing
   package, bind it to future candidate evidence, and apply the confirmed direct-publishing policy
   with GitHub environment approval. This future OIDC workflow transition remains separate from
   initial bootstrap creation and publication authorization. The unselected staged alternative
   remains documented with its npm `11.15.0`+, Node `22.14.0`+, existing-package, publish-access,
   and approving-maintainer 2FA prerequisites.

The guarded workflow is prepared in this phase, but its token value is never read or stored and
no GitHub environment or registry state is created. The runbook sequences design tokens before
UI, with the SDK independent. Registry verification follows publication. FRED adoption follows
successful registry verification in another OpenSpec change; RAGS adoption is separately tracked.

### 8. Keep recovery version-based and bytes-preserving

Before publication, a failed gate discards the candidate. A byte change invalidates the
candidate evidence. After publication, packages are immutable: recovery deprecates a bad
version when appropriate and publishes a newly versioned correction or restores a prior
validated version. A partial sequence does not publish UI until its token dependency is
available. Later consumers roll back through lockfiles and previously built application
images, never by overwriting an npm version.

### 9. Extend exact CI selection without widening all frontend validation

`scripts/package-inputs.mjs`, its selection tests, and the pull-request filter will include
the release contract, member manifests/lockfile, release helpers, evidence schema, registry
verifier and fixtures, release documentation, the governing frontend packaging RFC, and
release-readiness workflow wiring. These
inputs select both release-readiness and applicable existing archive regression jobs.
Unrelated application changes may continue to skip package work; canonical package and host
inputs retain their existing selection behavior. Workflow-contract tests also require every job
that runs consumer-dependent package tests to provision its own caches before those tests. The
release-readiness and application-toolchain jobs run as one producer/receiver chain when selected;
tests require an exact same-run artifact name, explicit dependency, separate provisioning, and no
mutable latest-run lookup.

### 10. Make only a targeted RFC sequencing correction

The implementation updates the existing RFC in place. Its combined “publish prereleases and
migrate FRED” row is split into release readiness, publication plus genuine registry
verification, and later FRED adoption. The RFC continues to mark publication, SDK ownership
transfer, FRED/RAGS adoption, theme/live-locale work, and stable release as open. Shipped
package behavior remains in the existing package READMEs; the new runbook covers release
operation only.

### 11. Reconcile delayed visibility and preserve truthful partial-release identity

The first bootstrap run (`34853407387`, attempt `1`) published
`@fred-oss/design-tokens@0.1.0-alpha.1` from commit
`f49f2439d54b44f7739c5bd7fca3f789e0e528d6`. Its immediate exact-version lookup returned
404, and the workflow stopped before UI or SDK. Retained artifact `10352121632` has ZIP SHA-256
`25fe6a65498d7109b8ec5a2b6d43de24fa9b9d161376ab80f2416c82ac328b82`; its three archive
SHA-512 values match the approved evidence. A subsequent independent registry check verified the
design-token archive, npm signature, Sigstore certificate, repository, workflow, source commit,
and digest. UI and SDK remain absent.

Post-publication reconciliation uses one shared HTTP adapter for the configured registry's safely
encoded exact package/version endpoint. It deliberately does not use `npm view`: npm `11.19.0`
requests package-wide metadata before selecting an exact version, so a package-wide 404 can hide
available exact-version metadata. The adapter bounds each request, follows no redirect, retains
the selected registry origin, and retries only an actual exact-endpoint HTTP 404 for six attempts
at five-second intervals. It never retries `npm publish`. Authentication/authorization errors,
other HTTP failures, redirects, timeouts, malformed responses, wrong name/version, or integrity
mismatches stop immediately, as does exhausted visibility. Bootstrap preflight, publication
reconciliation, recovery state checks, and registry-verifier metadata resolution share this
adapter. The next package cannot begin until the previous exact version is visible with the
expected identity and bytes.

Recovery is a third, explicit manual input in the existing `swift`-restricted workflow, separate
from ordinary bootstrap and its all-versions-absent preflight. A reviewed recovery plan pins the
original source commit, run/attempt, final artifact ID/name, and artifact ZIP digest. An
unprotected preparation job retrieves and hash-checks that exact retained artifact without
pre-extracting it. The recovery helper requires exactly the candidate evidence, candidate transfer
metadata, and three expected tarballs as regular ZIP entries; rejects traversal, links, special
entries, omissions, and additions before extraction; extracts into a fresh isolated directory;
and validates the transfer metadata, evidence, filenames, byte lengths, and SHA-512 values. Only
verified ZIP contents are materialized for transfer. Preparation then cryptographically verifies
the existing design-token version against the original candidate provenance, requires UI and SDK
to be absent, and records recovery evidence tied to the current GitHub run.

The distinct `npm-publish` environment job independently rechecks the pinned ZIP after artifact
download, extracts it freshly, rejects any mismatch between the ZIP and separately transferred
candidate copies, and repeats the registry/provenance preflight. Only then may its step receive the
bootstrap token. UI followed by SDK are published exclusively from paths in that verified fresh
extraction, not from loose transferred archives. The helper cleans the extraction on success or
failure and never regenerates original candidate evidence.

npm provenance truthfully records the commit executing each publish. The original candidate
evidence is not rewritten: design tokens continue to require source commit `f49f2439…`, while the
recovery evidence requires UI and SDK attestations to name the recovery run's actual
`GITHUB_SHA`. Repository, workflow path/ref, certificate issuer, archive digests, coordinates, and
original candidate/artifact identity remain unchanged. Final registry verification validates
these per-package expectations before consumers run. If the original artifact expires, any
published role differs, a missing role appears unexpectedly, or provenance cannot be verified,
the recovery stops; maintainers must prepare a newly versioned release rather than weakening or
relabeling evidence.

The first recovery attempt after the ZIP correction (run `34873471933`) downloaded and
hash-checked the pinned ZIP, then exited `13` with an unsettled top-level await before producing
recovery evidence. The recovery entry module was awaiting preparation, preparation dynamically
imported the registry verifier for real existing-package provenance checks, and that verifier
statically imported recovery-evidence validation back from the still-evaluating entry module.
Function-level tests imported an already-evaluated recovery module and replaced the existing-
package verifier, so they could not expose the evaluation deadlock.

Reusable plan, artifact-identity, workflow-identity, original-evidence, provenance-expectation,
and recovery-evidence validation now lives in an execution-independent module. Both CLI modules
import that module directly; the recovery entry retains its prior validation exports for callers
but is no longer a dependency of the registry verifier. The recovery CLI may therefore complete
its dynamic verifier import without waiting on itself. Fresh-process tests launch the actual
recovery and registry-verifier entry points with bounded timeouts, a controlled local TLS registry,
an external npm command shim, and cryptographically signed controlled provenance. They exercise
real existing-package verification and module evaluation while remaining incapable of reaching a
writable registry or producing genuine public-registry evidence.

### 12. Continue verification from retained publication evidence

The completed recovery artifact is a second immutable trust boundary. A reviewed continuation
contract pins artifact `10363547296`, its source commit/run/attempt/name and ZIP SHA-256, the
nested original artifact identity, the historical recovery execution, and the per-package source
commits. A `verify-existing` workflow choice retrieves that artifact by ID with read-only Actions
permission, validates GitHub metadata and the outer ZIP, validates the nested original ZIP, and
compares every copied archive and evidence file with both containers. It never rebuilds a
candidate or rewrites original candidate/recovery evidence.

Historical publication and current verification are independent identities. Recovery evidence is
validated against the pinned historical execution: design tokens require `f49f2439…`, while UI
and SDK require `a1fedc66…`. Separate preparation evidence records the current workflow's actual
commit, run, and attempt, and final evidence retains both identities. GitHub environment values
are read, never replaced to impersonate the publication run.

npm's exact-version endpoint remains authoritative for coordinate and SHA-512 admission. Because
`npm pack` also consults package-wide metadata, the verifier performs a bounded read-only
package-wide readiness check before invoking npm. Only an actual package-wide HTTP 404 is retried;
authentication, authorization, redirects, malformed data, or identity/integrity drift fail
immediately. The subsequent npm install remains exact and registry-only, and signature audit,
Sigstore verification, expected provenance matching, clean consumers, browser smoke, and host
compatibility are unchanged.

The new choice explicitly excludes candidate generation, candidate compatibility transfer, and
both publication jobs. It uses neither the `npm-publish` environment, bootstrap secret, nor
`id-token: write`. Preparation may install pinned tooling and verification separately provisions
application dependencies and Chromium. Final evidence is created and uploaded only after the
complete verifier returns successfully, making the same retained artifact independently
rerunnable until it expires.

## Risks / Trade-offs

- **[A confirmed contract could be mistaken for publication authorization]** → Keep candidate
  generation bound to committed clean source and exact dual-toolchain validation, and retain the
  explicit manual publication choice plus protected-environment approval as separate gates.
- **[A release-only toolchain can diverge from application CI]** → Retain both environments,
  pass hash-verified archives between them, and record both toolchains in evidence.
- **[CI-retained artifacts can expire or be downloaded incorrectly]** → Retain tarballs and
  evidence as one commit-addressed artifact and re-check SHA-512 before any later use; expiration
  requires a fresh candidate run.
- **[Registry APIs or provenance representation can evolve]** → Pin npm exactly, test failures
  closed, and revise the verifier/toolchain together from current official documentation.
- **[A valid signature can attest the wrong release]** → Keep repository, commit, workflow, and
  artifact-digest expectations outside the downloaded statement and require every identity
  comparison after cryptographic verification.
- **[Broad local-reference rejection would reject npm's intended graphs]** → Validate each
  boundary separately: allow only declared producer links and integrity-matched disposable
  tarballs whose declaration is the exact generated canonical reference and whose package
  identity, contained real path, bytes, and required resolution integrity all match approved
  evidence, while keeping published manifests and registry consumers local-reference-free.
- **[Registry metadata shape is handled incorrectly or points elsewhere]** → Read npm's
  `dist.attestations.url`, validate its endpoint and coordinate, re-root the pathname to the
  approved registry, and exercise raw npm-shaped responses in controlled adapter tests.
- **[Staged publishing may appear to solve bootstrap]** → State explicitly that it requires an
  existing package and separate initial package creation authority.
- **[Independent versions add release coordination]** → Encode the selected UI/token pairing
  in one contract and publish dependencies before consumers.
- **[A public package could be partially released]** → Stop the sequence before UI if its token
  peer is unavailable; supersede published mistakes with new versions rather than overwrite. If
  an original candidate remains intact and a subset is already published with matching bytes and
  provenance, the reviewed partial-recovery path may publish only the still-absent coordinates.
- **[A package-wide registry lookup can lag behind an exact version]** → Admit identity only from
  the bounded exact-version endpoint, then retry only package-wide 404 reads before npm transport;
  reject authentication, malformed data, identity/integrity drift, and every other response
  failure immediately.
- **[Loose recovery files can diverge from a hash-pinned ZIP]** → Derive the candidate baseline
  from a safe fresh extraction at preparation and publication, compare every transferred copy,
  and publish only from the verified extraction.
- **[Module tests can miss an entry-point evaluation cycle]** → Keep reusable recovery validation
  independent of CLI execution and run bounded preparation, publication, and recovery-aware
  registry-verifier subprocesses in fresh Node processes.

## Migration Plan

1. Implement coordinate-independent contract parsing, expected-metadata validation, candidate
   evidence/integrity/provenance-identity handling, boundary-aware producer/consumer reference
   validation, registry-verifier fixture tests, and CI selection using non-authoritative test
   contracts.
2. Record the selected `fred-oss` scope, exact `@fred-oss/*@0.1.0-alpha.1` coordinates, public
   npm/`next` policy, bootstrap actor and authority, named owners, confirmed direct policy, and
   guarded workflow identity; transition the complete contract to `maintainer-confirmed`.
3. Synchronize the three member manifests, UI token peer, and producer lockfile to those selected
   coordinates while keeping the root private; run the full archive regression suite.
4. Prepare the manual, `swift`-restricted workflow and approved transfer/publication controls.
   Controlled fixture tests prove them without producing approved evidence or contacting npm.
5. After the confirmed contract reaches committed `swift`, run preparation to produce one
   immutable candidate, validate it under both toolchains, and retain its evidence.
   A separately approved manual run may then bootstrap the nonexistent packages from those exact
   bytes and perform genuine public-registry verification.
6. For the recorded partial first release only, merge the reconciliation correction, dispatch
   `recover-bootstrap`, review the pinned original artifact and recovery evidence, and approve
   the protected job only if existing design-token provenance and missing UI/SDK preflight pass.
   The recovery publishes no design-token command and does not rebuild archives. Before another
   dispatch, require the real preparation CLI and recovery-aware registry-verifier entry point to
   pass the fresh-process module-evaluation regressions.
7. After all three coordinates exist, merge the verification continuation, dispatch only
   `verify-existing`, and retain genuine all-package registry evidence. Do not rerun either
   bootstrap path or rebuild the original candidate.
8. Only after registry evidence exists, plan FRED adoption and any SDK ownership transfer. If
   transfer changes SDK bytes, validate and publish that version before adoption. Plan RAGS
   separately.

Rollback of the continuation is deletion of disposable verification output or reversion of its
repository changes. Published versions remain immutable and are not changed by this path.

## Open Questions

No release-contract ownership or publishing-policy decision remains open. Initial publication is
complete. The later OIDC workflow transition and genuine all-package registry verification remain
unexecuted operational gates rather than contract decisions.

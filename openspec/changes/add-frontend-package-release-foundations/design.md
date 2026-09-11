## Context

See [proposal.md](proposal.md) for motivation. The existing private producer at
`libs/frontend/` builds `@fred/design-tokens`, `@fred/ui`, and
`@fred/iframe-sdk` from canonical FRED sources and validates their actual tarballs in
isolated consumers. Its member manifests, producer lockfile, validators, tests, and
consumer graphs still encode `0.0.0-development`; the pack scripts also select the
three current names directly. The root's `private: true` is already enforced and is
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

Public npm lookups during the completed audit did not find the three provisional
coordinates. A 404 is not evidence that the `@fred` scope is available to or controlled
by this organization. No publication or registry configuration exists in this checkout.

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
- Make repository work testable before registry ownership decisions while keeping
  approval-dependent tasks visibly gated.

**Non-Goals:**

- Creating npm organizations/packages, choosing or changing registry access, adding a
  publishing workflow, authenticating to npm, or publishing any version.
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

The proposed initial policy is the current three `@fred/*` names, independently selected
`0.1.0-alpha.1` versions, and `next`; these values are not evidence of scope ownership or
permission. Coordinate-independent implementation uses explicit test fixture contracts.
An approved candidate run requires a maintainer-confirmed contract. Final member manifest
and lockfile synchronization is therefore a gated task after coordinate confirmation.

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
reject `workspace:`, `file:`, `link:`, directory, or source-checkout references. The
private producer lockfile is validated with a narrower boundary rule: npm-generated
`link: true` entries are allowed exactly for the members declared by the root workspace
manifest, provided every resolved target is the expected member directory inside
`libs/frontend/`. Any undeclared link, name/directory mismatch, symlink escape, absolute
checkout target, or other link is rejected. This preserves npm's legitimate workspace
model without permitting it to leak into a packed manifest.

Registry URL, public-access setting, scope ownership, and owner identities are decisions,
not harmless metadata defaults. Any `publishConfig` fields that encode those choices are
added only after maintainers confirm them; release-readiness validation fails if the
selected contract requires a value that the manifest does not contain.

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
to run as regression gates.

Checks that execute FRED application tests remain in an environment provisioned from
`apps/frontend/package-lock.json` and the application's separately controlled Node/npm
baseline. They consume the already produced SDK tarball and its verified integrity, never
the release job's `node_modules`. The host and its test runner resolve only the application
installation; the SDK entry resolves only from the hash-verified extracted archive or,
during post-publication verification, the exact registry installation. The evidence record
names both environments. Updating application tooling remains separate work.

Alternative rejected: changing every frontend job to the release Node/npm pair, because
that would turn package readiness into an unreviewed application-toolchain migration.

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
The generated lock is then allowed to retain that exact archive reference. A `file:` target
to a directory, a different file, a symlink, any checkout path, or an archive whose bytes do
not match is rejected. Installed FRED packages themselves must be ordinary extracted
directories, not symlinks. Registry dependencies such as React continue to resolve from the
prepared cache during candidate validation.

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

Alternative rejected: accepting `next` or another tag at verification time, because tags
are mutable and cannot identify the reviewed release.

### 7. Separate bootstrap, Trusted Publishing, staged policy, and publication

The compact runbook records four maintainer gates before any later publish command exists:

1. Confirm organization-controlled scope, package names, owners, public-access/registry
   policy, and exact coordinates.
2. Confirm and record the bootstrap actor or credential identity with account or organization
   authority capable of creating brand-new scoped public packages. Package-scoped credentials
   for nonexistent packages are not assumed to work.
3. Create each initial package through the separately approved bootstrap process. npm's
   staged publishing cannot create a brand-new package.
4. Separately confirm and configure the exact trusted publisher repository and workflow identity
   for each existing package, bind it to future candidate evidence, then choose direct or staged
   publishing as maintainer policy. Staging is recommended for review but remains a policy choice
   and requires its documented Node/npm/access/2FA prerequisites.

No publishing workflow or token is added in this change. The runbook sequences a later
publication as design tokens first, SDK independently, and UI only after its selected token
peer exists. Registry verification follows publication. FRED adoption follows successful
registry verification in another OpenSpec change; RAGS adoption is separately tracked.

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
verifier and fixtures, release documentation, and release-readiness workflow wiring. These
inputs select both release-readiness and applicable existing archive regression jobs.
Unrelated application changes may continue to skip package work; canonical package and host
inputs retain their existing selection behavior.

### 10. Make only a targeted RFC sequencing correction

The implementation updates the existing RFC in place. Its combined “publish prereleases and
migrate FRED” row is split into release readiness, publication plus genuine registry
verification, and later FRED adoption. The RFC continues to mark publication, SDK ownership
transfer, FRED/RAGS adoption, theme/live-locale work, and stable release as open. Shipped
package behavior remains in the existing package READMEs; the new runbook covers release
operation only.

## Risks / Trade-offs

- **[Final coordinates are unconfirmed]** → Implement contract parsing, validation, evidence,
  consumer parameterization, verifier tests, and documentation with explicit fixtures first;
  block manifest/lockfile candidate completion until maintainers confirm the coordinate record.
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
  tarballs, while keeping published manifests and registry consumers local-reference-free.
- **[Staged publishing may appear to solve bootstrap]** → State explicitly that it requires an
  existing package and separate initial package creation authority.
- **[Independent versions add release coordination]** → Encode the selected UI/token pairing
  in one contract and publish dependencies before consumers.
- **[A public package could be partially released]** → Stop the sequence before UI if its token
  peer is unavailable; supersede published mistakes with new versions rather than overwrite.

## Migration Plan

1. Implement coordinate-independent contract parsing, expected-metadata validation, candidate
   evidence/integrity/provenance-identity handling, boundary-aware producer/consumer reference
   validation, registry-verifier fixture tests, and CI selection using non-authoritative test
   contracts.
2. Have maintainers confirm scope ownership, final package coordinates, release metadata,
   owners, registry/access policy, distinct bootstrap identity and authority, authorized Trusted
   Publishing repository/workflow identity, and staged/direct policy. This is a gate, not an
   implementation inference.
3. Synchronize the three member manifests, UI token peer, and producer lockfile to the confirmed
   contract while keeping the root private; run the full current archive regression suite.
4. Produce one candidate set under the exact release toolchain, provision separately, run all
   offline consumers/browser and application-host compatibility gates, and retain tarballs plus
   evidence. This completes repository readiness but publishes nothing.
5. In later authorized work, bootstrap nonexistent packages, configure trusted publishers,
   publish the exact candidate bytes in dependency order, and run genuine public-registry
   verification.
6. Only after registry evidence exists, plan FRED adoption and any SDK ownership transfer. If
   transfer changes SDK bytes, validate and publish that version before adoption. Plan RAGS
   separately.

Rollback during this change is deletion of disposable candidate output or reversion of the
repository changes; no registry state exists to roll back.

## Open Questions

- Which organization-controlled npm scope and final package names will maintainers approve?
- Which exact owners may bootstrap packages, and what organization/account permission path is
  approved for creating each nonexistent public scoped package, under which bootstrap identity?
- Which public registry/access settings and exact source repository plus GitHub workflow identity
  will be authorized for later Trusted Publishing and provenance matching?
- Will maintainers choose staged or direct publishing after bootstrap? Recommended default:
  staged review for later releases, subject to the documented prerequisites.
- Will all three first prereleases use the proposed independent value `0.1.0-alpha.1`, and will
  `next` be the initial dist-tag? Recommended default: yes, once ownership is confirmed.

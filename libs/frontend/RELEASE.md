# Frontend package release readiness

The producer contains coordinate-independent release tooling for the design-token, UI,
and iframe SDK packages. It does not confirm ownership of the proposed `@fred` scope,
authorize a publisher, create packages in a registry, or publish an archive.

## Release contracts

Release expectations are external inputs, not values inferred from a built archive or a
downloaded attestation:

- `release/development-fixture-contract.json` describes the current private workspace and
  its deliberately non-publishable development coordinates. It supports repository tests.
- `release/proposed-release-contract.json` records discussion defaults only. Its `proposed`
  state is not publication approval and cannot produce approved candidate evidence.
- A maintainer-confirmed contract must record the exact package names and versions, registry,
  dist-tag policy, producer Node/npm versions, source repository, bootstrap publisher, and
  later Trusted Publishing workflow certificate identity and GitHub Actions OIDC issuer before
  release evidence can be approved. Fixture identities, development versions, and the
  development tag cannot be promoted by changing only the contract state.

The selected producer pins are [Node 24.21.0](https://nodejs.org/en/download/archive/v24.21.0)
and [npm 11.19.0](https://github.com/npm/cli/releases/tag/v11.19.0). They satisfy npm's
[Trusted Publishing requirements](https://docs.npmjs.com/trusted-publishers/) at the time of
this change. They are deliberately separate from FRED application's existing Node/npm baseline.

The workspace root remains `private: true` and is never a release member. npm-generated
workspace links are allowed only for the three explicitly declared producer members and must
resolve inside this checkout. Published manifests reject `workspace:`, `file:`, `link:`,
`git+file:`, directory, or source-checkout dependency references.

Disposable offline consumers may contain npm-generated `file:` references to the exact
candidate tarballs named by verified evidence. Before `npm ci`, every root or nested local
manifest/lock reference must map to an approved package identity and use exactly
`file:<approved filename>`. It must remain a non-symlink regular file inside the isolated
consumer and match the recorded filename, package version, and archive SHA-512. Dependency
declarations have no integrity field; every direct or nested local package-resolution entry must
contain valid SRI SHA-512 integrity exactly matching the approved record. A matching basename
alone is insufficient. Tilde, whitespace/control-character, dot-segment, encoded, query,
fragment, backslash, absolute, and escaping alternatives are noncanonical. Directory
dependencies, local Git checkout references, additional local archives, workspace links,
checkout fallback, and reuse of FRED's dependency tree remain invalid. A registry consumer has
a stricter boundary: every FRED dependency must resolve to the exact expected registry coordinate
and integrity without a local fallback.

## Coordinate-independent checks

From `libs/frontend`, use the repository development toolchain for ordinary archive work:

```sh
make release-check
make release-test
make pack-check
make isolated-consumer
make host-integration
make browser-smoke
```

Provision consumer dependencies and Chromium separately as described in
[README.md](README.md). Offline validation performs no download. The production-host gate uses
the frontend application's own pinned test dependencies to run the host; the SDK under test is
always loaded from a validated archive or an exact registry installation.

Fixture evidence is visibly labelled `fixture-candidate-evidence`. It exercises the tools but
is neither approved candidate evidence nor proof that a public package exists.

## Fixture transfer between CI toolchains

The pull-request workflow rehearses the future immutable release boundary without publishing.
Its release-readiness job uses Node `24.21.0` and npm `11.19.0` to create exactly one designated
fixture archive per package after archive validation. It uploads only those three `.tgz` files
and `fixture-transfer.json` as a seven-day artifact. The artifact name binds the checked-out
commit, workflow run ID, and run attempt; its metadata also binds the fixture contract digest,
observed producer toolchain, exact coordinates, filenames, byte lengths, SHA-512 values, and
repository/workflow identity. It contains no checkout files, credentials, dependency trees,
consumer caches, or browser installation.

The dependent application-toolchain job downloads that exact artifact from the same workflow
run. Before any consumer executes, the receiver rejects a missing or additional file, a
non-regular file or symlink, modified bytes, malformed metadata, a different contract or source
commit, or a different run identity. It then passes only the verified absolute archive paths and
integrities to the existing isolated consumers, browser harness, and production-host integration.
It neither rebuilds packages nor falls back to `target/archives`, workspace sources, or locally
generated names. Consumer-cache and browser provisioning remain separate network-capable steps;
the transferred validation itself installs from the prepared caches and performs no browser
bootstrap.

Final `fixture-candidate-evidence` is written only after all receiver gates pass. It records the
transfer metadata digest and artifact identity, the exact archive records, the independently
observed application Node/npm versions, and downstream results. Failure removes any stale final
record. A final post-gate verification recomputes the transferred lengths and SHA-512 values and
requires the evidence package records to remain identical to producer metadata. Both the transfer
metadata and final evidence remain fixtures: neither can authorize publication or satisfy
public-registry verification.

For a local separate-directory rehearsal, provision dependencies and Chromium first, then use
the command-line entry points. The producer command must run under the fixture contract's exact
Node/npm versions; the receiver intentionally runs under the application toolchain:

```sh
make consumer-provision
make browser-install

npm run fixture:transfer:create -- \
  --output /tmp/fred-fixture-producer \
  --repository ThalesGroup/fred \
  --workflow local-fixture-transfer \
  --run-id local-review \
  --run-attempt 1

cp -R /tmp/fred-fixture-producer /tmp/fred-fixture-receiver

PLAYWRIGHT_BROWSERS_PATH=target/playwright npm run fixture:transfer:validate -- \
  --transfer /tmp/fred-fixture-receiver \
  --evidence /tmp/fred-fixture-validation/final-evidence.json \
  --stage-root /tmp/fred-fixture-validation/staged \
  --repository ThalesGroup/fred \
  --workflow local-fixture-transfer \
  --run-id local-review \
  --run-attempt 1
```

Local rehearsal metadata truthfully records whether the checkout was dirty. GitHub Actions
requires a clean checkout. Producer output cleanup is restricted to a dedicated descendant of
`libs/frontend/target/` or a system temporary directory; broad or symlink roots are rejected.
After a push, reviewers must still confirm the real upload/download actions selected the same-run
artifact and retained final evidence; local success cannot prove that remote service behavior. If
an artifact expires, is incomplete, or fails verification, discard it and rerun the producer job.
Never rebuild an archive in the receiver or repair an artifact in place.

## Candidate and registry commands

After maintainers supply a confirmed contract, use its exact producer toolchain and a clean
source commit:

```sh
npm run release:candidate -- --contract /absolute/path/to/confirmed-contract.json \
  --approved \
  --evidence /absolute/path/to/candidate-evidence.json
```

The command packs each member once, validates those bytes, and records the source commit,
exact Node/npm versions, package coordinates, filenames, sizes, and SHA-512 integrities. Later
publication must use those same bytes. Rebuilding or modifying an archive invalidates the
evidence and requires the complete candidate validation again.

Before reusing retained artifacts, run `npm run release:verify-evidence --` with the same
`--contract`, `--evidence`, `--design-tokens`, `--ui`, and `--iframe-sdk` paths. It recomputes
every archive integrity and rejects a changed contract, filename, or byte sequence.

After genuine publication, registry verification accepts only exact coordinates and previously
recorded integrity:

```sh
npm run registry:verify -- --contract /absolute/path/to/confirmed-contract.json \
  --evidence /absolute/path/to/approved-candidate-evidence.json \
  --design-tokens @scope/design-tokens@x.y.z \
  --ui @scope/ui@x.y.z \
  --iframe-sdk @scope/iframe-sdk@x.y.z
```

The verifier does not fall back to local tarballs or workspace sources. Signature validity is
necessary but insufficient: Sigstore verification first requires the expected workflow
certificate URI and issuer, then the attested artifact digest, source repository, source commit,
and authorized workflow identity must independently match the confirmed contract and candidate
evidence. Provenance discovery reads npm's `dist.attestations.url`, validates its npm endpoint
and exact coordinate, and re-roots only its pathname onto the approved registry before fetching;
missing, malformed, or disallowed endpoint metadata fails closed. Controlled local tests of this
behavior are not a successful public-registry run.

## Maintainer decisions and sequencing

Before an approved candidate can be produced, maintainers must confirm:

1. an organization-controlled npm scope and the final names/initial versions;
2. package owners and bootstrap authority for creating each package;
3. the registry, access, dist-tag, and staged-publishing policy;
4. the exact bootstrap identity and later Trusted Publishing workflow identity.

Initial package creation is distinct from later Trusted Publishing: staged publishing cannot
create a package that does not exist. Bootstrap permissions must therefore be verified rather
than assumed. Publication remains a manual, separately authorized operation.

Publish design tokens before UI; the iframe SDK is independent of that pair. Verify the exact
published bytes and provenance before any FRED adoption. If later protocol ownership transfer
changes the SDK archive, build, validate, and publish a new SDK version before FRED consumes it.
RAGS adoption is separate work.

On failure, stop promotion, retain evidence and logs, and do not overwrite a published version.
Correct the source or release contract, choose a new version when necessary, rebuild, and rerun
all validation. Consumer rollback restores a previously verified dependency set and redeploys;
it never mutates an existing registry version.

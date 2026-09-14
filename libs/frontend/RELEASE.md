# Frontend package release readiness

The producer prepares `@fred-oss/design-tokens`, `@fred-oss/ui`, and
`@fred-oss/iframe-sdk` version `0.1.0-alpha.1` for public npm publication under the
`next` tag. Repository commands and pull-request jobs do not publish. The manual
publication workflow remains disabled by default and cannot run until the incomplete
ownership and publishing-policy fields below are confirmed in a committed release
contract.

## Release contracts

Release expectations are external inputs, not values inferred from a built archive or a
downloaded attestation:

- `release/development-fixture-contract.json` exercises the selected coordinates while
  retaining fixture identities and evidence classifications. It supports repository tests
  but can never authorize publication.
- `release/proposed-release-contract.json` records the confirmed `fred-oss` organization,
  three `@fred-oss` coordinates, public npm registry/access, `next` tag, bootstrap account,
  verified organization-owner authority, and expected workflow identity. It remains
  `proposed` because the enduring owners and later publishing policy are incomplete.
- A maintainer-confirmed contract must record the exact package names and versions, registry,
  dist-tag policy, producer Node/npm versions, source repository, bootstrap publisher, named
  API/protocol/release/publishing owners, and
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

Fixture evidence is visibly labelled `fixture-candidate-evidence`. It exercises the tools with
the selected coordinates but is neither approved candidate evidence nor proof that a public
package exists.

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

For each exact coordinate, the verifier checks registry metadata and downloaded archive SHA-512
against the approved candidate before installation. It then creates and validates a registry-only
lock graph, including every resolved FRED package in that graph, and runs `npm ci --ignore-scripts`
in the fresh disposable root. `npm audit signatures` runs only after `npm ls` and the installed
manifest/real-path checks prove that the exact package is a non-linked dependency inside that
root. A package-lock alone is insufficient, and a missing install or local/workspace/checkout
fallback fails closed.

## Prepared first-release workflow

`.github/workflows/Publish-frontend-packages.yml` is manual-only. It rejects every ref except
`swift`, defaults to `prepare-only`, and requires the explicit `publish-bootstrap` choice before
the publication job exists. The workflow uses Node `24.21.0` and npm `11.19.0` to validate and
pack one designated candidate set, transfers those exact bytes to the separately pinned
application Node `22.13.0` / npm `10.9.2` job, and writes approved evidence only after offline
consumers, browser smoke, and production-host compatibility pass. The final 30-day artifact keeps
the three tarballs, transfer metadata, and evidence together.

The publication job downloads that artifact, recomputes every SHA-512, checks the committed
source and workflow identity, confirms the authenticated npm account is the contract's bootstrap
identity, and preflights that none of the exact versions exists. It publishes design tokens, then
UI, then the independent SDK with `--provenance --access public --tag next`, checking registry
integrity after each package. A pre-existing or partially published coordinate stops the complete
sequence before another mutation; do not rerun blindly or overwrite a version. The following job
performs genuine registry/provenance and clean-consumer verification under the separately pinned
application Node `22.13.0` / npm `10.9.2` toolchain so its browser and production-host evidence
does not silently migrate application tooling. None of these claims is evidence that a workflow
has actually run.

That final job sets `PLAYWRIGHT_BROWSERS_PATH=target/playwright` for both `make browser-install`
and `npm run registry:verify`. The verifier confirms that Playwright's Chromium executable exists
inside that exact directory before registry resolution and never installs a browser itself. A
missing directory, absent executable, or resolution through Playwright's default cache fails with
the provisioning command.

The initial token is used only for creation. Later releases require a separately reviewed workflow
change that removes the bootstrap secret and uses npm Trusted Publishing. The choice to allow
direct Trusted Publishing or require staged publication remains unresolved; staged publishing
cannot create a brand-new package.

### Manual GitHub and npm setup

1. In the GitHub repository, open **Settings → Environments**, create `npm-publish`, restrict its
   deployment branches to `swift`, and select the required release reviewers. The identities of
   those reviewers remain a maintainer decision.
2. Add one environment secret named `NPM_BOOTSTRAP_TOKEN` containing the already-created temporary
   granular token. Do not add it as a repository or organization secret. Do not expose it to a
   pull-request, preparation, validation, installation, or registry-verification job.
3. Complete `maintainerApproval.owners`, select `maintainerApproval.publishingPolicy`, change the
   contract state to `maintainer-confirmed`, review the resulting contract, and merge it to
   `swift`. Organization ownership does not select the package API or SDK protocol owners.
4. In **Actions → Publish frontend packages → Run workflow**, select `swift` and
   `prepare-only`. Review the candidate and application-validation jobs. This is a rehearsal; a
   later run rebuilds and therefore creates a different candidate record.
5. For the authorized creation run, select `swift` and `publish-bootstrap`. The environment gate
   pauses the publish job after the exact candidate is prepared and validated. Approve only that
   job and its commit-addressed artifact. Do not trigger the workflow from another ref.
6. Confirm that the final registry-verification job succeeds for all three exact versions before
   any adoption. If publication stops partway, preserve the logs/evidence, verify the published
   subset, and make an explicit recovery decision; never rerun into an existing version or accept
   different bytes.
7. After all packages exist, configure a GitHub Actions Trusted Publisher on each npm package with
   organization `ThalesGroup`, repository `fred`, workflow filename
   `Publish-frontend-packages.yml`, and environment `npm-publish`. Choose direct vs staged allowed
   actions only after the open policy decision is recorded.
8. Replace the bootstrap-token step with the reviewed OIDC path, verify it with a new version,
   restrict traditional token publishing as approved, then revoke the temporary granular token
   from npm and remove `NPM_BOOTSTRAP_TOKEN` from the GitHub environment.

## Maintainer decisions and sequencing

The following are confirmed: organization `fred-oss`, scope `@fred-oss`, the three
`0.1.0-alpha.1` coordinates, public `https://registry.npmjs.org/`, `next`, bootstrap account
`marc.fawaz`, verified organization-owner authority, and the expected GitHub workflow identity.
Before an approved candidate can be produced, maintainers must still confirm:

1. the named package/public-API, SDK protocol-compatibility, release, and enduring npm-publishing
   owners;
2. the later direct or staged Trusted Publishing policy and required reviewers.

Initial package creation is distinct from later Trusted Publishing: staged publishing cannot
create a package that does not exist. The supplied organization-owner evidence establishes the
bootstrap account's authority without recording its token. Publication remains a manual,
separately authorized operation.

Publish design tokens before UI; the iframe SDK is independent of that pair. Verify the exact
published bytes and provenance before any FRED adoption. If later protocol ownership transfer
changes the SDK archive, build, validate, and publish a new SDK version before FRED consumes it.
RAGS adoption is separate work.

On failure, stop promotion, retain evidence and logs, and do not overwrite a published version.
Correct the source or release contract, choose a new version when necessary, rebuild, and rerun
all validation. Consumer rollback restores a previously verified dependency set and redeploys;
it never mutates an existing registry version.

# Frontend package release readiness

The producer prepares `@fred-oss/design-tokens`, `@fred-oss/ui`, and
`@fred-oss/iframe-sdk` version `0.1.0-alpha.1` for public npm publication under the
`next` tag. Repository commands and pull-request jobs do not publish. The manual
publication workflow remains disabled by default. The release contract is now
maintainer-confirmed, but publication still requires a committed `swift` source, an explicit
manual publication choice, and approval through the protected environment.

## Release contracts

Release expectations are external inputs, not values inferred from a built archive or a
downloaded attestation:

- `release/development-fixture-contract.json` exercises the selected coordinates while
  retaining fixture identities and evidence classifications. It supports repository tests
  but can never authorize publication.
- `release/proposed-release-contract.json` retains its established filename and records the
  confirmed `fred-oss` organization, three `@fred-oss` coordinates, public npm registry/access,
  `next` tag, bootstrap account, verified organization-owner authority, all four named owners,
  direct publishing policy, and expected workflow identity. Its state is
  `maintainer-confirmed`.
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

Using the confirmed contract requires its exact producer toolchain and a clean source commit:

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
the ordinary publication job exists. The separate `recover-bootstrap` choice is restricted to the
reviewed partial-release incident described below. The workflow uses Node `24.21.0` and npm `11.19.0` to validate and
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

### Partial first-release incident and reviewed recovery

Workflow run `34853407387`, attempt `1`, from commit
`f49f2439d54b44f7739c5bd7fca3f789e0e528d6` published
`@fred-oss/design-tokens@0.1.0-alpha.1`. The publish helper then made one immediate registry
lookup, received a temporary exact-version 404, and stopped before publishing UI or iframe SDK.
The correction retries only exact-version reads for bounded visibility lag, then requires exact
name, version, and candidate SHA-512. It never retries `npm publish`; unauthorized reads,
malformed or mismatched metadata, and exhausted retries remain stopping failures.

Bootstrap, recovery, and registry verification now share a bounded HTTP adapter for the encoded
exact-version endpoint (`/<package>/<version>`). It does not use `npm view`, because npm 11 first
requests package-wide metadata even when given an exact coordinate. Only an HTTP 404 from the
exact-version endpoint means absent or temporarily invisible; redirects, authentication or other
HTTP failures, timeouts, malformed JSON, and identity/integrity drift fail immediately. The
adapter follows no redirect and requires the response to remain on the selected registry request.

The final original artifact is ID `10352121632`, named
`frontend-packages-release-f49f2439d54b44f7739c5bd7fca3f789e0e528d6-34853407387-1`, with
ZIP SHA-256 `25fe6a65498d7109b8ec5a2b6d43de24fa9b9d161376ab80f2416c82ac328b82`.
`release/bootstrap-recovery.json` records that immutable incident identity and declares design
tokens published and UI/SDK missing. Read-only verification on 2026-09-14 found the exact design
token version with candidate SHA-512
`sha512-+3UeYRe4Qhgtx+U1T/QQqu9172N+7c+DbuSo8G/2mvp5nbrjgLJj1VDdcOv4AYsuaYEvpNzERHo7Z6GTFNenqw==`;
npm signature audit, Sigstore certificate validation, and independent digest/repository/commit/
workflow checks passed. The UI and SDK exact versions returned 404. Package-wide metadata for
design tokens, which temporarily returned 404 during the incident, is no longer used for
reconciliation.

Recovery is an explicit `recover-bootstrap` selection, not a rerun of ordinary bootstrap. Its
uncredentialed preparation job retrieves the exact original ZIP, verifies its GitHub artifact
metadata and ZIP digest, and passes the ZIP unopened to the recovery helper. The helper requires
the exact five regular entries (candidate evidence, transfer metadata, and three archives),
rejects traversal, links, special files, missing files, and additions, extracts into a fresh
temporary directory, cross-checks transfer metadata/evidence/archive bytes, and only then
materializes the preserved recovery inputs. It cryptographically verifies the existing
design-token package and requires UI and SDK to remain absent before recording recovery evidence
tied to the current workflow execution.

The protected job downloads that preserved ZIP and its derived copies, repeats ZIP hash, safe
extraction, transfer/evidence/archive, registry, and provenance verification independently, and
rejects any inconsistent transferred copy. Only its publication step can receive
`NPM_BOOTSTRAP_TOKEN`; UI and SDK are published from the fresh verified ZIP extraction, never
from the loose transferred copies. Design tokens are not published.

The original evidence remains truthful and unchanged. Design-token provenance must identify the
original `f49f2439…` source. Because npm provenance records the publishing workflow's actual
`GITHUB_SHA`, UI and SDK must identify the recovery run's committed `swift` SHA. Recovery evidence
binds both facts while retaining the same approved repository, workflow path/ref, certificate
issuer, coordinates, and archive digests. Final registry verification consumes that evidence and
performs signature, Sigstore, exact-identity, clean-consumer, browser, and host checks for all
three packages.

Manual recovery procedure (not executed by repository tests):

1. Merge the reviewed correction to `swift` before the retained artifact expires. Confirm artifact
   `10352121632` is still available and its reported and downloaded ZIP digests match the value
   above. Confirm the helper accepts exactly the five expected regular entries and derives the
   candidate evidence, transfer metadata, and archive paths from that ZIP. If it is unavailable,
   different, malformed, or contains an unsafe or unexpected entry, stop and create a newly
   versioned candidate.
2. Recheck exact registry state: design tokens must match the recorded name/version/SHA-512 and
   provenance; UI and SDK must be absent. Any other state stops this recovery.
3. In **Actions → Publish frontend packages → Run workflow**, select `swift` and
   `recover-bootstrap`. Do not select `publish-bootstrap`, which intentionally rejects the partial
   state.
4. Review the preparation job's recovery evidence. Confirm it names the original artifact/run and
   original candidate commit, the current workflow run and real `GITHUB_SHA`, design tokens as the
   verified published role, and UI/SDK as absent roles. Confirm the retained candidate copies are
   byte-identical to the independently extracted pinned ZIP.
5. Approve the `npm-publish` environment only if that evidence is exact. The protected step issues
   no design-token publish command and publishes UI before SDK. It does not rebuild or relabel any
   archive.
6. Require the final public-registry job to verify design-token provenance against `f49f2439…`
   and UI/SDK provenance against the recovery SHA, then pass clean registry consumers, browser
   smoke, and production-host integration. Retain the recovery artifact and logs.
7. If any read, publish, or reconciliation step fails, do not rerun blindly. Inspect exact-version
   state. A package confirmed with the expected bytes is immutable; an indeterminate or drifted
   state requires explicit review and normally a new version.

The workflow and controlled tests only prepare this recovery. They do not constitute protected
environment approval, publication of UI/SDK, or genuine all-package registry verification.

The initial token is used only for creation. Later releases require a separately reviewed workflow
change that removes the bootstrap secret and uses direct npm Trusted Publishing with GitHub
environment approval. Selecting that policy does not implement the OIDC transition or authorize
publication. Staged publishing cannot create a brand-new package.

The unselected [staged-publishing alternative](https://docs.npmjs.com/staged-publishing/)
requires npm `11.15.0` or later, Node `22.14.0` or later, an existing package, publish access,
and 2FA on the approving maintainer's account. These prerequisites remain documented for future
policy review; they do not change the confirmed direct policy.

### Contract and environment confirmation (2026-09-14)

Maintainers confirmed `marc.fawaz` as the package API, SDK protocol compatibility, release, and
enduring npm-publishing owner, and selected direct Trusted Publishing for subsequent releases.
The GitHub release-reviewer account is `marcfawaz`; it is a distinct identifier from the npm and
contract owner identity `marc.fawaz` and is intentionally not added to the release-contract
schema.

A repository administrator reports that the `npm-publish` environment is configured, supported
by a supplied screenshot showing required reviewer `marcfawaz`, **Prevent self-review** disabled,
administrator bypass disabled, deployment branch `swift` only with zero tags, and an environment
secret named `NPM_BOOTSTRAP_TOKEN`. Because **Prevent self-review** is disabled, the maintainer who
initiates a release will also satisfy the required-reviewer gate; this is intentional, and the
approval gate itself remains required. The screenshot crops the environment name, so the association with `npm-publish` is an
administrator report rather than independently visible screenshot evidence. Repository tooling
did not query GitHub settings, inspect or validate the secret, approve an environment deployment,
run the workflow, or publish a package.

### Manual GitHub and npm setup

1. In the GitHub repository, independently verify the administrator-reported `npm-publish`
   environment configuration before release: deployment branch `swift` only, no tags, required
   reviewer `marcfawaz`, self-review allowed, and administrator bypass disabled. Keep the required
   approval gate even though the initiating maintainer may approve it.
2. Independently verify that the environment, rather than the repository or organization, has one
   secret named `NPM_BOOTSTRAP_TOKEN`. Do not inspect or expose its value to a pull-request,
   preparation, validation, installation, or registry-verification job.
3. Review the maintainer-confirmed contract and merge it to `swift`. The four ownership fields use
   npm/contract identity `marc.fawaz`; the distinct GitHub reviewer identity is `marcfawaz`.
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
7. After all packages exist, configure direct GitHub Actions Trusted Publishing on each npm
   package with organization `ThalesGroup`, repository `fred`, workflow filename
   `Publish-frontend-packages.yml`, and environment `npm-publish`. Preserve GitHub environment
   approval for the direct publication path.
8. Replace the bootstrap-token step with the reviewed OIDC path, verify it with a new version,
   restrict traditional token publishing as approved, then revoke the temporary granular token
   from npm and remove `NPM_BOOTSTRAP_TOKEN` from the GitHub environment.

## Maintainer decisions and sequencing

The following are confirmed: organization `fred-oss`, scope `@fred-oss`, the three
`0.1.0-alpha.1` coordinates, public `https://registry.npmjs.org/`, `next`, bootstrap account
`marc.fawaz`, verified organization-owner authority, package/public-API, SDK protocol-
compatibility, release, and enduring npm-publishing owner `marc.fawaz`, direct Trusted Publishing
for subsequent releases, and the expected GitHub workflow identity. The required GitHub reviewer
is the distinct account `marcfawaz`. No release-contract owner or publishing-policy decision
remains unresolved.

Initial package creation is distinct from later Trusted Publishing: staged publishing cannot
create a package that does not exist. The supplied organization-owner evidence establishes the
bootstrap account's authority without recording its token. Publication remains a manual,
separately authorized operation, and the selected direct policy neither implements the later OIDC
workflow transition nor authorizes a publish run.

Publish design tokens before UI; the iframe SDK is independent of that pair. Verify the exact
published bytes and provenance before any FRED adoption. If later protocol ownership transfer
changes the SDK archive, build, validate, and publish a new SDK version before FRED consumes it.
RAGS adoption is separate work.

On failure, stop promotion, retain evidence and logs, and do not overwrite a published version.
Correct the source or release contract, choose a new version when necessary, rebuild, and rerun
all validation. Consumer rollback restores a previously verified dependency set and redeploys;
it never mutates an existing registry version.

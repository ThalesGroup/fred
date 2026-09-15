# Frontend package releases

The first `@fred-oss/design-tokens`, `@fred-oss/ui`, and `@fred-oss/iframe-sdk`
`0.1.0-alpha.1` versions are published on public npm under the `next` tag. Genuine
all-package registry verification completed in a separate read-only run. The retained manual
workflow now has manual `prepare-only`, protected `publish`, and read-only `verify`
operations for subsequent independently selected versions. This ordinary path has not
been dispatched or used to publish a new version; the completed first-release evidence
below remains historical and unchanged.

## Release contracts

Release expectations are external inputs, not values inferred from a built archive or a
downloaded attestation:

- `release/package-inventory.json` registers stable member IDs, contained producer workspaces,
  and reviewed specialized archive/consumer profiles. Its schema and parser reject unknown,
  duplicate, root, and escaping registrations. The private root's workspace list must agree.
- The three committed member `package.json` files alone supply live names, versions, peers,
  dependencies, exports, and publish metadata. The selected contract no longer copies them.
- `release/development-fixture-contract.json` retains fixture identities and evidence
  classifications. Tests may construct future independent coordinates only in disposable
  manifests; fixture results never authorize publication or genuine registry verification.
- `release/proposed-release-contract.json` retains its established filename and records the
  confirmed central scope, public npm registry/access, `next` tag, source repository/branch,
  workflow filename/environment, four named owners, direct policy, expected provenance issuer,
  exact producer/application toolchains, and reviewed baseline digest. Its state is
  `maintainer-confirmed`; package API or SDK protocol ownership is not derived from npm scope.
- A maintainer-confirmed policy must record exact registry, producer and application Node/npm
  versions, source repository, bootstrap publisher, named
  API/protocol/release/publishing owners, and
  later Trusted Publishing workflow certificate identity and GitHub Actions OIDC issuer before
  release evidence can be approved. Fixture identities, development versions, and the
  development tag cannot be promoted by changing only the contract state.

The selected producer pins are [Node 24.21.0](https://nodejs.org/en/download/archive/v24.21.0)
and [npm 11.19.0](https://github.com/npm/cli/releases/tag/v11.19.0). They satisfy npm's
[Trusted Publishing requirements](https://docs.npmjs.com/trusted-publishers/) at the time of
this change. They are deliberately separate from FRED application's existing Node/npm baseline.

Each member has a `CHANGELOG.md` entry matching its committed manifest version. The factual
`alpha.1` entries were added in this migration and point to the unchanged historical
first-release evidence below; they do not assert that the original publication PR contained
these changelog files. A future
version requires one exact, nonempty `Review: approved` entry in the source-reviewed version PR;
that machine check does not itself grant a new npm publication approval. No version is bumped
automatically. `make release-check` validates the inventory, schemas, manifests, policy,
private producer links, changelogs, and durable compatibility ledger offline.

The source-reviewed `release/compatibility-baselines.json` retains the exact previously
published design-token `alpha.1` coordinate, registry SHA-512, independently expected
attested digest/repository/publication commit/workflow/issuer, and historical verification
trace. It was imported after checking the retained verification artifact ZIP digest, its
historical evidence, exact npm registry tarball bytes, and real Sigstore verification. The
policy pins a digest of that ledger; altering its expectations requires reviewed policy
change. Normal local checks read the ledger and no longer need the expiring CI ZIP. An
UI-only provisioning now separately rechecks exact registry metadata/downloaded SHA-512,
the installed nonlinked dependency graph and npm signatures, and cryptographically verified
Sigstore provenance against the ledger's independent expectations. It warms the dedicated
React cache and retains the verified token archive plus a receipt. Offline validation rechecks
the receipt and bytes; it never needs the historical CI ZIP or a network fetch.

`release/release-record.schema.json` and `scripts/release-record.mjs` define separate candidate,
publishing-attempt, aborted-terminal, publication-outcome, and verification record models. Selected or all-member
`release:candidate` preparation reuses its already validated evidence/bytes to emit a companion
record with selection, policy/baseline digests, source identity, observed toolchains, archive
metadata, peer ranges, and gates. Fixture/incomplete records, unpersisted attempt models, and
controlled verification models cannot authorize publication or claim public registry success.
The ordinary publisher binds candidate artifact ID, originating run/attempt, ZIP SHA-256,
record digest, exact selected coordinates, actual publishing commit/run/attempt, policy digest,
and package-specific ordered command intents into a separate pre-command attempt artifact.
Upload and independent GitHub API/ZIP/record readback must complete before any `npm publish`
command; the selected member's intent is read back again at its own command boundary. A
retained intent means publication may have been attempted, not that a command ran or succeeded.
On a handled failure leaving a serialized untouched suffix, the publisher writes an aborted
terminal record and immediately stops. Its artifact is usable only after independent checks
of the exact completed failed run/attempt, failed publishing step, successful later terminal
upload, record digest, and candidate/attempt binding. A crash without this terminal may remain
unrecoverable. A later verifier records its own execution without changing the
candidate source or each package's actual publishing identity. Controlled tests of these
operations are not genuine OIDC or public-registry release evidence.

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
checkout fallback, and reuse of FRED's dependency tree remain invalid. UI-only offline
consumption keeps the selected UI `file:` archive distinct from the exact published token
version in its prepared registry cache. The latter's lock entry must carry the ledger SHA-512,
approved registry URL, exact version, and no link or local fallback. A registry consumer has
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

Final `fixture-candidate-evidence` and companion `candidate-record.json` are written only after
all receiver gates pass. The companion record binds that same verified transfer, observed
application toolchain, and gate results; it joins the retained preparation artifact without
creating a publishing attempt or authorization. The evidence records the
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

`--select` accepts comma-separated stable inventory IDs; omission retains all-member
commands, while an explicit empty, duplicate, unknown, or private-root selection fails.
Ordering follows committed dependency/peer edges, so selected design tokens precede UI.
`iframeSdk` requires no token/UI candidate, React cache, or UI browser output. `designTokens`
creates only the token candidate. `ui` creates only the UI candidate and consumes the
separately provisioned exact prior token baseline. `designTokens,ui` validates both candidate
archives and the committed UI peer range together. The fourth-package fixture in
`fixtures/release-fourth-package.json` exercises generic selection, record, and registry
identity checks without registering a real producer member or granting a specialized archive
validator, consumer, or publication authority.

Network-capable provisioning remains separate from offline validation and browser execution:

```sh
# SDK-only: no React cache or token/UI prerequisite
make consumer-provision-iframe-sdk
make browser-install
make RELEASE_SELECTION=iframeSdk release-transfer-create
PLAYWRIGHT_BROWSERS_PATH=target/playwright make RELEASE_SELECTION=iframeSdk release-transfer-validate

# UI-only: prepare the pinned React cache, then independently recheck exact
# published token bytes and provenance. Neither step runs during validation.
make consumer-provision-react
make compatibility-provision
make browser-install
make RELEASE_SELECTION=ui release-transfer-create
PLAYWRIGHT_BROWSERS_PATH=target/playwright make RELEASE_SELECTION=ui release-transfer-validate
```

Provision the React cache before the compatible-token baseline. Re-running
`consumer-provision-react` replaces that cache and requires another
`compatibility-provision` before UI-only offline installation; otherwise the
missing exact registry response fails with an actionable cache-prerequisite error.

Approved evidence still requires the confirmed contract, clean source, actual packers, and
real application-toolchain gates. Controlled fixture tests demonstrate selection and transfer
but are not approved candidate evidence. The retained workflow now accepts explicit selected
package IDs; its default remains all-member preparation without publication.

Using the confirmed contract requires its exact producer toolchain and a clean source commit:

```sh
PLAYWRIGHT_BROWSERS_PATH=target/playwright npm run release:candidate -- \
  --contract /absolute/path/to/confirmed-contract.json \
  --approved \
  --evidence /absolute/path/to/candidate-evidence.json \
  --record /absolute/path/to/candidate-record.json
```

With `--select designTokens`, `--select ui`, `--select iframeSdk`, or a comma-separated
combination, the command packs only those members once. Omission packs all members. It
validates those bytes and records the source commit, exact Node/npm versions, package
coordinates, filenames, sizes, and SHA-512 integrities. Later
publication must use those same bytes. Rebuilding or modifying an archive invalidates the
evidence and requires the complete candidate validation again.

Before reusing retained artifacts, run `npm run release:verify-evidence --` with the same
`--contract`, `--evidence`, selected `--design-tokens`/`--ui`/`--iframe-sdk` paths, and
`--select` when evidence is selected. It recomputes every archive integrity and rejects a
changed contract, filename, or byte sequence.

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
behavior are not a successful public-registry run. Selected verifier helpers distinguish
selected candidates from the reviewed compatibility-only token dependency and reject wrong
bytes or provenance. Ordinary retained verification now binds selected public results to
the exact prior candidate and publishing attempts while recording the verifier's own
execution. A selected fixture-only command still reports controlled tooling; the historical
all-member generic command remains available.

For each exact coordinate, the verifier checks registry metadata and downloaded archive SHA-512
against the approved candidate before installation. It then creates and validates a registry-only
lock graph, including every resolved FRED package in that graph, and runs `npm ci --ignore-scripts`
in the fresh disposable root. `npm audit signatures` runs only after `npm ls` and the installed
manifest/real-path checks prove that the exact package is a non-linked dependency inside that
root. A package-lock alone is insufficient, and a missing install or local/workspace/checkout
fallback fails closed.

`npm pack` requires package-wide metadata even after the verifier has accepted exact-version
metadata. The verifier therefore performs a separate bounded package-wide readiness check before
invoking npm. Only a package-wide HTTP 404 is retried; authentication, authorization, redirect,
malformed metadata, name/version drift, and integrity drift fail immediately. The exact-version
identity and candidate SHA-512 remain the authority, and no publication command is involved.

## Manual independent-release workflow

`.github/workflows/Publish-frontend-packages.yml` remains a manual `workflow_dispatch`
on committed `swift` only. `prepare-only` is the default: it authorizes the source and
selected IDs, builds and packs exactly that candidate set under Node `24.21.0` / npm
`11.19.0`, and transfers the archives to separately provisioned Node `22.13.0` / npm
`10.9.2` application-toolchain validation. Producer-wide unit and archive regressions remain
separate from the selected candidate file set.
The approved transfer constructor accepts only the canonical reviewed policy/manifests,
canonical producer root, clean-source input, actual packers, and matching reviewed member
changelogs; disposable roots or injected fixture packers cannot produce release-labeled transfers.
The receiver rechecks transfer identity, source commit, package coordinates, lengths, and
SHA-512 values before offline consumers, browser smoke, and production-host compatibility.
Preparation cannot publish, use a publishing environment or token, or request OIDC write
permission. `publish` creates fresh candidates or requires an explicit original candidate
reference for continuation, then waits for one protected `npm-publish` approval. Only that
job receives `id-token: write`; no bootstrap secret is referenced. It checks original
candidate bytes and reviewed source, uploads and reads back a bound attempt, reconciles
exact versions read-only, and uses `npm publish <retained tarball> --tag next --access public
--provenance` only for demonstrably absent versions. Selected tokens are verified before
UI. An OIDC rejection stops without token/login fallback. A publish command is never
automatically repeated. A matching version can be skipped only after exact bytes and
cryptographic provenance match a retained attempt; wrong or ambiguous evidence stops.

`verify` retrieves pinned retained candidate and attempt artifacts, then provisions its own
dependencies and Chromium before exact registry-only installation, npm installed-tree
signature auditing, Sigstore provenance, clean consumers, browser smoke, and SDK host
compatibility where applicable. It packs nothing, requests no OIDC write authority, and
does not enter `npm-publish`. The verifier's `GITHUB_SHA`, run, and attempt remain its own;
each package is checked against its actual prior publishing execution. It can run again
after candidate preparation from a different source commit: the current committed `swift`
controller and policy authorize the operation, while retained artifact metadata binds the
candidate's historical source and each attempt's actual publishing commit. No older policy
checkout can override a changed current policy. The reviewed token baseline remains
independent of its old CI ZIP; expiry of a selected candidate or attempt artifact blocks
continuation.

The five manual inputs are `operation` (`prepare-only`, `publish`, `verify`), `packages`
(comma-separated stable IDs; default `designTokens,ui,iframeSdk`), `candidate-ref` (blank
for fresh preparation/publication), `attempt-refs` (JSON array, default `[]`), and
`terminal-refs` (JSON array of aborted terminal references, default `[]`). A retained
reference is JSON with exactly `artifactId`, `runId`, `runAttempt`, `sourceCommit`, `zipSha256`
(64 lowercase hex characters), and `recordDigest` (`sha256-` SRI). Copy the exact candidate
reference from the successful preparation job's summary; do not substitute the current run
attempt or a mutable latest-run artifact. For a partial continuation, first wait for the
original publishing run to complete, inspect its actual failed `publish` job, and obtain the
exact attempt and terminal references from retained GitHub artifact IDs, ZIP SHA-256, record
digests, run/attempt, and source commit. Use `operation=publish`, the original `candidate-ref`,
the candidate's exact `packages` selection, **all** prior `attempt-refs`, and their matching
`terminal-refs`; a fresh protected approval is required. The publisher requires full committed
Git history to find each selected version's first exact reviewed changelog heading and
GitHub's independently observed merge time for its merged `swift` pull request. It uses
the earliest of that time and the introduction commit's author/committer times as the
history lower bound, so a skewed commit clock cannot hide an earlier publication. The
protected job needs `pull-requests: read` for that lookup. From this reviewed boundary it
enumerates retained attempts **and** attempt-specific workflow
jobs, rejects omitted/deleted/expired/mismatched history, and refuses a fresh candidate that
reuses any earlier attempted coordinate. An older unrelated release outside the selected
version's reviewed window does not block a new version; a history query at GitHub's result
cap fails closed. It validates each terminal against the exact completed failed run and
job step boundary. The source-reviewed known-published ledger also reserves the three
historical alpha.1 coordinates, cross-checked against this runbook's immutable first-release
appendix; a temporary 404 cannot turn them into new publication candidates. A package's exact registry bytes and provenance must match its historical
retained intent before it is skipped. A missing later package may continue only when **every**
relevant prior attempt has a verified terminal proving it was untouched. A 404, missing
terminal, pending/cancelled run, failed upload, or absent outcome alone never proves
non-execution. If npm accepted a command but its outcome was lost, matching cryptographic
registry evidence can reconstruct success without a second publish. If reads remain
inconclusive, stop; never retry a possibly invoked command. A process crash before terminal
persistence/upload may require a new reviewed version. For independent verification, use
`operation=verify`, the original candidate reference, and the
publishing-attempt references; verification never creates a new candidate. A changed ZIP,
expired candidate/attempt/terminal, or unresolved partial outcome requires review, not archive rebuild
or npm version overwrite.

The workflow requests `retention-days: 30` on candidate, attempt, terminal, outcome, and final
verification artifacts. GitHub's read-only API reported a 30-day expiry on the completed
historical verification artifact (created `2026-09-14T20:03:00Z`, expires
`2026-10-14T20:02:59Z`). Repository/organization retention settings and future artifact
API expiries are not a committed guarantee: check each selected artifact's actual
`expires_at` before relying on it. The durable prior-token compatibility ledger is
source-reviewed and independent of its historical CI ZIP; a selected publication retry is not.

The generic `npm run registry:verify --` command remains available for an independently
approved evidence set. It requires explicit exact registry coordinates, the confirmed contract,
candidate evidence, installed-tree signature auditing, Sigstore verification, and clean registry
consumers, but produces tooling evidence rather than a genuine publication success record
without retained actual publishing attempts. It is not a continuation of the completed incident
and accepts no recovery or verification-plan options. Ordinary direct OIDC publication
code is prepared but not proof of package trust settings. Before a real new-version
dispatch, maintainers review the
version/changelog PR and each selected package's npm Trusted Publisher binding to
`ThalesGroup/fred`, the exact workflow filename, `npm-publish` environment, and permission
for direct `npm publish` (not merely staged publication). This must be reviewed in npm
settings; credential-free CI cannot inspect it. `npm whoami`, a dry run, or policy validation
is not OIDC authorization evidence. Initial creation of a future fourth package still
requires separate authority before its trust binding exists. After a partial failure,
retain original candidate/attempt/terminal references, reconcile exact versions read-only,
obtain fresh protected approval, and publish only missing versions whose non-execution is
demonstrable from a verified completed terminal boundary. A 404 after an attempt is ambiguous,
not proof of absence. If those bytes or attempts expire, require a new reviewed version and
fresh validation. Rollback of
an adopted application uses its prior image/lockfile; published npm versions are not
overwritten or silently unpublished.

## Maintainer decisions and sequencing

The existing confirmed release policy names organization `fred-oss`, scope `@fred-oss`,
the public npm registry, `next` tag, source branch/workflow/environment,
bootstrap account `marc.fawaz`, named package API / SDK protocol / release / enduring
publishing owners, and direct Trusted Publishing as the selected subsequent policy.
The committed member manifests supply their current `0.1.0-alpha.1` coordinates;
historical publication facts remain in the evidence appendix and compatibility ledger.
The distinct required GitHub reviewer is `marcfawaz`. This slice changes no published
coordinates and neither installs a Trusted Publisher nor establishes bootstrap-token
revocation. Predecessor OpenSpec task 12.7 therefore remains open.

Future releases must preserve dependency order (design tokens before UI), validate exact
archive bytes and provenance, and stop on ambiguous or partial failures without overwriting
published versions. FRED registry adoption and RAGS migration are separate changes.

## Completed first-release evidence (historical, not active configuration)

The first three public versions were published by separate, committed `swift` runs. The
validated original candidate belongs to source
[`f49f2439d54b44f7739c5bd7fca3f789e0e528d6`](https://github.com/ThalesGroup/fred/commit/f49f2439d54b44f7739c5bd7fca3f789e0e528d6),
[run `34853407387`, attempt `1`](https://github.com/ThalesGroup/fred/actions/runs/34853407387),
and [artifact `10352121632`](https://api.github.com/repos/ThalesGroup/fred/actions/artifacts/10352121632) (ZIP SHA-256
`25fe6a65498d7109b8ec5a2b6d43de24fa9b9d161376ab80f2416c82ac328b82`). Design
tokens were published in that run. UI and iframe SDK were published without replacing the
original candidate bytes from source
[`a1fedc661c9ec1846b5333aa4e546af0f0810033`](https://github.com/ThalesGroup/fred/commit/a1fedc661c9ec1846b5333aa4e546af0f0810033),
[recovery run `34882883783`, attempt `1`](https://github.com/ThalesGroup/fred/actions/runs/34882883783),
and [recovery artifact `10363547296`](https://api.github.com/repos/ThalesGroup/fred/actions/artifacts/10363547296) (ZIP SHA-256
`fe008c951be747cc496e9c82adf4f54f8ecd4d5c8c8bdbbf9dbda1d2a34e86b8`). The
original evidence and the package archives remain immutable; these GitHub artifacts have
retention limits and source links are not replacement archive bytes.

| Published coordinate                    | Candidate SHA-512                                                                                 | Attested publication source                |
| --------------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| `@fred-oss/design-tokens@0.1.0-alpha.1` | `sha512-+3UeYRe4Qhgtx+U1T/QQqu9172N+7c+DbuSo8G/2mvp5nbrjgLJj1VDdcOv4AYsuaYEvpNzERHo7Z6GTFNenqw==` | `f49f2439d54b44f7739c5bd7fca3f789e0e528d6` |
| `@fred-oss/ui@0.1.0-alpha.1`            | `sha512-+BmE1ASoIDN8HYDugYCd8gzykHcspH7LxQuM5m4HjQWMoVErR99L1OU+bcp2ICN1AkvUoOwfNbtpU9eFp5ln8A==` | `a1fedc661c9ec1846b5333aa4e546af0f0810033` |
| `@fred-oss/iframe-sdk@0.1.0-alpha.1`    | `sha512-FG0y07SN6I+iNzKxJGMC1RYeJeGHCitbRBob7jr7iGMW5AcMt1pfoIJm//UK/cMq0E1QC2sE+hWpF2VsPwsz6w==` | `a1fedc661c9ec1846b5333aa4e546af0f0810033` |

Each package's provenance names repository `https://github.com/ThalesGroup/fred` and
workflow `https://github.com/ThalesGroup/fred/.github/workflows/Publish-frontend-packages.yml@refs/heads/swift`.
A distinct [read-only verification run `34890367123`, attempt `1`](https://github.com/ThalesGroup/fred/actions/runs/34890367123)
from source
[`97920a0ad2df4ec90829819c9174fee4dc798d17`](https://github.com/ThalesGroup/fred/commit/97920a0ad2df4ec90829819c9174fee4dc798d17)
retained [artifact `10365859307`](https://api.github.com/repos/ThalesGroup/fred/actions/artifacts/10365859307), named
`frontend-packages-public-registry-verification-97920a0ad2df4ec90829819c9174fee4dc798d17-34890367123-1`.
GitHub's API digest and the downloaded ZIP SHA-256 both equal
`9d3ba17c4016fd194c64527cb10f95d6c711e5963a37b7cf95386d23620981b4`;
the ZIP contains only `final-evidence.json` and expires on `2026-10-14` unless separately
retained. That evidence records all six successful gates: exact registry archives, npm
signatures, Sigstore provenance, clean registry consumers, browser smoke, and production-host
compatibility. It keeps the historical publishing commits separate from the verifier's actual
commit/run/attempt. It does not establish subsequent Trusted Publisher configuration or
bootstrap-token revocation; predecessor OpenSpec task 12.7 remains open.

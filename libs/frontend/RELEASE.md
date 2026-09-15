# Frontend package release readiness

The first `@fred-oss/design-tokens`, `@fred-oss/ui`, and `@fred-oss/iframe-sdk`
`0.1.0-alpha.1` versions are published on public npm under the `next` tag. Genuine
all-package registry verification completed in a separate read-only run. The retained manual
workflow is preparation-only and has no publishing or incident-continuation operation.

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
independent UI release must still recheck the exact registry bytes and cryptographic
provenance before using this compatibility-only dependency; that execution belongs to the
next migration slice, not to a fixture test.

`release/release-record.schema.json` and `scripts/release-record.mjs` define separate candidate,
publishing-attempt, publication-outcome, and verification record models. Current all-member
`release:candidate` preparation reuses its already validated evidence/bytes to emit a companion
record with selection, policy/baseline digests, source identity, observed toolchains, archive
metadata, peer ranges, and gates. Fixture/incomplete records, unpersisted attempt models, and
controlled verification models cannot authorize publication or claim public registry success.
The attempt model is provisional and carries no persisted candidate-artifact origin yet;
task 3.4 will bind and read back that artifact and the actual OIDC execution before it can be
used as a pre-command publication contract.
Selected-only packing, durable attempt upload/readback, OIDC publishing, and workflow publish/
verify paths are later work; the retained workflow remains preparation-only.

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

Using the confirmed contract requires its exact producer toolchain and a clean source commit:

```sh
npm run release:candidate -- --contract /absolute/path/to/confirmed-contract.json \
  --approved \
  --evidence /absolute/path/to/candidate-evidence.json \
  --record /absolute/path/to/candidate-record.json
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

`npm pack` requires package-wide metadata even after the verifier has accepted exact-version
metadata. The verifier therefore performs a separate bounded package-wide readiness check before
invoking npm. Only a package-wide HTTP 404 is retried; authentication, authorization, redirect,
malformed metadata, name/version drift, and integrity drift fail immediately. The exact-version
identity and candidate SHA-512 remain the authority, and no publication command is involved.

## Retained preparation workflow

`.github/workflows/Publish-frontend-packages.yml` remains a manual `workflow_dispatch`
on committed `swift` only. Its sole `prepare-only` operation authorizes the source,
builds and packs one candidate set under Node `24.21.0` / npm `11.19.0`, and transfers
the exact archives to the separately provisioned application-toolchain validation job.
The approved transfer constructor accepts only the canonical reviewed policy/manifests,
canonical producer root, clean-source input, actual packers, and matching reviewed member
changelogs; disposable roots or injected fixture packers cannot produce release-labeled transfers.
The receiver rechecks transfer identity, source commit, package coordinates, lengths, and
SHA-512 values before offline consumers, browser smoke, and production-host compatibility.
Preparation cannot publish, use a publishing environment or token, or request OIDC write
permission. No workflow input can activate the retired bootstrap, recovery, or retained-artifact
verification paths.

The generic `npm run registry:verify --` command remains available for an independently
approved evidence set. It requires explicit exact registry coordinates, the confirmed contract,
candidate evidence, installed-tree signature auditing, Sigstore verification, and clean registry
consumers. It is not a continuation of the completed incident and accepts no recovery or
verification-plan options. A later workflow for independent releases or OIDC publishing must be
reviewed as a separate change.

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

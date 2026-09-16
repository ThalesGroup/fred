# Local implementation verification (2026-09-16)

This is local compatibility and package evidence for issue #2712, not a release
candidate or public-registry verification of the context extension. At that
verification, the working tree was uncommitted and the generated SDK archive
still carried the development manifest's `0.1.0-alpha.1` version. Its bytes
differed from the immutable published `0.1.0-alpha.1`; it must never be
published under that coordinate.

## Exact inputs and provenance

- Pre-extension host: commit `4a69a0229163cd354cdf36f62ca7e213aeaeebaf`.
  `git archive` extracted `apps/frontend` to a disposable checkout. Its
  `TeamApplicationHostPage.tsx` SHA-256 is
  `7a6b2f8c082df78a29443aba6f9da43453c4f0aeac6d97dde2c9b8a314547c2c`,
  equal to `git show` of that commit. The application lockfile and manifest
  SHA-256 also match the current checkout, but the historical checkout received
  its own `npm ci --offline --ignore-scripts`. Only its disposable integration
  test was augmented to assert that old-host context leaves theme absent; its
  host source was not edited.
- Published SDK: the actual npm archive for
  `@fred-oss/iframe-sdk@0.1.0-alpha.1`, downloaded with `npm pack` from
  `https://registry.npmjs.org/`, has SHA-512 integrity
  `sha512-FG0y07SN6I+iNzKxJGMC1RYeJeGHCitbRBob7jr7iGMW5AcMt1pfoIJm//UK/cMq0E1QC2sE+hWpF2VsPwsz6w==`
  and SHA-1 shasum `7c01f6fb3a5e10276c36fc6386250cf70b79fc4d`.
  Exact-version npm metadata and the independently committed
  `known-published-coordinates.json` agree. `npm audit signatures` on a
  disposable installed exact-version tree reported one verified registry
  signature and one verified attestation. The repository's
  `verifyNpmPackageProvenance` cryptographically verified the Sigstore bundle;
  the signed statement's archive digest, repository
  `https://github.com/ThalesGroup/fred`, source commit
  `a1fedc661c9ec1846b5333aa4e546af0f0810033`, workflow
  `https://github.com/ThalesGroup/fred/.github/workflows/Publish-frontend-packages.yml@refs/heads/swift`,
  invocation repository, run `34882883783`, and attempt `1` matched explicit
  expected values. Metadata integrity alone was not treated as provenance.
- New SDK: `make pack-check` produced and validated the actual local archive,
  SHA-512 integrity
  `sha512-fNbSpX1uChVdelbLIlPyVZzRAvIHwPssZUe/ua/VSMkxgFUXjovoFQ+D//oIp7AkJERXuX2V5zEcfbOes/3xGQ==`.
  The canonical protocol source SHA-256 recorded by the archive validator is
  `0681eadf8db2631094f9ba08b05fbbb50b5c47599a7ba2631ebd7b6295356a67`.
  This archive is fixture/build evidence only, not approved release evidence.

## Four-way protocol-`"1"` matrix

All runs used the real production host component in the named checkout and
the actual SDK archive's `dist/index.js`, never a hand-written client mock.
`FRED_IFRAME_SDK_ENTRY_URL=<archive-derived entry> node_modules/.bin/vitest run
src/rework/components/pages/TeamApplicationHostPage/TeamApplicationHostPage.sdk-integration.test.tsx`
was run with Node 22.13.0/npm 10.9.2. The historical host tests ran inside
the disposable checkout; the extended host tests ran in this working tree at
HEAD `28aca673d685526a45e1c2f54d675e1db7dbe15f` plus this uncommitted diff.

| SDK archive                                     | Host source           | Command                                                                                                         | Result                                                                                                                                                                                                                                                            |
| ----------------------------------------------- | --------------------- | --------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Published alpha.1, integrity `sha512-FG0y07SN…` | Pinned `4a69a022…`    | `FRED_IFRAME_SDK_ENTRY_URL=$PUBLISHED_ENTRY node_modules/.bin/vitest run "$TEST_FILE"`                          | 4/4 passed: handshake, route/navigation/open-chat, HTTP/transport/bodyless/duplicate replies, capacity, frame/team replacement; absent theme asserted in the disposable test.                                                                                     |
| Published alpha.1, same integrity               | Extended working tree | `FRED_IFRAME_SDK_ENTRY_URL=$PUBLISHED_ENTRY FRED_IFRAME_SDK_LEGACY=1 node_modules/.bin/vitest run "$TEST_FILE"` | 5/5 passed (live-API-only tests skipped): optional initial theme and repeated theme/locale contexts leave the old client connected; route, request, navigation, open-chat, and lifecycle remain functional. The old client is not claimed to expose live context. |
| New packed SDK, integrity `sha512-fNbSpX1…`     | Pinned `4a69a022…`    | `FRED_IFRAME_SDK_ENTRY_URL=$LOCAL_ENTRY node_modules/.bin/vitest run "$TEST_FILE"`                              | 4/4 passed: old-host context omits theme without fabricated fallback; handshake and existing behavior remain functional.                                                                                                                                          |
| New packed SDK, same integrity                  | Extended working tree | `make host-integration` in `libs/frontend` with application Node/npm                                            | 7/7 passed: initial light and dark, both theme directions, locale changes, route/request/navigation/open-chat, capacity, and frame/team replacement.                                                                                                              |

For the three direct Vitest commands above, the recorded local values were:

```sh
PUBLISHED_ENTRY=/private/tmp/fred-sdk-baseline.uYVeFa/installed/node_modules/@fred-oss/iframe-sdk/dist/index.js
LOCAL_ENTRY=/private/tmp/fred-host-4a69a022.4cL9GT/apps/frontend/node_modules/@fred-oss/iframe-sdk-current/dist/index.js
TEST_FILE=src/rework/components/pages/TeamApplicationHostPage/TeamApplicationHostPage.sdk-integration.test.tsx
```

The historical commands ran from `/private/tmp/fred-host-4a69a022.4cL9GT/apps/frontend`;
the extended-host commands ran from the repository's `apps/frontend`. Both used the
application's pinned Node/npm. The local SDK entry was copied only into the
disposable historical checkout from the validated local tarball to make Vite's
module resolver load it; the production host source remains the pinned file.

The installed-tarball neutral consumer type-check/build, SDK unit and host
tests, and three-origin browser smoke cover later repeated and malformed
contexts, wrong origin/source/application identity, unsupported protocol,
listener exception isolation/unsubscribe, and old-frame disposal. The child
query includes conflicting `?theme=dark&locale=fr`; accepted host context
remains authoritative. A replacement frame receives an initially dark
context across the distinct origins, separately from the initially light
first frame. Browser evidence reported zero external requests,
zero dependency installations, zero browser provisioning, and successful HTTP
responses for every request.

**Decision:** all supported combinations passed. Protocol `"1"` is retainable
for this additive extension. This is not a version-selection, publication, or
consumer-adoption decision.

## Gates

Producer Node 24.21.0/npm 11.19.0; application Node 22.13.0/npm 10.9.2.
Dependency caches and Chromium were provisioned before offline checks.

| Command                                                              | Result                                                                                                                         |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `make code-quality` in `libs/frontend`                               | Passed.                                                                                                                        |
| `make test` in `libs/frontend`                                       | 376/376 passed, including loopback metadata tests and comment-decoy archive negatives.                                         |
| `make release-check` in `libs/frontend`                              | Passed.                                                                                                                        |
| `make release-test` in `libs/frontend`                               | 153/153 passed.                                                                                                                |
| `make pack-check` in `libs/frontend`                                 | Token, UI, SDK archives validated.                                                                                             |
| `make isolated-consumer` in `libs/frontend`                          | Token, UI, SDK actual tarballs installed offline and built outside FRED.                                                       |
| `make browser-smoke` in `libs/frontend`                              | Passed token/UI/SDK local-only Chromium checks.                                                                                |
| `make host-integration` in `libs/frontend` with application Node/npm | 7/7 passed against the production host page.                                                                                   |
| `make code-quality`, `make build`, `make test` in `apps/frontend`    | Passed; application tests: 232 files passed, 2 skipped, 2420 tests passed, 9 skipped; proxy config 9/9 and proxy smoke passed. |

The independent cold review found two evidence gaps: initial-dark cross-origin
handshake coverage and comment-only markers bypassing archive API checks. Both
were corrected; the reviewer re-inspected the fixes and found no remaining
issue. The archive validator now follows the exported factory to its returned
client class and structurally checks declaration members, with three
comment-decoy negative tests. Strict OpenSpec validation and final diff checks
passed. The existing RFC remains open for release and adoption work.

## SDK-only source preparation (2026-09-16)

At `2026-09-16T18:46:53Z`, from source commit
`54814439292119a78132087bd74b35387a53deff`, the public
`https://registry.npmjs.org/` version set for `@fred-oss/iframe-sdk` contained
only `0.1.0-alpha.1` (`next` and `latest` both pointed to it). An exact
`0.1.0-alpha.1` lookup returned its expected name, version, and SHA-512; an
exact `0.1.0-alpha.2` lookup returned npm `E404` / “No match found for version”.
The source-reviewed `known-published-coordinates.json` also records only SDK
alpha.1. The source-preparation coordinate is therefore `0.1.0-alpha.2`.
These checks used the pinned Node 24.21.0/npm 11.19.0 and explicit registry:

```sh
npm view @fred-oss/iframe-sdk versions dist-tags --json --registry=https://registry.npmjs.org/ --prefer-online --fetch-retries=0 --fetch-timeout=15000
npm view @fred-oss/iframe-sdk@0.1.0-alpha.1 name version dist.integrity --json --registry=https://registry.npmjs.org/ --prefer-online --fetch-retries=0 --fetch-timeout=15000
npm view @fred-oss/iframe-sdk@0.1.0-alpha.2 name version dist.integrity --json --registry=https://registry.npmjs.org/ --prefer-online --fetch-retries=0 --fetch-timeout=15000
```

This registry observation reserves nothing. Recheck the exact coordinate after
the source PR merges and immediately before approved candidate preparation.
This source-preparation branch cannot satisfy the committed-`swift`
candidate boundary; task 6.2 remains unchecked until the changes are merged
and immutable approved candidate evidence is prepared from clean committed
`swift`. Task 6.3 remains a separately authorized publication and
genuine registry-verification operation.

### Source-reviewable validation

The SDK-only manifest and npm-generated producer lockfile now name
`@fred-oss/iframe-sdk@0.1.0-alpha.2`. The lockfile diff changes only the
`iframe-sdk` workspace version. Design tokens remain `0.1.0-alpha.1` and UI
remains `0.1.0-alpha.2`; their manifests, changelogs, and exports were not
changed. The SDK changelog has one reviewed alpha.2 entry. The packed README
describes `onContext` as included in this package version without claiming
publication, workspace adoption, or registry verification.

The final local `make pack-check` archive is
`fred-oss-iframe-sdk-0.1.0-alpha.2.tgz`, SHA-512
`sha512-c2v0kFOCDtxecXONgWLqX3PqNQmXgw4Whd06QJU1tudSUSIRUeTwB6XTZdPZlpzUBVoFxx6Qeu4LPENAvmUhZw==`.
Archive inspection confirmed the unchanged `.` and `./protocol` export paths,
`onContext` in the public declaration, optional resolved `theme`, protocol
`"1"`, and no runtime or peer dependency added. This digest identifies only
local validation bytes; it is not approved immutable candidate evidence.

| Command and toolchain                                                 | Local result                                                                                                                                                                                                  |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `make release-check`, Node 24.21.0/npm 11.19.0                        | Passed; confirmed policy, manifests, changelog, private workspace, and dependency boundaries.                                                                                                                 |
| `make release-test`, Node 24.21.0/npm 11.19.0                         | 153/153 passed; loopback metadata tests required authorized local-network execution. Version-sensitive controlled fixtures now derive their expected coordinate rather than assuming the live SDK is alpha.1. |
| `make test`, Node 24.21.0/npm 11.19.0                                 | 376/376 passed after updating current-archive and consumer assertions to read the manifest.                                                                                                                   |
| `make pack-check`, Node 24.21.0/npm 11.19.0                           | Token alpha.1, UI alpha.2, and SDK alpha.2 archives passed package-specific checks.                                                                                                                           |
| `npm run test:consumer:iframe-sdk`, Node 22.13.0/npm 10.9.2           | Passed: actual alpha.2 tarball installed from the prepared cache in npm offline mode, type-checked, and built outside FRED.                                                                                   |
| `make host-integration`, Node 22.13.0/npm 10.9.2                      | 7/7 passed against the production host and actual alpha.2 tarball.                                                                                                                                            |
| `npm run test:browser -- --select iframeSdk`, Node 22.13.0/npm 10.9.2 | Passed with pre-provisioned Chromium, three distinct loopback origins, no dependency installation, no browser provisioning, and zero external requests.                                                       |
| `make code-quality`, Node 24.21.0/npm 11.19.0                         | Passed ESLint and Prettier.                                                                                                                                                                                   |

The approved `release:candidate` path rejects a dirty checkout, and the
manual `prepare-only` workflow authorizes committed `swift` only. At this
earlier source-preparation point, no approved candidate, registry-success
record, workflow run, or publication had been created. The later alpha.2
candidate and attempted publication are recorded below; the former alpha.2
dispatch guidance is no longer applicable.

## Alpha.2 publication failure and alpha.3 source recovery (2026-09-16)

The preceding alpha.2 source-preparation guidance is historical, not a current
instruction to dispatch an alpha.2 release. Approved alpha.2 candidate
preparation subsequently succeeded from committed source
`ec6a356e9f7bc462848d9bd1886507b73f08598f`: run `35141553419`, attempt
`1`, artifact `10465890332`, ZIP SHA-256
`be20a244a10420fdbc26f7a1424c860113da4339b6c15936eb62f10239c7ce70`,
record digest `sha256-9zdyAUosx7VvL0b3o0zo7f1xqxdp9qlqgHX1mjJhDbw=`, and
`@fred-oss/iframe-sdk@0.1.0-alpha.2` archive SHA-512
`sha512-c2v0kFOCDtxecXONgWLqX3PqNQmXgw4Whd06QJU1tudSUSIRUeTwB6XTZdPZlpzUBVoFxx6Qeu4LPENAvmUhZw==`.
This supplied immutable candidate evidence establishes the candidate-preparation
portion of task 6.2 for alpha.2, not publication or completion of the alpha.3 task.

The protected publication run `35142891059`, attempt `1`, retained attempt
artifact `10466181656` (ZIP SHA-256
`19ee51faf0b79c31b9c14e6583401844c47102e385019ca402d48d05bc1ed555`,
record digest `sha256-Vv0pZn2uBu9b8LvpMoFOu5DmQWJU93ZWg36C4coQH5g=`).
It reached the actual `npm publish` command for the alpha.2 archive, which
failed with `ENEEDAUTH`. No publication outcome or `publishing-terminal.json`
was retained, and public-registry verification was skipped. A missing terminal
cannot prove non-invocation: alpha.2 must not be retried as though untouched,
treated as published, or added to `known-published-coordinates.json`. The
operator subsequently recreated the iframe SDK Trusted Publisher connection;
this is external configuration context, not a setting changed or verified here.

At `2026-09-16 20:07 UTC`, with this branch at
`ec6a356e9f7bc462848d9bd1886507b73f08598f`, read-only public npm checks
under Node `24.21.0` / npm `11.19.0` used these exact commands:

```sh
npm view @fred-oss/iframe-sdk versions dist-tags --json --registry=https://registry.npmjs.org/ --prefer-online --fetch-retries=0 --fetch-timeout=15000
npm view @fred-oss/iframe-sdk@0.1.0-alpha.2 name version dist.integrity --json --registry=https://registry.npmjs.org/ --prefer-online --fetch-retries=0 --fetch-timeout=15000
npm view @fred-oss/iframe-sdk@0.1.0-alpha.3 name version dist.integrity --json --registry=https://registry.npmjs.org/ --prefer-online --fetch-retries=0 --fetch-timeout=15000
```

The complete version set contained only `0.1.0-alpha.1`, with `next` and
`latest` pointing to alpha.1. Both exact alpha.2 and alpha.3 lookups returned
npm `E404` / “No match found for version”. The sandbox's first attempt could
not resolve the registry (`ENOTFOUND`); the recorded results are from the
authorized network-enabled retry. These observations reserve no version. The
source-recovery coordinate is `@fred-oss/iframe-sdk@0.1.0-alpha.3`; alpha.2
changelog and incident evidence remain intact.

The pinned npm lockfile regeneration changed only the `iframe-sdk` workspace
version from `0.1.0-alpha.2` to `0.1.0-alpha.3`. Design tokens remain
`0.1.0-alpha.1`, UI remains `0.1.0-alpha.2`; public SDK exports, dependencies,
canonical protocol source SHA-256
`0681eadf8db2631094f9ba08b05fbbb50b5c47599a7ba2631ebd7b6295356a67`,
and protocol `"1"` are unchanged. The local validated archive is
`fred-oss-iframe-sdk-0.1.0-alpha.3.tgz`, SHA-512
`sha512-RtGsASmlDCPw9i6QOzejU65c8baC+AM8Yi3kUuQ99fevhbXa3xIjyOhUiesraDpV2gPY4g1FobnJOEagSHEdkQ==`.
It contains the same `.` and `./protocol` runtime and declaration exports,
eight validated packed files, and no bundled dependencies. These are local
pack-check bytes, not approved immutable candidate evidence.

| Command in `libs/frontend` | Toolchain | Source-reviewable result |
| --- | --- | --- |
| `make release-check` | Node 24.21.0 / npm 11.19.0 | Passed. |
| `make release-test` | Node 24.21.0 / npm 11.19.0 | 153/153 passed with loopback fixture access; the initial sandbox run failed only on `listen EPERM 127.0.0.1`. |
| `make test` | Node 24.21.0 / npm 11.19.0 | 376/376 passed with loopback fixture access. |
| `make pack-check` | Node 24.21.0 / npm 11.19.0 | Design-token alpha.1, UI alpha.2, and SDK alpha.3 archives validated. |
| `npm run test:consumer:iframe-sdk` | Node 22.13.0 / npm 10.9.2 | Alpha.3 actual tarball installed from the prepared cache in npm offline mode, type-checked, and built outside FRED. |
| `make host-integration` | Node 22.13.0 / npm 10.9.2 | 7/7 passed against the production host and actual alpha.3 archive. |
| `PLAYWRIGHT_BROWSERS_PATH=target/playwright npm run test:browser -- --select iframeSdk` | Node 22.13.0 / npm 10.9.2 | Passed with pre-provisioned Chromium and distinct loopback origins; no dependency/browser provisioning during validation. |
| `make code-quality` | Node 24.21.0 / npm 11.19.0 | ESLint and Prettier passed. |

No release workflow was dispatched, no package was published, and no npm or
GitHub setting was changed in this source-preparation pass. Task 6.2 remains
unchecked until a fresh alpha.3 registry check and approved immutable candidate
evidence from clean committed `swift`; task 6.3 remains unchecked until separate
publication authority and genuine public-registry verification.

## Published alpha.3 close-out (2026-09-16)

The preceding unchecked-task and no-publication statements describe the earlier
source-preparation pass, not the final state. The SDK-only alpha.3 candidate was
subsequently prepared from clean committed `swift` source
`56b498c0e338606b00b50f33bfcdd6e02ee61693` in run `35147048936`, attempt
`1`. Candidate artifact `10466938820` has ZIP SHA-256
`1e1c8b8e03f32d76e187835e0a7db2be52cb80ee33fb380ed54ab97f7d5fb7bc`
and record digest `sha256-PmrhhDt8IHBXAr2hf8z3YQRZEx//oZYFzKyZz21z0Og=`.
Its `@fred-oss/iframe-sdk@0.1.0-alpha.3` tarball has SHA-512
`sha512-RtGsASmlDCPw9i6QOzejU65c8baC+AM8Yi3kUuQ99fevhbXa3xIjyOhUiesraDpV2gPY4g1FobnJOEagSHEdkQ==`.
The candidate record reports archive, offline neutral consumer, distinct-origin
browser, and production-host gates passed under the pinned separate toolchains.
This is approved immutable candidate evidence for task 6.2, not a local fixture.

Protected publication used a separate run `35147742170`, attempt `1`, with
retained attempt artifact `10466824522`, ZIP SHA-256
`0836b12d5b1709914f087586facc78ed3f54997adb0c74d0a4528a4aaba013a8`
and attempt digest `sha256-gmlkcY4Pjy0baONTa0AVM9wAr2ATxvA37FJzsHupP4A=`.
npm accepted the alpha.3 publish command into automated validation. The GitHub
publish job later failed after its six bounded exact-version visibility reads;
this was delayed registry metadata, not evidence of failed package publication.
It did not trigger a republish. The older alpha.2 `ENEEDAUTH` attempt remains
failed-at-authentication history and was never claimed as published.

Independent read-only verify-only run `35148411102`, attempt `1`, retained
artifact `10467986853`, ZIP SHA-256
`764d602a7b24eadbb5936dc91de82c0e8cf45b017d9de1f6ae79e75198cc493b`,
outcome digest `sha256-5sI1oUJNA8N+c/f27rVmldR8MdH1CAs+TjQcKyKH4Js=`.
The retained record reports readiness `registry-verified` and all six final
public gates true: exact registry archives, npm signatures, Sigstore
provenance, clean registry consumers, browser smoke, and production-host
compatibility. The verified public archive SHA-512 equals the candidate's.
Cryptographically verified provenance binds the artifact digest to repository
`https://github.com/ThalesGroup/fred`, source commit
`56b498c0e338606b00b50f33bfcdd6e02ee61693`, workflow
`https://github.com/ThalesGroup/fred/.github/workflows/Publish-frontend-packages.yml@refs/heads/swift`,
invocation repository `https://github.com/ThalesGroup/fred`, publishing run
`35147742170` attempt `1`, and issuer `https://token.actions.githubusercontent.com`.
The verifier's execution identity is separately run `35148411102` attempt `1`.

At close-out, read-only `npm view` under Node 24.21.0/npm 11.19.0 returned
exact alpha.3 name, version, and matching SHA-512 from
`https://registry.npmjs.org/`; the package version set was alpha.1 and
alpha.3, `next` was alpha.3, and `latest` was alpha.1. GitHub's read-only API
confirmed the three completed run/attempt/source identities and artifact
metadata; streaming the three ZIPs independently reproduced their SHA-256
digests. The downloaded candidate tarball independently reproduced the
recorded SHA-512. The final verification ZIP contained the retained
`registry-verification.json` with the above identities and gate results.
Tasks 6.2 and 6.3 are now evidenced; all 26 change tasks are complete.

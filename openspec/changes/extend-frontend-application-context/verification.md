# Local implementation verification (2026-09-16)

This is local compatibility and package evidence for issue #2712, not a release
candidate or public-registry verification of the context extension. The working
tree is uncommitted. The generated new SDK archive still carries the development
manifest's `0.1.0-alpha.1` version, but its bytes differ from the immutable
published `0.1.0-alpha.1`; it must never be published under that coordinate.

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

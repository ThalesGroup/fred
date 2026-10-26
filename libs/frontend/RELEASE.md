# Frontend npm releases

Release `@fred-oss/design-tokens`, `@fred-oss/ui`, and `@fred-oss/iframe-sdk` independently through the same commands locally and in CI. Each operation accepts exactly one `PACKAGE`: `design-tokens`, `ui`, or `iframe-sdk`.

The package manifest is authoritative for its npm name, version, exports, dependencies, and publish settings. Change a version and its changelog in a reviewed source change; release commands never bump versions.

## Prerequisites

- A clean committed checkout. Preparation records `HEAD` and rejects uncommitted or untracked source so the metadata cannot misidentify its source.
- Node `24.21.0` and npm `11.19.0` for release preparation.
- Producer dependencies: `npm ci` in `libs/frontend`.
- Chromium: `make browser-install`.
- For UI: `make consumer-provision-react`. Preparation also verifies that an exact published `@fred-oss/design-tokens` version satisfies UI's declared peer range and places it in the isolated-consumer cache.
- For iframe-sdk: `make consumer-provision-iframe-sdk` and `npm ci` in `apps/frontend` for the production-host compatibility check.
- Registry access to `https://registry.npmjs.org/`.

Local publication and promotion use the operator's normal npm configuration. Run `npm login` if the account is not already authenticated; npm may request interactive authorization or 2FA.

## Prepare one package

From a fresh clone:

```sh
cd libs/frontend
npm ci
make browser-install

# Package-specific prerequisite:
make consumer-provision-iframe-sdk
npm --prefix ../../apps/frontend ci

make prepare-release PACKAGE=iframe-sdk
```

Preparation builds only the selected package, validates its archive, runs the applicable isolated consumer, browser, and production-host checks, and writes:

```text
target/releases/iframe-sdk/<manifest-version>/
  fred-oss-iframe-sdk-<manifest-version>.tgz
  release.json
```

`release.json` is generated. It binds the stable package selector, npm name, manifest version, source commit, archive filename, SHA-512 integrity, and whether preparation ran locally or in GitHub Actions. Operators do not edit it or provide hashes.

Use an explicit portable directory when another environment will publish the bytes:

```sh
make prepare-release PACKAGE=iframe-sdk RELEASE_DIR=/absolute/path/to/iframe-sdk-release
```

The destination must be empty. Transfer the complete directory unchanged.
The receiving checkout must still expose the same package name and version. UI dependency
validation reads the peer range packed into the prepared tarball, not a later working-tree
edit. GitHub CI checks out the recorded source commit, but OIDC publication additionally
requires the workflow itself to have been dispatched from that same commit.

Equivalent preparation commands are:

```sh
make prepare-release PACKAGE=design-tokens
make prepare-release PACKAGE=ui
make prepare-release PACKAGE=iframe-sdk
```

UI preparation stops with `publish design-tokens first` only when no exact published token version satisfies the peer range in `ui/package.json`. iframe-sdk never requires UI or tokens.

## Publication dry run

Always validate a transferred directory before a real upload:

```sh
make publish PACKAGE=iframe-sdk DRY_RUN=1
make publish PACKAGE=iframe-sdk RELEASE_DIR=/absolute/path/to/iframe-sdk-release DRY_RUN=1
```

The dry run validates metadata, packed manifest identity, checksum, UI dependencies where applicable, and exact registry state. It never invokes `npm publish` or changes a distribution tag. If the version already exists with matching integrity it reports `already-published`; different bytes are a conflict.

## Publish prepared bytes

Local publication defaults to `next`:

```sh
make publish PACKAGE=iframe-sdk
make publish PACKAGE=iframe-sdk RELEASE_DIR=/absolute/path/to/iframe-sdk-release
```

The command:

1. Validates the generated metadata and exact tarball again.
2. Reads the exact registry version.
3. Returns success without uploading if matching bytes already exist.
4. Stops if the version exists with different bytes.
5. Invokes npm once, with `--ignore-scripts`, only after a definite 404.
6. Performs bounded read-only visibility checks after npm accepts the upload.

Publication never rebuilds or silently prepares. Package lifecycle scripts are disabled. Local mode does not request CI provenance.
It explicitly disables any manifest-level provenance default and inherits the terminal,
so npm login, web authorization, or OTP prompts remain interactive.

An ambiguous npm failure or exhausted post-upload 404s produces `publish-result.json` with state `uncertain` and prints the exact `make verify-release` command. Do not publish again based on a temporary 404.

## Verify and promote

Verification is read-only and compares the registry's exact version integrity with the prepared tarball:

```sh
make verify-release PACKAGE=iframe-sdk
make verify-release PACKAGE=iframe-sdk RELEASE_DIR=/absolute/path/to/iframe-sdk-release
```

Promotion is a separate mutation. It verifies that the requested exact version exists before moving a tag:

```sh
make promote PACKAGE=iframe-sdk VERSION=0.1.1-alpha.1 CHANNEL=latest DRY_RUN=1
make promote PACKAGE=iframe-sdk VERSION=0.1.1-alpha.1 CHANNEL=latest
```

Promotion never prepares or publishes an archive.

## Authentication and provenance

`AUTH_MODE` is explicit:

| Mode              | Use                         | Requirement                                                              | Provenance    |
| ----------------- | --------------------------- | ------------------------------------------------------------------------ | ------------- |
| `local` (default) | Developer terminal          | Normal npm login/configuration; CI is rejected                           | Not requested |
| `token`           | CI publication or promotion | `CI=true` and `NODE_AUTH_TOKEN`                                          | Not requested |
| `oidc`            | GitHub Actions publication  | GitHub OIDC environment and prepared GitHub source matching `GITHUB_SHA` | Requested     |

Examples:

```sh
CI=true NODE_AUTH_TOKEN=... make publish PACKAGE=iframe-sdk AUTH_MODE=token
CI=true NODE_AUTH_TOKEN=... make promote PACKAGE=iframe-sdk VERSION=0.1.1-alpha.1 CHANNEL=latest AUTH_MODE=token
```

OIDC mode refuses a directory prepared locally and requires the prepared source commit,
the publishing checkout, and GitHub's original `GITHUB_SHA` to be identical. The command
never rewrites GitHub identity variables to manufacture provenance. Separate preparation
and publication runs remain supported when both runs start from the same source commit.

If `swift` advances after preparation, a later GitHub OIDC run cannot truthfully publish
that older archive. Download the complete unchanged release directory, verify it, and use
explicit local authentication, or an explicitly configured token-mode CI job, to publish
the same bytes without CI provenance. Do not rebuild, edit the metadata, or silently fall
back from OIDC.

Authentication modes never silently fall back.
Token mode generates a temporary registry-scoped npm configuration and removes it after
the mutation. OIDC uses an isolated token-free npm configuration. Local, token, and OIDC
credentials cannot be mixed; select the mode that owns the credential explicitly.

## GitHub Actions adapter

`.github/workflows/Publish-frontend-packages.yml` keeps the existing filename for npm Trusted Publisher configuration. Its manual inputs are:

- `operation`: `prepare`, `publish`, `verify`, or `promote`;
- `package`: one stable package selector;
- optional `prepared-run-id` for a prior run containing that package's prepared directory;
- `version` and `channel` for promotion;
- `dry-run` for non-mutating publication or promotion validation.

The workflow keeps GitHub artifact upload/download and run selection in the adapter. For
the one selected run, it performs a bounded GitHub API lookup and verifies the actual
repository, workflow path, `swift` source branch, and head commit before binding those
values to `release.json`. It does not require the selected run to be complete or successful.
No candidate, attempt, terminal, checksum, or JSON input is accepted. Shared scripts call
no GitHub API, so GitLab CI can transfer the directory and invoke the same Make commands.

Promotion values are passed as environment data and validated before either the dry-run or
credentialed job reaches Make. The Make target preserves them as opaque values before the
shared command performs its exact semantic-version and distribution-tag checks.

Only the protected `npm-publish` publication job receives `id-token: write`. Publication and promotion serialize per package. Real promotion uses a protected `NPM_TOKEN` because npm distribution-tag changes are not the Trusted Publisher upload operation. Promotion dry runs run in a separate credential-free job. Preparation and verification receive no publishing credential.

Before enabling CI mutation, maintainers must confirm:

- the `npm-publish` GitHub environment and reviewers;
- the existing packages' Trusted Publisher relationship to `ThalesGroup/fred`, this workflow filename, and the environment;
- a protected `NPM_TOKEN` for CI promotion if CI promotion is desired.

## Failures and rollback

- `version-conflict`: the immutable registry version contains different bytes. Choose a new version; never overwrite it.
- `registry-authentication` / `registry-authorization`: fix credentials or package permissions. These are not absence.
- `registry-network` / `registry-timeout`: retry read-only verification when connectivity returns.
- `publication-uncertain`: run the printed verification command. Do not issue another upload until exact registry state is known.
- UI dependency unavailable: publish a compatible design-token version first or revise UI's peer range in reviewed source.

Rollback never replaces npm bytes. Deprecate or supersede a bad version, move a distribution tag back to a previously verified version, and restore consumer lockfiles or application images as appropriate.

## Historical releases

The already published versions remain historical and are not republished or retroactively given provenance by this process:

- `@fred-oss/design-tokens@0.1.1-alpha.0`
- `@fred-oss/ui@0.1.1-alpha.0`
- `@fred-oss/iframe-sdk@0.1.1-alpha.1`

The #3278 recovery machinery is not part of routine releases. Historical GitHub artifacts and prior npm versions remain unchanged.

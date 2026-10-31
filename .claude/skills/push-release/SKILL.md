---
name: push-release
description: Prepare a reviewable Fred release PR, validate versions and operator notes, then publish paired code/chart tags only when explicitly authorized. Resolve the current release branch instead of assuming Swift.
---

# Prepare and publish a Fred release

Read `AGENTS.md`, `deploy/release-notes/README.md`, the root release Make targets
and current CI workflows. Preserve this operational release-note workflow; it is
not the retired RFC or architecture documentation process. A request to prepare a
release authorizes preparing its release PR, not release tags or PyPI publication.
Existing explicit authorization for a precise publication remains valid.

## Establish the release

Inspect branch, status and selected remote. Resolve the intended release branch
from the user and current workflow, asking only if it remains ambiguous. Fetch its
ref and tags when possible. Use a suitable topic branch/worktree and preserve
unrelated work. Never commit preparation directly to the release branch or tag a
preparation branch.

Run `make release-plan` and use its ancestry-based baseline, maximum impact and
minimum eligible version; never choose the largest repository-wide tag. No new
commits means nothing to release. Resolve missing declarations with accurate
in-range notes. A historical coverage review must actually inspect the reported
range; do not invent acknowledgements to bypass it.

Inspect commit bodies, affected code and merged PR context across that range.
Group all intermediate changes to one subject into its final shipped behavior.
A bug that existed only between unpublished commits is not a user regression.
Keep internal changes out of user-facing notes, while declaring their operator
impact in the retained workflow.

Use the helper's minimum version (none -> patch, minor -> minor, major -> major).
Optional activation that needs operator work still affects impact. Validate an
explicit version through the helper; explain a deliberately larger version at
sign-off. Release candidates compare to the prior stable baseline and preserve
the eligible core version on promotion.

## Prepare coherent release inputs

Use the current Make targets rather than manually drifting package versions:

- `make python-release-plan BASE_TAG=<reported-stable-tag>` identifies changed
  shared packages, capabilities and manifests.
- `make prepare-python-release BASE_TAG=<reported-stable-tag>` with the reviewed
  `CAPABILITY_PACKAGES`, `CAPABILITY_MANIFESTS` and `POD_CHANGED` selections applies
  the independent package patches and relocks affected projects. Inspect target
  arguments before use. Select only affected manifests; retain initial versions
  for new manifests. Do not blindly set every Python package to the Fred version.
- Check stored configuration compatibility for bumped manifests and any necessary
  upgrade path. Review dependency floors, chart appVersions and lockfile churn.
- `make publish-libs-dry-run BASE_TAG=<reported-stable-tag>` builds and validates
  package artifacts without uploading. Actual `publish-libs` needs separate
  publication authorization and its own checks against PyPI.

Prepend the verified release entry to `apps/frontend/public/release.md`, preserving
its current shape and using the actual date/version. Write concise user outcomes;
combine related changes and omit implementation trivia. Never edit dist copies.
Keep operator procedures in source notes under `deploy/release-notes/changes/`,
including a declaration for release preparation itself. Distinguish mandatory
upgrade, optional activation and user re-ingestion. Do not request private values.

Reconcile ordering/conflicting source notes and preserve already published notes.
Use `after` dependencies or correction notes as needed. Run
`make release-guide RELEASE_VERSION=<version>` and inspect the generated
`deploy/release-notes/releases/v<version>/migration.md`. Fix sources and regenerate;
do not hand-edit the generated guide. An all-none guide must clearly say that
normal deployment requires no extra action. Resolve coverage blockers first.

## Review and publication

Validate the worktree guide with `scripts/migration_guides.py verify --worktree
--version <version>` through the repository's configured Python environment.
Stage explicit release-input paths only, commit on the topic branch, then run
`make migration-check` and verify the committed guide. Push that topic and open
the release PR against the resolved target, using the PR template and a body file.
Attach the created PR to the chat when the tool supports it.

Report the proposed version and baseline, full new UI note, ordered operator
procedures, changed package/manifest versions, actual checks and limitations.
Wait for required PR CI and developer review; merge only when authorized. No
implicit vulnerability or load campaign belongs to preparation.

After merge, verify the exact target commit, release inputs and required checks.
Present that commit, version and publication effects for tag authorization unless
already explicitly authorized. Publish two annotated tags on the same reviewed
commit: `code/v<version>` for images and `chart/v<version>` for Helm charts.
A bare `v<version>` does not trigger these workflows. Never overwrite an existing
tag; inspect its target if it already exists. Push only these two named tags,
never `git push --tags`. Do not promote to another branch implicitly.

Check the actual tag-triggered runs in `Build-and-push-docker.yml` and
`Package-and-push-charts.yml`; a branch CI run is not a release build. Report the
tag commit, run/release links and pending or failed publication stages honestly.
Tag authorization does not authorize package uploads, deployment or bypassing
branch protection.

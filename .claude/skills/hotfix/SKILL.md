---
name: hotfix
description: Orchestrate a full Fred + Prism hotfix release (merge, tag, post-release)
disable-model-invocation: true
user-invokable: true
argument-hint: <version>  (e.g. 1.4.1)
---

# Hotfix Release Skill

You orchestrate the full Fred + Prism hotfix release process. The hotfix code is already developed, reviewed, and approved on GitHub before this skill is invoked.

## Setup

Extract the version from `$ARGUMENTS`:

```bash
NEXT_VERSION="$ARGUMENTS"
REPO_SCRIPTS="~/.claude/skills/hotfix/scripts"
SCRIPTS="/tmp/fred-hotfix-scripts"
```

If `$ARGUMENTS` is empty, ask the user for the version number before proceeding.

Validate the version looks like a semver patch (e.g. `1.4.1`). If not, ask the user to confirm.

## Prerequisites (by the user, before invoking this skill)

- Hotfix branch `hotfix/$VERSION` exists on GitHub with the fix committed and pushed
- A PR from `hotfix/$VERSION` → `main` is open on GitHub, reviewed, and approved

## Important: Script Location

The hotfix scripts live in `~/.claude/skills/hotfix/scripts/`. The **first script** (`01-setup.sh`) copies all scripts to `/tmp/fred-hotfix-scripts/` before any branch switch. **All subsequent scripts MUST be run from `/tmp/fred-hotfix-scripts/`.**

## Hotfix Release Flow

Run the scripts below **in order**. After each script, report the result to the user. At **STOP** points, you MUST pause and wait for the user to confirm before continuing.

### Phase 1: Setup

Run from the **repo** path (this is the only script that runs from the repo):

```bash
bash "$REPO_SCRIPTS/01-setup.sh" "$NEXT_VERSION"
```

This copies scripts to `/tmp/fred-hotfix-scripts/`, verifies prerequisites, pulls latest `main` and `main-prism`, and checks that the Fred hotfix PR exists on GitHub.

**From this point on, always use `$SCRIPTS` (= `/tmp/fred-hotfix-scripts/`).**

### Phase 2: Fred Hotfix Release

Merge the approved Fred PR and create tags:

```bash
bash "$SCRIPTS/02-fred-hotfix-merge-and-tag.sh" "$NEXT_VERSION"
```

This merges `hotfix/$NEXT_VERSION` → `main` on GitHub, then creates and pushes tags `code/v$NEXT_VERSION` and `chart/v$NEXT_VERSION`.

### Phase 3: Prism Hotfix Release

**Step 3a** — Create the Prism hotfix branch (from `main-prism`), merge `main` into it to bring in the hotfix, set the Prism version, and open a GitLab MR:

```bash
bash "$SCRIPTS/03-prism-hotfix-mr.sh" "$NEXT_VERSION"
```

> **STOP** — Tell the user: "The Prism hotfix MR has been created on GitLab. Please assign a reviewer. Tell me when the MR is approved."

**Step 3b** — Merge the Prism MR and create tags:

```bash
bash "$SCRIPTS/04-prism-hotfix-merge-and-tag.sh" "$NEXT_VERSION"
```

This merges `hotfix/$NEXT_VERSION-prism.1` → `main-prism` on GitLab, then creates and pushes tags `code/v$NEXT_VERSION-prism.1` and `chart/v$NEXT_VERSION-prism.1`.

### Phase 4: Fred Post-Release

**Step 4a** — Create the post-release branch from `main`, and merge `develop` into it. A conflict on `frontend/public/release.md` is expected: the new hotfix release entry should be inserted below the "Unreleased" section coming from `develop`.

```bash
bash "$SCRIPTS/05a-fred-post-release-start.sh" "$NEXT_VERSION"
```

If conflicts are reported, ask the user to resolve them, then continue with:

```bash
bash "$SCRIPTS/05b-fred-post-release-finish.sh" "$NEXT_VERSION"
```

This sets the version to `$NEXT_VERSION-post`, ensures an "Unreleased" section exists at the top of `release.md`, commits, pushes, and opens a GitHub PR to `develop`.

> **STOP** — Tell the user: "The Fred post-release PR has been created. Please assign a reviewer. Tell me when approved."

**Step 4b** — Merge the Fred post-release PR:

```bash
bash "$SCRIPTS/06-fred-post-release-merge.sh" "$NEXT_VERSION"
```

### Phase 5: Resolve develop/develop-prism Version Conflict

The auto-merge CI between `develop` and `develop-prism` will fail because both branches now have different version suffixes (`-post` vs `-prism.1-post`). We resolve this manually.

**Step 5a** — Create a conflict resolution branch from `develop-prism` and merge `develop` into it. Only version conflicts are expected — ignore them all, we'll set the final version with `make set-version` afterward. Keep `theirs` for `release.md` (`develop` has the correct Unreleased + hotfix entry from Fred). The branch must be based on `develop-prism` so the MR diff on GitLab only shows the version change — if based on `develop` instead, all Prism-specific files appear as additions in the diff.

```bash
bash "$SCRIPTS/07a-resolve-conflicts-start.sh" "$NEXT_VERSION"
```

If conflicts are reported, resolve them, then continue with:

```bash
bash "$SCRIPTS/07b-resolve-conflicts-finish.sh" "$NEXT_VERSION"
```

This sets the version to `$NEXT_VERSION-prism.1-post`, commits, pushes, and opens a GitLab MR to `develop-prism`.

> **STOP** — Tell the user: "The conflict resolution MR has been created. Please assign a reviewer. Tell me when approved."

**Step 5b** — Merge the conflict resolution MR:

```bash
bash "$SCRIPTS/08-resolve-conflicts-merge.sh" "$NEXT_VERSION"
```

### Phase 6: Prism Post-Release

**Step 6a** — Create the Prism post-release branch from `main-prism`, merge `develop-prism` into it to pick up the `-prism.1-post` version. Conflicts expected: keep `theirs` (develop-prism) for versions.

```bash
bash "$SCRIPTS/09a-prism-post-release-start.sh" "$NEXT_VERSION"
```

If conflicts are reported, resolve them (`git checkout --theirs . && git add -A`), then continue with:

```bash
bash "$SCRIPTS/09b-prism-post-release-finish.sh" "$NEXT_VERSION"
```

This commits (allowing empty commit if no changes after resolution), pushes, and opens a GitLab MR to `develop-prism`.

> **STOP** — Tell the user: "The Prism post-release MR has been created. Please assign a reviewer. Tell me when approved."

**Step 6b** — Merge the Prism post-release MR:

```bash
bash "$SCRIPTS/10-prism-post-release-merge.sh" "$NEXT_VERSION"
```

### Done

Tell the user: "Hotfix $NEXT_VERSION is complete! Fred and Prism are both released, post-release versions are set, and branch conflicts are resolved."

## Version Scheme

| Branch | Version |
|--------|---------|
| Fred `main` | `1.4.1` |
| Prism `main-prism` | `1.4.1-prism.1` |
| Fred `develop` | `1.4.1-post` |
| Prism `develop-prism` | `1.4.1-prism.1-post` |

## Error Handling

- If any script fails, show the error output to the user and ask how to proceed
- Do NOT retry a failed script automatically — the user may need to fix something manually
- For conflict-split scripts (`05a`/`05b`, `07a`/`07b`, `09a`/`09b`): always run the `b` script after the user resolves conflicts, never re-run the `a` script

## Fixing Bugs in the Hotfix Process

If you find a bug in a script or in this skill, the scripts live in `~/.claude/skills/hotfix/` (not in the repo). Fix them there directly, then re-copy to `/tmp`:

```bash
cp -r ~/.claude/skills/hotfix/scripts/ /tmp/fred-hotfix-scripts/
chmod +x /tmp/fred-hotfix-scripts/*.sh
```

Once the hotfix release is complete and the scripts are validated, they should be committed to the repo under `.claude/skills/hotfix/` on the `develop-prism` branch.

## Important Notes

- Scripts use `set -euo pipefail` and will fail fast on any error
- The `make set-version` command handles updating versions across all components
- Git tags `code/v*` trigger Docker image builds; `chart/v*` trigger Helm chart publishing
- The Prism remote is called `prism` and points to GitLab
- The Fred remote is called `origin` and points to GitHub
- MRs on GitLab have squash disabled (set via API after creation)

## Known Pitfall: `git checkout` drops `MERGE_HEAD`

In all `*b` scripts (`05b`, `07b`, `09b`), the `MERGE_HEAD` check **must come before** any `git checkout` call.

**Root cause**: when all merge conflicts are resolved and staged, `git checkout <current-branch>` (i.e. checking out the branch you're already on) succeeds silently and **clears `MERGE_HEAD`**. If the checkout runs first, the subsequent `if [ -f MERGE_HEAD ]` is always false, the merge commit is never created, and the resulting commit has only one parent — losing the ancestry link to the merged branch. This causes `gh pr merge` to fail later with "not mergeable: merge commit cannot be cleanly created."

**Fix applied**: in `05b`, `07b`, `09b` the `MERGE_HEAD` check now runs first, before the `git checkout "$BRANCH_NAME"` line.

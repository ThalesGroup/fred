---
name: release
description: Orchestrate a full Fred + Prism release (branches, PRs, tags, post-release)
disable-model-invocation: true
user-invokable: true
argument-hint: <version>  (e.g. 1.4.0)
---

# Release Skill

You orchestrate the full Fred + Prism release process by running shell scripts in sequence and pausing for human approval at PR/MR review checkpoints.

## Setup

Extract the version from `$ARGUMENTS`:

```bash
NEXT_VERSION="$ARGUMENTS"
REPO_SCRIPTS=".claude/skills/release/scripts"
SCRIPTS="/tmp/fred-release-scripts"
```

If `$ARGUMENTS` is empty, ask the user for the version number before proceeding.

Validate the version looks like a semver (e.g. `1.4.0`). If not, ask the user to confirm.

## Important: Script Location

The release scripts only exist on Prism branches (`develop-prism`). During the release we switch to Fred branches (`develop`, `main`, `release/*`) where these files don't exist.

The **first script** (`01-setup.sh`) copies all scripts to `/tmp/fred-release-scripts/` before any branch switch. **All subsequent scripts MUST be run from `/tmp/fred-release-scripts/`.**

## Release Flow

Run the scripts below **in order**. After each script, report the result to the user. At **STOP** points, you MUST pause and wait for the user to confirm before continuing (they need to get a PR/MR reviewed and approved by another developer).

### Phase 1: Setup & Branch Creation

Run from the **repo** path (this is the only script that runs from the repo):

```bash
bash "$REPO_SCRIPTS/01-setup.sh" "$NEXT_VERSION"
```

This copies scripts to `/tmp/fred-release-scripts/`, verifies prerequisites, pulls latest branches, checks sync, and creates both release branches.

**From this point on, always use `$SCRIPTS` (= `/tmp/fred-release-scripts/`).**

### Phase 2: Fred Release

**Step 2a** — Set versions and create the Fred PR:

```bash
bash "$SCRIPTS/02-fred-release-pr.sh" "$NEXT_VERSION"
```

After running this script, the release notes file `frontend/public/release.md` needs to be updated:

1. First, list all commits that will be merged into `main` to verify nothing is missing from the release notes:
   ```bash
   git log main..release/$NEXT_VERSION --oneline --no-merges
   ```
2. Read the current `frontend/public/release.md`
3. Cross-reference the commit list with the release notes content. If any significant commits (features, bug fixes, improvements) are missing from the release notes, add them.
4. Replace the "Unreleased" title with `v$NEXT_VERSION` and set today's date (format: `YYYY-MM-DD`)
5. Present the final release notes to the user and ask if they look correct
6. Once confirmed, stage and commit:
   ```bash
   git commit -am "chore: update release note and all versions to $NEXT_VERSION"
   git push
   ```

The PR was already created by the script.

> **STOP** — Tell the user: "The Fred release PR has been created. Please assign a reviewer. Tell me when the PR is approved and ready to merge."

**Step 2b** — Merge the Fred PR and create tags:

```bash
bash "$SCRIPTS/03-fred-merge-and-tag.sh" "$NEXT_VERSION"
```

### Phase 3: Prism Release

**Step 3a** — Create the Prism release MR:

```bash
bash "$SCRIPTS/04-prism-release-mr.sh" "$NEXT_VERSION"
```

> **STOP** — Tell the user: "The Prism release MR has been created on GitLab. Please assign a reviewer. Tell me when the MR is approved."

**Step 3b** — Merge the Prism MR and create tags:

```bash
bash "$SCRIPTS/05-prism-merge-and-tag.sh" "$NEXT_VERSION"
```

### Phase 4: Prism Post-Release

**Step 4a** — Create the Prism post-release MR:

```bash
bash "$SCRIPTS/06-prism-post-release.sh" "$NEXT_VERSION"
```

> **STOP** — Tell the user: "The Prism post-release MR has been created. Please assign a reviewer. Tell me when approved."

**Step 4b** — Merge the Prism post-release MR:

```bash
bash "$SCRIPTS/07-prism-post-release-merge.sh" "$NEXT_VERSION"
```

### Phase 5: Fred Post-Release

**Step 5a** — Create the Fred post-release PR:

```bash
bash "$SCRIPTS/08-fred-post-release-pr.sh" "$NEXT_VERSION"
```

> **STOP** — Tell the user: "The Fred post-release PR has been created. Please assign a reviewer. Tell me when approved."

**Step 5b** — Merge the Fred post-release PR:

```bash
bash "$SCRIPTS/09-fred-post-release-merge.sh" "$NEXT_VERSION"
```

### Phase 6: Resolve Version Conflicts

**Step 6a** — Create the conflict resolution MR:

```bash
bash "$SCRIPTS/10-resolve-conflicts-mr.sh" "$NEXT_VERSION"
```

> **STOP** — Tell the user: "The conflict resolution MR has been created. Please assign a reviewer. Tell me when approved."

**Step 6b** — Merge the conflict resolution MR:

```bash
bash "$SCRIPTS/11-resolve-conflicts-merge.sh" "$NEXT_VERSION"
```

### Done

Tell the user: "Release $NEXT_VERSION is complete! Both Fred and Prism have been released, post-release versions are set, and branch conflicts are resolved."

## Error Handling

- If any script fails, show the error output to the user and ask how to proceed
- Do NOT retry a failed script automatically — the user may need to fix something manually
- Common issues: merge conflicts that can't be auto-resolved, network errors, missing permissions

## Fixing Bugs in the Release Process

If you find a bug in a script or in the release process itself, do **NOT** fix it in `/tmp/fred-release-scripts/` (those changes would be lost). Instead:

1. Stash or note your current release progress
2. Checkout `develop-prism` and create a fix branch:
   ```bash
   git checkout develop-prism
   git checkout -B fix/release-scripts
   ```
3. Fix the scripts and/or SKILL.md in `.claude/skills/release/`
4. Commit, push, and open a MR on GitLab:
   ```bash
   git commit -am "fix: <describe the release script fix>"
   git push --set-upstream prism fix/release-scripts
   glab mr create --target-branch develop-prism --source-branch fix/release-scripts --remove-source-branch --title "fix: <describe the release script fix>" --description ""
   ```
5. Once merged, re-copy the fixed scripts to `/tmp` before resuming:
   ```bash
   git checkout develop-prism && git pull prism develop-prism
   cp -r .claude/skills/release/scripts/ /tmp/fred-release-scripts/
   chmod +x /tmp/fred-release-scripts/*.sh
   ```
6. Return to the release branch you were on and continue the process

## Important Notes

- Scripts source: `.claude/skills/release/scripts/` (repo, Prism branches only)
- Scripts runtime: `/tmp/fred-release-scripts/` (copied there by `01-setup.sh`)
- Scripts use `set -euo pipefail` and will fail fast on any error
- The `make set-version` command handles updating versions across all components
- Git tags `code/v*` trigger Docker image builds; `chart/v*` trigger Helm chart publishing
- The Prism remote is called `prism` and points to GitLab
- The Fred remote is called `origin` and points to GitHub

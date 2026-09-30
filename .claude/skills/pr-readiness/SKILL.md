---
name: pr-readiness
description: Check Fred's prerequisites before opening or marking a pull request ready, then diagnose the PR's GitHub CI checks. Use for pre-PR readiness, CI validation, or resolving a red Fred PR.
---

# Fred PR readiness

Assess the current branch against its actual target branch and report a concrete **ready / not ready** verdict with evidence. When asked to fix the PR, resolve failures within the authorized scope and recheck them. Do not claim readiness from an earlier commit's results.

## Establish the review target

- Read root `AGENTS.md`, `CLAUDE.md`, closer instructions, and `.github/pull_request_template.md`; root `AGENTS.md` wins on the OpenSpec and frozen-backlog policy. Check `git status` and identify the tracking issue, current branch, target branch, PR number, and latest head SHA. Use `gh pr view --json number,baseRefName,headRefOid,isDraft,url` when a PR exists. Otherwise determine the intended target from the user or branch context; do not assume `main` or `develop`.
- Confirm the branch contains one coherent outcome, has no unrelated local edits, and the GitHub issue and any relevant OpenSpec change reflect its scope. For substantive work, check proposal, design, tasks, delta specs, team confirmation, and unfinished acceptance items. A localized lightweight fix can use the root `AGENTS.md` exception.
- Inspect `git diff --name-only <base>...HEAD` and `git diff --check <base>...HEAD`. Run the existing `audit-branch` procedure with the correct base if a deeper branch audit is useful; its old example uses `origin/develop`, which may be wrong.

## Required local gates

- From the repository root, run `make code-quality` and `make test` against the current work. The root quality target covers all modules; do not substitute a single package run for it. Record commands, date, head SHA, pass counts, skips, and failures. For a large or resource-limited run, report any gate not run as pending; do not recycle pre-rebase evidence.
- Every non-Dependabot PR needs a new English note under `docs/swift/ops/migrations/`, including docs-only PRs. Follow `docs/swift/ops/MIGRATION-GUIDES.md` and run `make migration-check MIGRATION_BASE=<target-ref>` with uncommitted edits included. A new Alembic revision requires at least `minor`. A `production` declaration requires a semantic change to Fred chart `values.yaml`; commented examples alone do not count. Validate the operational truth of the note as well as the script result.
- If chart or backend configuration changed, run the relevant drift and file checks from `.github/workflows/Check-config-schema.yml`, including `make check-chart-schema-drift` for chart changes. For Alembic changes, check heads and the migration workflow; inspect the actual CI failure before changing revision ancestry. If controllers or models changed, regenerate and compare the OpenAPI client as required by `CLAUDE.md`.
- Read the PR-triggered workflows in `.github/workflows/` for additional gates on this diff. In particular, `Check-docker-images.yml` builds every declared image from a clean checkout; check that Dockerfiles copy files imported from outside a package (including test fixtures), and reproduce relevant image builds when practical. Local package builds do not establish that an image build will pass.
- Review the documentation checklist and current contracts in `CLAUDE.md`. Reconcile implementation and OpenSpec artifacts, record exact remaining manual acceptance work, and archive only a completed change. Run specialist review procedures only where the changed code calls for them.

## GitHub CI and PR description

- Use `gh pr checks <number>` and inspect every failing, pending, cancelled, or skipped required check on the **latest head SHA**. Read job logs for failures and rerun local reproduction where practical. A skipped dependent job is not proof that its underlying check passed. Separate product failures, CI/environment failures, and manual checks; give each a next action and verify fixes on a new head.
- Fill `.github/pull_request_template.md` truthfully, with the issue, scope, tests, current quality output, raw `basedpyright` output where a touched package has a non-empty baseline, docs, risk/rollback, migration note and impact. Treat stale template references to the frozen backlog and unconditional RFC gate according to root `AGENTS.md`. Link evidence to the tested SHA. Mark incomplete manual provider or deployment scenarios as pending, even if unit CI is green.
- Before opening a PR, ensure the dedicated branch is pushed and review the proposed title, base and body. Before marking an existing PR ready, require current required checks to pass and no unresolved acceptance blocker. Do not merge or publish on the strength of this skill alone.

## Report

Give a concise table of each blocker with its evidence and owner/action. State what passed, what remains unverified, and the exact SHA checked. If GitHub authentication or logs are unavailable, continue local checks and state the resulting visibility limit explicitly.

---
name: review-fork
description: Safety-first review of an external pull request from an untrusted fork. Fetches the diff read-only into an isolated worktree, scans for supply-chain / exfiltration / CI-tampering threats, checks scope, then delegates correctness review. Never builds or runs the fork's code.
user-invocable: true
argument-hint: <PR number> [optional: repo, defaults to ThalesGroup/fred]
---

# Review Fork Skill

Review a pull request that comes from an **external contributor's fork**. The threat model is
different from your own branches: a malicious or careless external PR rarely breaks correctness —
it slips in CI/workflow changes, build-script hooks, new dependencies, network calls, or data
exfiltration. This skill owns that **safety layer** and delegates ordinary correctness review to
`/code-review`.

## Prime safety rule — read this first

**Never build or execute the fork's code during this review.** Do not run `make`, `npm install`,
`pip install`, `pytest`, the app, or any script the PR touches, until the threat scan is clean
**and** the developer explicitly approves. Reviewing code ≠ running code. Cloning and reading a
diff is safe; `npm install` runs arbitrary `postinstall` scripts, and `make`/`pytest` execute
attacker-controlled code. The whole point of this skill is to look without running.

Everything below is read-only except `git worktree add` (creates an isolated, throwaway checkout)
and `git fetch` (downloads refs). Both are safe — they never execute repo code.

## Step 0 — resolve arguments

- PR number: first token of `$ARGUMENTS` (required — if missing, ask).
- Repo: second token if given, else `ThalesGroup/fred` (this repo's `origin`).

Use `REPO` and `PR` as shorthand below.

## Step 1 — provenance

```bash
gh pr view $PR --repo $REPO --json number,title,author,isCrossRepository,headRepositoryOwner,changedFiles,additions,deletions,createdAt,state,labels
```

Establish and report:

- **Is it actually a fork?** `isCrossRepository` must be `true`. If `false`, this is an internal
  branch — tell the user the safety layer is overkill and they probably want `/review` instead.
- **Who is the author?** Check their track record:
  ```bash
  gh api "search/issues?q=repo:$REPO+author:<login>+type:pr+is:merged" --jq '.total_count'
  ```
  Zero merged PRs = first-time contributor = higher scrutiny. Note it; don't accuse.
- Headline the size (files / +adds / −dels). Large diffs from first-time contributors warrant the
  most care.

## Step 2 — safe fetch into an isolated worktree

GitHub exposes every PR head on the **base** repo as `refs/pull/<PR>/head`, so you never add the
fork as a remote. Fetch it and check it out in a throwaway worktree that is isolated from the
user's working tree:

```bash
git fetch origin "pull/$PR/head:pr-$PR"
git worktree add "../fred-pr-$PR" "pr-$PR"
```

Read code from `../fred-pr-$PR`. **Do not cd into it and run anything.** Capture the diff for the
scans below:

```bash
gh pr diff $PR --repo $REPO > /tmp/pr-$PR.diff
```

(Clean up at the end — see Step 7.)

## Step 3 — threat scan (the part generic reviewers skip)

Run these against the diff and the changed-file list. Each hit is a **flag for human eyes**, not an
automatic rejection — report what you find with the evidence.

**3a — high-trust files changed.** Any change to these is a red flag on an external PR because they
run on *your* infrastructure, not just in the app:

```bash
gh pr view $PR --repo $REPO --json files -q '.files[].path' | grep -Ei \
  '(^|/)\.github/|(^|/)Makefile|(^|/)Dockerfile|docker-compose|(^|/)\.gitlab-ci|Jenkinsfile|(^|/)scripts?/|(^|/)package\.json|(^|/)pyproject\.toml|(^|/)setup\.(py|cfg)|requirements.*\.txt|(^|/)\.pre-commit|(^|/)\.husky/'
```

If `.github/workflows/`, CI config, or build/install hooks are touched: **read those changes
line-by-line and quote them in the report.** A PR titled "fix typo" that edits a workflow is a
classic attack shape.

**3b — new dependencies.** Diff any manifest/lockfile changes. A new package — especially a
typo-squat or one with install scripts — is the most common supply-chain vector. List every added
or version-bumped dependency.

**3c — suspicious code patterns.** Grep the diff for added lines (`^+`) containing:

```bash
grep -nE '^\+' /tmp/pr-$PR.diff | grep -Ei \
  'eval\(|exec\(|subprocess|os\.system|child_process|requests\.(get|post)|urllib|fetch\(|socket|base64|b64decode|atob\(|pickle\.loads|marshal\.loads|curl |wget |\.env|os\.environ|getenv|secret|token|credential|api[_-]?key|\\x[0-9a-f]{2}|exfil'
```

For each hit, judge intent in context: a legit HTTP client in a networking module is fine; an
outbound POST added to a markdown formatter is not. Pay special attention to obfuscation
(base64/hex blobs, single-letter-variable minified-looking code, long string literals).

**3d — out-of-scope writes / binaries.** Look for large binary blobs, vendored directories, files
written outside the PR's apparent purpose, or modifications to unrelated modules.

## Step 4 — scope sanity

Compare the PR **title/description** against the **actual changed files**. A mismatch is a strong
signal — either sloppy (unrelated changes bundled in) or deliberate (cover story). State plainly:
"Title says X; diff also touches Y, Z — explain the connection or split the PR."

## Step 5 — delegate correctness review

Only now that the PR is provenance-checked and threat-scanned, run the ordinary quality/bug pass on
the same diff. Invoke `/code-review` (it reviews the working diff) or review the worktree directly
for: correctness, conventions (`docs/CONVENTIONS.md`), test coverage, contract drift. Don't
re-implement what `/code-review` does — call it.

## Step 6 — verdict

End with a structured verdict:

```
## Fork PR review — #<PR> "<title>"
- Author / provenance: <login>, <N merged PRs>, fork=<owner>
- Scope match: <matches title / MISMATCH: ...>
- Threat scan:
  - CI / build / install files: <none touched / list + quoted changes>
  - New dependencies: <none / list>
  - Suspicious patterns: <none / list with file:line and judgment>
  - Out-of-scope / binaries: <none / list>
- Correctness (from /code-review): <summary>
- VERDICT: SAFE TO BUILD LOCALLY | NEEDS HUMAN EYES (reasons) | DO NOT BUILD (reasons)
- Recommended next step: <merge / request changes with specifics / reject>
```

**Never upgrade to "SAFE TO BUILD LOCALLY" while any threat flag is open.** When in doubt, "NEEDS
HUMAN EYES" is the correct answer — say exactly what a human must look at.

## Step 7 — cleanup

Remove the throwaway worktree and branch so nothing fork-derived lingers:

```bash
git worktree remove "../fred-pr-$PR" --force
git branch -D "pr-$PR"
rm -f /tmp/pr-$PR.diff
```

## Posting feedback (only if asked)

Do not post anything to the PR unless the developer explicitly asks. When they do, use
`gh pr review $PR --repo $REPO --comment` or `--request-changes` with the verdict's specifics.

---
name: audit-branch
description: Pre-PR audit of the current branch — dead code, duplicate symbols, contract drift, leftover artifacts, import gaps.
user-invocable: true
argument-hint: [optional: focus area, e.g. "python" | "frontend" | "contracts"]
---

# Audit Branch Skill

A structured pre-PR audit. Run this before opening any pull request. It catches the class of
problems that `make code-quality` misses: logic regressions from merges, dead artifacts from
iteration, and drift between implementation and documented contracts.

## Step 1 — establish scope

```bash
git diff --name-only origin/develop...HEAD
```

Group changed files by module:
- `libs/fred-core/**`
- `libs/fred-sdk/**`, `libs/fred-runtime/**`, `libs/fred-agents/**`
- `apps/control-plane-backend/**`
- `apps/knowledge-flow-backend/**`
- `apps/frontend/**`

If `$ARGUMENTS` names a focus area (`python`, `frontend`, `contracts`), narrow the audit to that
group and note that the rest was skipped.

> **Open team decision — frontend scope:**
> By default this audit skips deep TypeScript analysis (it is slow and tsc already runs in
> `quality-root`). Should `/audit-branch` include a pass over new `.tsx`/`.ts` files for dead
> exports and missing `$ARGUMENTS`-style prop types? Decide before the first team-wide rollout.

## Step 2 — dead code and leftover artifacts

For each changed **Python** file, look for:

- Unused local assignments (`variable = ...` never read after assignment — ruff F841 catches runtime,
  but also check variables only used in a removed call).
- Imports that are not referenced in the file body (beyond `# noqa: F401` intentional ones).
- Commented-out code blocks of more than 3 lines — flag for removal or for explanation.
- Development-iteration artifacts: migration scripts with placeholder IDs
  (e.g. `c1d2e3f4`, `b2c3d4e5`), `TODO` / `FIXME` comments added in this branch.
- Duplicate class members: scan each changed class for repeated `@field_validator`,
  `@property`, or `@model_validator` decorators targeting the same field name.

For each changed **Alembic** directory, verify the migration chain:
```bash
# In the app directory:
uv run alembic history
```
Check that `down_revision` values form a linear chain with no orphaned scripts.

## Step 3 — import integrity

For any module referenced by a changed file that does **not** exist on disk, flag it — even if a
`# type: ignore` suppresses the static error. These are silent runtime bombs.

Pattern to grep:
```bash
grep -rn "from fred_core\." <changed_python_files> | grep -v "^#"
```
Then verify each referenced module path exists under `libs/fred-core/fred_core/`.

## Step 4 — contract drift check

Read `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` and
`docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`.

For each new or changed API endpoint, request/response model, or ORM model in the branch:
- Check whether it is listed in the relevant contract.
- If it is listed: verify the field names and types match.
- If it is not listed: flag as **undocumented** (not necessarily wrong, but the team must decide
  whether to add it to the contract or treat it as internal-only).

> **Open team decision — undocumented endpoints:**
> Should undocumented endpoints block the PR (hard stop) or produce a warning (advisory)?
> This is a policy call — the team should agree before enforcing it via CI.

## Step 5 — merge artifact check

If the branch has a merge commit (`git log --merges -1`), also run the checks from `/merge-review`
inline. Do not duplicate the output — summarise any merge-related findings in a single section.

## Output format

```
## Branch audit — <branch> — <date>

### Summary
- Files changed: N (Python: X, Frontend: Y, Alembic: Z, Docs: W)
- Merge commits: 0 | 1 (see Merge section)

### 🔴 Must fix before PR
- <file>:<line> — <description>

### 🟡 Should review
- <file>:<line> — <description>

### ℹ️ Team decisions needed
- <description of open policy choice>

### ✅ Clean areas
- Contract alignment: OK
- Alembic chain: linear, no orphans
```

Do **not** auto-fix anything. Report only. The developer decides what to act on.

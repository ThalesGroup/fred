---
name: merge-review
description: Post-merge validation — check that both sides of a merge were fully integrated, nothing was silently dropped, and quality still passes.
user-invocable: true
argument-hint: [optional: branch name that was merged in, e.g. "origin/swift"]
---

# Merge Review Skill

Run this immediately after any `git merge`. Merges — especially from a shared upstream branch — are
the highest-risk moment for silent regressions: `git checkout --theirs` drops logic, auto-merge
concatenates duplicate blocks, and renamed symbols go unnoticed.

## Step 1 — identify the merge

```bash
git log --merges -5 --oneline
```

Find the most recent merge commit (or the one named in `$ARGUMENTS`). Extract:
- Which branch was merged in
- Which files were touched by the merge commit

```bash
git show --name-status <merge-commit-sha>
```

## Step 2 — scan for incomplete integration

For each file modified by the merge, do the following checks.

### Dropped logic
Compare both parent sides of the merge:
```bash
git diff <merge-sha>^1 <merge-sha>   # what our branch added / kept
git diff <merge-sha>^2 <merge-sha>   # what the incoming branch added / kept
```
Look for code paths that existed on one parent but are absent in the merge result — specifically:
- Activity calls, workflow steps, or service method calls that one side introduced and the other
  did not touch (these should survive the merge).
- Registered Temporal activities or workers listed on one side but missing in the merged result.
- Import statements that one side added and the merge result dropped.

### Duplicate blocks
Read each merged Python file and look for:
- Repeated `@field_validator` decorators targeting the same field.
- Repeated `@property` definitions with the same name.
- Repeated field declarations inside a Pydantic model.
- Commented-out blocks that appear twice (sometimes both sides' conflict markers were accepted).

### Alembic chain
For any `alembic/versions/` directory touched by the merge:
```bash
uv run alembic history   # run from inside the app directory
```
Verify the chain is linear. Flag any script whose `down_revision` points to a script that no longer
exists, or any two scripts that share the same `down_revision`.

## Step 3 — run quality gate

Invoke the `/quality-root` skill (or run `make code-quality` from the monorepo root directly).
Do not skip this even if Step 2 found nothing — formatting drift and type errors are common
post-merge side effects.

## Step 4 — check registered workers

For any Temporal worker file touched by the merge (typically `activities.py`, `worker.py`):
- List every function decorated with `@activity.defn` in the activities file.
- Verify every such function is registered in the worker's `activities=[...]` list.
- List every `workflow.execute_activity("name", ...)` call in workflow files.
- Verify "name" matches an `@activity.defn(name="...")` registered in the worker.

Unregistered activities are silent runtime crashes — Temporal accepts the workflow start but
fails at execution time with no static warning.

> **Open team decision — blocking scope:**
> Should this skill hard-stop (refuse to close out) if it finds a dropped-logic or unregistered
> activity issue, or should it always be advisory so the developer decides?
> The team should agree on this, especially before running it in a CI context.

## Output format

```
## Merge review — <merge-sha> — <date>
Merged: <incoming-branch> → <target-branch>
Files touched by merge: N

### 🔴 Must verify
- <file>:<line> — <description of suspected dropped logic>

### 🟡 Suspicious patterns
- <file>:<line> — duplicate @field_validator for "retry_initial_interval"

### ✅ Clean
- Alembic chain: linear
- Registered activities: all workflow.execute_activity calls matched
- Quality gate: pass (or: see /quality-root output)
```

Do **not** auto-fix anything. The developer must confirm that flagged items are genuinely problems
before touching code — the skill cannot always distinguish an intentional removal from an accidental
drop.

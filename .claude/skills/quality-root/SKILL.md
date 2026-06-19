---
name: quality-root
description: Run make code-quality from the monorepo root, covering all modules. Never run it per-module.
user-invocable: true
argument-hint: [optional: module name to focus report on]
---

# Quality Root Skill

Run `make code-quality` from the **monorepo root** (`/home/dimi/Work/swift`), which covers all
modules in dependency order: `libs/fred-core`, `libs/fred-sdk`, `libs/fred-runtime`,
`libs/fred-agents`, `apps/control-plane-backend`, `apps/knowledge-flow-backend`, `apps/frontend`.

Running it per-module is a known failure mode — cross-module issues only appear from the root.

## Steps

1. `cd` to the monorepo root (find it by walking up from cwd until you find the top-level `Makefile`
   that orchestrates sub-projects).
2. Run `make code-quality` with a generous timeout (allow up to 10 minutes for a cold run).
3. Parse the output:
   - If **all modules pass**: report success with a one-line summary per module.
   - If **any module fails**: extract the exact error lines with file:line references, group them by
     module, and present them as a prioritised fix list.
4. If `$ARGUMENTS` names a specific module (e.g. `knowledge-flow-backend`), still run the full root
   check but highlight that module's results at the top of the report.

## What to look for beyond ruff/tsc errors

After the tool run, also scan the raw output for these softer signals that tools don't flag as errors
but that indicate real problems:

- `# type: ignore` comments that suppress `reportMissingImports` — the module probably doesn't exist yet.
- Basedpyright `reportRedeclaration` — a duplicate symbol, often from an unreviewed merge.
- Prettier `[warn]` lines — formatting drift that will cause the next CI run to fail.

## Output format

```
## Quality gate — <date>

| Module | Status | Issues |
|--------|--------|--------|
| libs/fred-core | ✅ pass | — |
| apps/knowledge-flow-backend | ❌ fail | 2 basedpyright errors |
...

### Failures

**apps/knowledge-flow-backend**
- `structures.py:417` — reportRedeclaration: duplicate validator `_normalize_retry_initial_interval`
```

> **Open team decision — auto-fix on pass:**
> Should this skill offer to auto-run `ruff format --fix` and `prettier --write` for formatting-only
> failures, or always report-only and let the developer run the fix manually?
> Agree on this before wiring it into CI.

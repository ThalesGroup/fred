---
name: test-gaps
description: Identify new code paths added in the current branch that have no test coverage. Reports gaps; does not write tests.
user-invocable: true
argument-hint: [optional: module name, e.g. "control-plane-backend" | "fred-core"]
---

# Test Gaps Skill

Find public functions, methods, and classes added or significantly changed in this branch that have
no corresponding test. This skill reports gaps — it does **not** write tests. Writing tests is a
separate, intentional act that requires the developer's judgment.

> **Open team decision — whether to generate stubs:**
> Some teams find it useful for this skill to optionally produce empty test stubs (functions with
> `pass` bodies) so the developer can fill them in. Others prefer a clean report only.
> Agree on this before the first team-wide rollout — the argument would be `/test-gaps --stubs`.

## Step 1 — establish scope

```bash
git diff --name-only origin/develop...HEAD
```

Filter to Python files only. If `$ARGUMENTS` names a module, restrict to that module's files.

## Step 2 — identify new or changed callables

For each changed Python file:
- Run `git diff origin/develop...HEAD -- <file>` and extract added lines (`+` prefix).
- From those lines, identify:
  - New `def` and `async def` functions at module level.
  - New `def` and `async def` methods inside classes (public only — skip names starting with `_`).
  - New class definitions.
- Note which of these are **net new** (didn't exist in `origin/develop`) vs **modified**.

Ignore private helpers (`_name`) and dunder methods (`__name__`) — they are tested indirectly.

## Step 3 — find test files

For each source file, locate its test counterpart using these conventions (in order):

1. `tests/test_<module_name>.py` in the same app root.
2. `tests/<subpath>/test_<filename>.py` mirroring the source path.
3. Any file in `tests/` that imports the source module.

If no test file exists: the entire module is untested — flag as a gap.

## Step 4 — cross-reference

For each new callable found in Step 2, grep the test files for any reference to that callable's
name:
```bash
grep -rn "<callable_name>" tests/
```

If no test file references the callable: flag it as untested.

> **Open team decision — integration tests:**
> Do tests that hit a real database (e.g. store-layer tests using a live Postgres engine) count
> toward coverage? Or only isolated unit tests with mocks?
> This affects whether `test_task_store.py` satisfies coverage for the store layer.
> The team should align on this — it changes how many gaps this skill reports.

## Step 5 — report

```
## Test gaps — <branch> — <date>

### Untested modules (no test file found)
- `apps/control-plane-backend/control_plane_backend/tasks/service.py`

### Untested callables
| File | Callable | Type | Status |
|------|----------|------|--------|
| `tasks/service.py` | `TaskService.create_run` | method | no test reference found |
| `tasks/store.py` | `TaskStore.append_event` | method | no test reference found |

### Partially covered
| File | Callable | Covered by |
|------|----------|------------|
| `tasks/api.py` | `get_task_run` | `test_task_store.py` (indirect) |

### ✅ Well covered
- `fred_core/tasks/bus.py` — all public methods referenced in tests
```

> **Open team decision — coverage threshold:**
> Should this skill flag a gap only when 0 tests exist, or when coverage falls below a threshold
> (e.g. 70%)? A threshold requires integrating `pytest-cov` output; zero-reference detection works
> without any test runner. Decide which model the team wants before adding this to the PR checklist.

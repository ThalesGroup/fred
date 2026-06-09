# AI Assistant Skills — Team Reference

Shared Claude Code skills that live in `.claude/skills/`. All team members invoke them the same way.
Skills are instructions to the AI assistant — they are not scripts and do not run automatically.

## Available skills

| Skill | Invoke | When to use |
|-------|--------|-------------|
| `/quality-root` | any time | Run `make code-quality` from the monorepo root. **Never run it per-module.** |
| `/merge-review` | after every `git merge` | Verify both sides were fully integrated — dropped logic, duplicate blocks, unregistered Temporal activities. |
| `/audit-branch` | before opening a PR | Dead code, leftover artifacts, contract drift, broken imports. |
| `/test-gaps` | before opening a PR | New public callables with no test coverage. |
| `/psql` | during debugging | Query the local Postgres stack via Docker. |

## Recommended workflow integration

```
git merge origin/develop
→ /merge-review              ← catches integration regressions immediately

[implementation work]

→ /audit-branch              ← pre-PR sweep
→ /test-gaps                 ← coverage check
→ /quality-root              ← final gate before push
```

## Open team decisions

The items below are intentionally unresolved. Each skill works without them, but the team should
agree before enforcing any of these as hard rules (e.g. in CI or PR checklists).

### 1. `/quality-root` — auto-fix formatting failures?

**The choice:** when only formatting errors remain (prettier, ruff format), should the skill offer
to auto-run the fix, or always report-only?

**Tradeoff:** auto-fix is faster day-to-day but can mask diffs in PR reviews if developers don't
notice what changed.

**Where to decide:** update `.claude/skills/quality-root/SKILL.md` once agreed.

---

### 2. `/audit-branch` — include frontend TypeScript analysis?

**The choice:** should the audit scan new `.tsx`/`.ts` files for dead exports and missing prop
types, or only cover Python modules?

**Tradeoff:** TypeScript analysis adds 2-3 minutes per run. `tsc` already runs in `quality-root`
and catches type errors; what's missing is export-level dead code detection.

**Where to decide:** update `.claude/skills/audit-branch/SKILL.md` once agreed.

---

### 3. `/audit-branch` — undocumented endpoints: block or warn?

**The choice:** if a new API endpoint is not listed in the relevant contract doc
(`RUNTIME-EXECUTION-CONTRACT.md` or `CONTROL-PLANE-PRODUCT-CONTRACT.md`), should the skill
treat this as a hard block (must fix before PR) or an advisory warning?

**Tradeoff:** hard block enforces contract hygiene but will slow down internal/experimental
endpoints that haven't been spec'd yet.

**Where to decide:** update `.claude/skills/audit-branch/SKILL.md` once agreed.

---

### 4. `/merge-review` — advisory vs blocking on dropped logic?

**The choice:** if the skill suspects a logic regression (e.g. a workflow step present on one
merge parent but absent in the result), should it refuse to close out (hard stop) or flag and
continue?

**Tradeoff:** false positives on hard stops are annoying; false negatives on advisory mode let
bugs through. The skill cannot always distinguish an intentional removal from an accidental one.

**Where to decide:** update `.claude/skills/merge-review/SKILL.md` once agreed.

---

### 5. `/test-gaps` — what counts as coverage?

**The choice A:** zero-reference detection (fast, no test runner needed) — flag any callable whose
name appears in no test file.

**The choice B:** `pytest-cov` threshold (accurate, requires a full test run) — flag any callable
below a team-agreed line coverage percentage.

**Choice C:** integration tests count. Choice D: integration tests do not count.

**Where to decide:** update `.claude/skills/test-gaps/SKILL.md` once agreed.

---

### 6. `/test-gaps` — generate empty test stubs?

**The choice:** should the skill optionally produce `pass`-body test stubs (invoked with
`/test-gaps --stubs`) so developers have a starting point, or should it always be report-only?

**Where to decide:** update `.claude/skills/test-gaps/SKILL.md` once agreed.

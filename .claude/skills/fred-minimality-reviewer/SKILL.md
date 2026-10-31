---
name: fred-minimality-reviewer
description: Review and plan FRED changes for minimality, convergence, reuse, dead-code removal, and measurable production-line reduction. Use when a branch adds or replaces abstractions, routes, state models, components, services, task flows, permissions, generated types, compatibility paths, or when the user asks to simplify FRED, reduce code size, remove dead code, consolidate implementations, or produce a deletion-first follow-up plan.
---

## Shared team policy

Read the active checkout's `AGENTS.md`, applicable nested instructions and
`fred-reconstruction-method` for domain/persistence work. Use that checkout's
arc42 and code; never load policy from a hardcoded personal Fred directory.
Apply the reuse, replacement and production-code reduction acceptance rule.
This is a bounded review unless fixes are requested. Propose verification needs
without automatically starting tests, load campaigns or independent agents.

# FRED Minimality Reviewer

Reduce concepts and owned production code, not readability. Prefer one coherent path
with fewer owners, states, translations, and compatibility branches.

## Required Workflow

1. Read repository instructions and agreed business decisions, current arc42 and nested guidance.
2. Establish the comparison boundary: current branch, base ref, and user-owned dirty changes.
3. Inventory changed and neighboring concepts before proposing code:
   - implementations and wrappers
   - registrations, factories, routes, hooks, stores, and dynamic imports
   - generated contracts and handwritten mirrors
   - tests, migrations, configuration, and documentation
4. Measure the diff with `git diff --stat` and `git diff --numstat`. Separate:
   - owned production code
   - tests and fixtures
   - generated files
   - migrations and schemas
   - documentation and deployment configuration
5. Search with `rg` for each old and new name, route, type, permission, state, helper,
   component, and configuration key. Do not infer deadness from one missing import.
6. Build a convergence map: existing path / competing path / canonical owner /
   deletion or folding candidate.
7. Apply the deletion-proof checklist before calling code dead.
8. Rank opportunities by correctness risk first, then net production-line reduction.
9. Define tests that preserve behavior after deletion.

## Deletion-Proof Checklist

Prove all applicable points before recommending removal:

- No static consumer remains (`rg`, imports, exports, route registration, dependency wiring).
- No dynamic consumer remains (plugin lookup, string registration, reflection, config entry,
  templates, CLI entry points, migrations, serialized names).
- The behavior has a named canonical replacement or is demonstrably unreachable.
- Authorization, failure behavior, persistence, retry, and UI behavior remain equivalent.
- Current agreed contracts and supported deployment configurations do not depend on it.
- Tests cover the retained path and fail if the removed behavior is accidentally restored.

Classify candidates as:

- **Delete now** — proven unused or fully superseded.
- **Fold now** — thin duplicate whose behavior belongs in an existing owner.
- **Converge first** — multiple live paths; choose and migrate to one before deletion.
- **Retain** — required by a contract, migration, supported variant, or dynamic consumer.

## Line-Reduction Rules

- Optimize net owned production lines and number of concepts, not total repository lines.
- Report gross additions and deletions; do not hide a large addition behind generated churn.
- Do not count generated-client deletion as architectural simplification unless its source
  contract or endpoint is also removed.
- Do not penalize tests that lock a smaller production design. Report test LOC separately.
- Never reduce lines by compressing statements, weakening types, merging unrelated concerns,
  deleting useful errors/logs, or replacing explicit code with opaque metaprogramming.
- Prefer deleting a path over adding a flag, adapter, alias, fallback, or second store.
- Transitional compatibility code must name its owner, removal condition, and target date or
  release. Otherwise treat it as permanent complexity.
- A new abstraction is justified only when it removes duplication or isolates real variability
  in the same change or a confirmed immediate follow-up.
- Preserve applied migrations; reduce live implementation without removing recovery
  guarantees or required evidence.

## FRED Minimality Invariants

- One business concept has one canonical vocabulary.
- One behavior has one owner; wrappers stay thin and justified.
- Backend models and generated frontend clients own cross-stack API shapes.
- Frontend server state is not mirrored without an explicit convergence strategy.
- New UI does not duplicate an existing design-system component.
- New routes do not bypass existing route families or permission models.
- Task producers reuse the shared durable task/event lifecycle rather than inventing local
  background execution or progress state.
- Keycloak authenticates; Control Plane evaluates authorization over PostgreSQL facts.
  Do not restore removed authorization engines or duplicate the permission matrix.

## Metrics to Report

For a reviewed diff or proposed slice, report when measurable:

| Metric | Before / added | After / deleted | Net |
| --- | ---: | ---: | ---: |
| Owned production LOC | | | |
| Test/fixture LOC | | | |
| Generated LOC | | | |
| Files | | | |
| Public concepts/routes/types | | | |

When exact LOC is unavailable, give a bounded estimate and state why. A deletion proposal
without consumer evidence is not a saving yet.

## Output

Lead with findings, highest severity first. Then provide:

1. **Short owner recap** — 3-6 lines: what is weak, why it matters, expected simplification,
   and material risk. Make it understandable without reading the detailed review.
2. **Evidence and convergence map** — exact files/lines and the canonical owner.
3. **Could remove instead of add** — deletion/folding candidates with proof status.
4. **Line-impact estimate** — separated metrics, never one misleading aggregate.
5. **Behavior-locking tests** — tests required before or with deletion.
6. **Complete implementation prompt** — when the user is scheduling work, provide a
   self-contained prompt for the chosen assistant to:
   - read repository governance and named canonical contracts
   - re-derive the finding from current code
   - preserve unrelated dirty changes
   - implement only the confirmed slice, deletion-first
   - name exact files/invariants and forbidden parallel paths
   - run proportional quality/tests and report before/after LOC by category
   - update the current task/issue and relevant arc42 explanation without a parallel ledger
   - stop and report if evidence contradicts the prompt

Do not implement a proposed slice merely because the prompt was produced. Wait for the user to
confirm and schedule it unless they explicitly requested implementation in the same turn.

## Red Flags

- Old and new names remain live together without a migration boundary.
- A wrapper, hook, store, or endpoint only forwards to another owner.
- A compatibility flag has no removal condition.
- A generated type is mirrored by handwritten Python or TypeScript.
- A local background task duplicates the durable task/executor lifecycle.
- A component is unmounted or unreachable but retains substantial state/effect code.
- Comments say temporary, legacy, deprecated, fallback, or TODO without tracked deletion.
- A claimed LOC reduction mostly comes from minification, tests, docs, or generated files.

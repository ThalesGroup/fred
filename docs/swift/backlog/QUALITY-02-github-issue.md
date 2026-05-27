# [QUALITY-02] Knowledge Flow quality parity with Control Plane + migration to apps folder

## Summary
Raise Knowledge Flow backend quality to equal or better than Control Plane quality standards, while migrating the service from knowledge-flow-backend to apps/knowledge-flow-backend.

This issue is the execution handoff for backlog item QUALITY-02.

## Source references
- Backlog: docs/swift/backlog/BACKLOG.md, section Phase QUALITY
- ID registry: docs/swift/data/id-legend.yaml, item QUALITY-02

## Current baseline (2026-05-25)
- Control Plane coverage: 79%
- Knowledge Flow coverage: 48%
- Bandit baseline footprint:
  - apps/control-plane-backend/.baseline/bandit-baseline.json: about 20 lines
  - knowledge-flow-backend/.baseline/bandit-baseline.json: about 2706 lines

## Goal
Reach equal or better practical quality than Control Plane for Knowledge Flow, without regressions and with default tests remaining offline-friendly.

## Scope
- Migrate service location:
  - from: knowledge-flow-backend/
  - to: apps/knowledge-flow-backend/
- Keep behavior and interfaces stable unless explicitly approved
- Improve test coverage and reduce baseline debt
- Keep code-quality and tests green throughout

## Required execution slices

### Q2.1 Baseline and migration prep
- [ ] Move service from knowledge-flow-backend/ to apps/knowledge-flow-backend/
- [ ] Keep all existing make targets usable from new root
- [ ] Preserve offline test behavior:
  - pytest marker not integration
  - socket restrictions
  - no external dependency requirement for default gates
- [ ] Produce before and after quality report (coverage, weak modules, baseline counts)

### Q2.2 Gate parity
- [ ] make code-quality passes in apps/knowledge-flow-backend
- [ ] make test passes in apps/knowledge-flow-backend
- [ ] No increase in basedpyright baseline entries
- [ ] No increase in bandit baseline entries

### Q2.3 Coverage uplift (risk-first)
- [ ] Raise total coverage from 48% to at least 65% (milestone A)
- [ ] Raise total coverage from at least 65% to at least 75% (milestone B)
- [ ] Target 80% stretch goal (parity plus)
- [ ] Prioritize modules under 40% coverage first
- [ ] Add deterministic offline unit tests only for default gates

### Q2.4 Baseline debt burn-down
- [ ] Reduce bandit baseline footprint by at least 40% from initial snapshot
- [ ] Reduce basedpyright baseline footprint by at least 30% from initial snapshot
- [ ] Add short rationale for each retained suppression

### Q2.5 Close-out proof pack
- [ ] Attach final metric table:
  - total coverage
  - top 20 weakest files before and after
  - baseline counts before and after
- [ ] Confirm service is fully runnable from apps/knowledge-flow-backend
- [ ] Update path-sensitive docs and scripts impacted by move

## Definition of done (hard gates)
- [ ] apps/knowledge-flow-backend is canonical location
- [ ] make code-quality is green from new location
- [ ] make test is green from new location
- [ ] Coverage is at least 75% (80% target)
- [ ] Baseline debt is strictly lower than initial snapshot
- [ ] No behavior regression in existing offline test suite

## Constraints
- Keep implementation minimal and direct
- Avoid architecture redesign unless explicitly approved
- Default validation must stay offline
- Integration tests must remain marked integration

## Suggested assignee profile
Backend engineer comfortable with Python testing, baseline debt cleanup, and path migration across make and CI wiring.

## Notes for reviewer
Please validate with objective outputs pasted in the issue:
- make code-quality output
- make test output
- coverage report summary
- baseline before and after counts

## Context

See [proposal.md](proposal.md) for motivation and tracking. The packaged
`grounded-research/SKILL.md` omits invocation controls, so both routes default
to enabled. The existing runtime contract already defines model-only skills.
The previous catalog consolidation has been archived.

## Goals / Non-Goals

Apply that existing contract to the packaged identity. Preserve the procedure,
canonical name, localization, preview and retained history. Custom directories
keep their authored metadata. No new invocation mechanism is needed.

## Decisions

Add `user-invocable: false` to
`libs/fred-runtime/fred_runtime/skills/grounded-research/SKILL.md`. Retain the
default `disable-model-invocation: false`. The existing catalog and eligibility
checks then enforce the same rule in commands, explicit execution and model
loads. A frontend-only filter would leave direct selections accepted; a loader
change would duplicate an existing mechanism.

Extend the parameterized tests in
`libs/fred-runtime/tests/test_common_skill_content.py` for model-only eligibility
and autonomous ReAct/native Deep instruction delivery. Include native child
loading and agent-origin attribution in focused verification. Reuse the existing
catalog and eligibility suites to check user command exclusion and explicit
selection rejection.

Update the existing migration guidance and invocation matrix during implementation
and close-out. Include this follow-up PR's own migration declaration as required
by the migration policy. No new schema or generated API field is required.

## Risks / Trade-offs

- Stale drafts may still select the skill: existing validation must reject them
  before inference, preserving the draft for correction.
- Mixed runtime versions advertise different modes: complete the runtime rollout
  before treating the catalog as uniform across replicas.

Work and memory stay bounded by the existing skill snapshot. This adds no
requests, queries, shared mutable state or coordination; concurrency and
cross-pod correctness use the existing immutable execution view and shared
global policy. Focused eligibility checks are appropriate; no new load test is
needed for the metadata-only change.

## Migration Plan

Deploy updated runtime packages to all replicas. Review drafts and integrations
that explicitly select `grounded-research`; natural-language research requests
remain supported through autonomous loading. Rollback to the previous runtime
package restores both invocation routes. No database or chart operation is
introduced.

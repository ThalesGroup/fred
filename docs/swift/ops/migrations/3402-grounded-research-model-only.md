---
schema: 1
title: "Reserve packaged grounded research for autonomous model invocation"
impact: minor
configuration: none
configuration_reason: "Only the packaged grounded-research invocation metadata changes; deployment configuration and chart values are unaffected."
---
## Applicability

Deployments using the packaged platform skill catalog. Custom skill directories
retain their authored invocation metadata.

## Prerequisites

Review drafts and integrations that explicitly select `grounded-research`.

## Configuration

No configuration or permission changes are required. Existing global skill
enablement policy continues to apply.

## Upgrade

Deploy the updated runtime package to every runtime replica. Remove explicit
`grounded-research` selections from drafts or integrations before resubmitting;
ask the research question in natural language so the model can choose the skill.
Mixed runtime versions can advertise different invocation modes during rollout.

## Validation

Verify `grounded-research` is absent from user commands and explicit selections
are rejected before inference. Inspect an autonomous ReAct or Deep load to confirm
the research instructions remain available with agent-origin attribution.

## Rollback

Restore the preceding runtime package on every replica to restore both invocation
routes. No database migration or history rewrite is introduced.

## Limitations

Already-loaded instructions retain the existing conversation continuity behavior.
Autonomous model selection remains dependent on the request and available tools.

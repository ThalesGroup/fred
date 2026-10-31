---
schema: 1
title: "Align team development instructions with Weaver foundations"
impact: none
configuration: none
configuration_reason: "Only contributor guidance, assistant instructions and skills change; no runtime configuration changes."
no_action_reason: "This update changes development guidance without modifying services, deployment artifacts or persisted data."
---
## Applicability

Contributors and coding assistants working on Fred Weaver.

## Prerequisites

No additional deployment prerequisites.

## Configuration

No runtime configuration changes. Repository tool adapters share AGENTS.md and
the skills exposed through .agents/skills and .claude/skills.

## Upgrade

Deploy normally. Contributors should read CONTRIBUTING.md and the shared
instructions before their next increment.

## Validation

Verify the tool entry points resolve to AGENTS.md and the Weaver reconstruction
skill, and that release-note validation accepts this note.

## Rollback

Restore the previous instruction revision if necessary; no data migration exists.

## Limitations

Capacity figures are design targets. This update does not implement the business
decisions or establish runtime capacity. Functional validation remains separate.

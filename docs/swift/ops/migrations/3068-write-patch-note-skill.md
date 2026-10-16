---
schema: 1
title: "Add a bilingual user patch-note drafting skill"
impact: none
configuration: none
configuration_reason: "Only repository skill instructions change; no Fred configuration key, chart value or permission changes."
no_action_reason: "The skill produces text for authors to copy manually; it changes no deployed behavior, stored data or client contract."
---
## Applicability

All Fred deployments upgrading to a release that contains this repository skill.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

No production validation is needed. In the repository, invoke the skill and check
that it returns a French and an English title with separate Markdown bodies.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The skill only drafts text; it does not publish or activate a patch note.

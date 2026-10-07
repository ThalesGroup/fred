---
schema: 1
title: "Plan read-only conversations after managed agent deletion"
impact: none
configuration: none
configuration_reason: "This draft adds OpenSpec planning artifacts only; no configuration keys, application code or database schemas change."
no_action_reason: "Planning documents do not change deployed behavior and require no operator action. Reconcile this note when the implementation is added."
---

## Applicability

The planning-only draft for preserving conversation history after managed agent deletion. The proposed runtime/frontend behavior is not implemented in this draft.

## Prerequisites

No additional prerequisites for these documentation changes.

## Configuration

No local or production configuration changes.

## Upgrade

No upgrade action is required for planning artifacts. Review the reconciled note before deploying the eventual implementation.

## Validation

Validate the OpenSpec change with `openspec validate read-only-conversations-after-agent-deletion --strict` and validate this declaration with `make migration-check MIGRATION_BASE=origin/swift`.

## Rollback

Revert the planning documentation if needed; deployed behavior and stored conversations are unaffected.

## Limitations

This note does not certify the proposed fix. Implementation, behavioral tests and independent review remain pending developer confirmation of the planning artifacts.

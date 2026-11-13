---
schema: 1
title: "Show progress while an agent's PowerPoint template is prepared"
impact: none
configuration: local
configuration_reason: "The local fred-agents production YAML now pins the Temporal endpoint and PPT preparation limits; deployed chart values and defaults do not change."
no_action_reason: "Existing upload and analysis APIs are unchanged; the indicators appear after a normal deployment."
---

## Applicability

Existing Fred deployments using PowerPoint template overrides on agents.

## Prerequisites

No additional deployment prerequisites beyond the normal procedure.

## Configuration

For a local run, point the control-plane, knowledge-flow and fred-agents
`config/.env` files at `./config/configuration_prod.yaml`. Start the
fred-agents preparation worker with `make run-worker` from `apps/fred-agents`.
The committed production YAML already enables `ppt_builder` preparation on
the runtime and control-plane sides and configures Knowledge Flow vision.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Upload a PowerPoint template override and save the agent. The form shows upload
progress and says the window can be closed. The agent card shows preparation
progress until
the template analysis succeeds or fails.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The existing polling schedule determines when the card reflects the final
preparation state.

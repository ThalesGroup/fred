---
schema: 1
title: "Show progress while an agent's PowerPoint template is prepared"
impact: minor
configuration: local
configuration_reason: "The local fred-agents production YAML now pins the Temporal endpoint and PPT preparation limits; deployed chart values and defaults do not change."
impact_reason: "Agent template selection now uses temporary preparation records and new team-scoped upload endpoints."
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

Apply the control-plane Alembic migration before deploying the new frontend.
Deploy the updated control-plane API, fred-agents worker, and frontend together.
Older clients may continue to use the existing upload-on-save route.

## Validation

Select a PowerPoint template override during agent creation or editing. The form
shows transfer and preparation progress immediately, without saving. The
fred-agents worker starts analysis after the transfer. Close and reopen the form
to check progress, then save to attach the prepared template to the agent.

## Rollback

Rollback the frontend first, then the API and worker. The existing upload-on-save
route remains available. The additive migration can remain in place during a
code rollback. Its downgrade requires all temporary draft rows and assets to be
cleaned before the draft owner-kind constraints can be removed.

## Limitations

The existing polling schedule determines when the card reflects the final
preparation state.

---
schema: 1
title: "Explicit reasoning effort and evaluation admission evidence"
impact: none
configuration: none
configuration_reason: "Explicit effort uses existing model metadata and inference admission; no deployment setting or chart changes."
no_action_reason: "Normal deployment supplies the updated Control Plane and runtime contracts; existing boolean reasoning callers keep their behavior."
---
## Applicability

Fresh Weaver installations using Control Plane-managed agent evaluation.

## Prerequisites

Control Plane and the Python runtime must include the new effort contract to use low or medium.

## Configuration

No new configuration. Effective levels reuse the offer's reasoning metadata; reasoning-capable offers without declared levels support high.

## Upgrade

Deploy the matching Fred components normally. Swift and earlier Weaver upgrades remain unsupported; this change adds no data migration.

## Validation

An evaluation requesting a supported effort returns that effort and the admitted model key, selection source and revisions in `inference`. An unsupported effort returns HTTP 409 with `reasoning_effort_unsupported` before execution. The chat boolean behavior is unchanged. Dimi performs live validation on k3d.

## Rollback

Use the normal deployment procedure for matching components; callers using explicit effort must return to the boolean contract when reverting this feature.

## Limitations

An older Python runtime accepting only `high` rejects low/medium admissions from a newer Control Plane, failing closed. Provider-reported `model_name` remains informational. Evaluator and k3d catalogue changes are separate lots; no live provider validation is claimed here.

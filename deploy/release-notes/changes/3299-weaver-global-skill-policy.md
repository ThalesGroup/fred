---
schema: 1
title: "Apply global platform skill opt-outs at turn admission"
impact: minor
configuration: local
configuration_reason: "Only comments in the local YAML examples change; packaged skills already default to enabled and explicit null remains the opt-out. Production chart values are unchanged, and policy is stored in the control-plane database."
---
## Applicability

Deployments that use the packaged platform skill catalog.

## Prerequisites

Apply control-plane migration `0006_platform_skill_policy` after the current `0005` baseline before starting the updated control plane. Complete the runtime rollout before disabling a skill.

## Configuration

No configuration keys change. A missing policy row leaves a skill enabled.

## Upgrade

Deploy the control plane and runtime together. The control plane reads disabled names from PostgreSQL at each admission and includes them in the runtime binding. The runtime excludes those packaged skills from new loads.

## Validation

As a feature manager, disable a packaged skill through the platform API. Confirm a new turn cannot select or load it, including when requests land on different runtime replicas. Re-enable it and confirm a later turn can load it again.

## Rollback

Re-enable all disabled skills before rolling runtimes back. The table may remain until the new control plane has stopped; dropping it removes stored opt-outs.

## Limitations

This draft still needs runtime-source inventory validation before disabling and the Weaver administration screen. Until those are complete, do not use the write API in production.

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

No configuration keys change. A missing policy row leaves a skill enabled. `skills: null` keeps a runtime's skills disabled, and a mounted custom directory remains outside the packaged-skill opt-out policy.

## Upgrade

Deploy the control plane and all runtime replicas before disabling a skill. The control plane consolidates live packaged-skill inventories from configured runtimes and reads the global policy from PostgreSQL at each admission. The admitted catalog and runtime binding exclude disabled packaged skills. Feature managers can review source status and change the global policy at Administration > Platform skills.

## Validation

As a feature manager, disable a packaged skill through the platform screen. Confirm a new turn cannot select, preview or load it, including when requests land on different runtime replicas. Re-enable it and confirm a later turn can load it again. Verify that `skills: null` and custom-directory sources are identified separately in the screen, and that a source outage blocks new disables but allows restoring a previously stored name.

## Rollback

Re-enable all disabled skills before rolling runtimes back. The table may remain until the new control plane has stopped; dropping it removes stored opt-outs.

## Limitations

A logical runtime URL behind a load balancer cannot prove that every replica is updated. Complete the runtime rollout before setting global opt-outs. Changes apply to new loads from the next turn; previously loaded instructions remain in conversation context.

---
schema: 1
title: "Accept discovered model licenses in Agent Pod runtime resolution"
impact: none
configuration: none
configuration_reason: "The SDK accepts license metadata already emitted by Control Plane; model source and organization policy settings are unchanged."
no_action_reason: "Deploy the corrected Agent Pod image through the normal chart update; no credential, policy or data changes are required."
---
## Applicability

Fresh Fred v5 installations whose authorized model offers include license metadata.

## Prerequisites

Use an Agent Pod build containing the corrected fred-sdk contract.

## Configuration

No configuration changes are required. Model permissions and strict contract
validation remain in effect.

## Upgrade

Publish and deploy the corrected Agent Pod image through the normal chart update.
Do not remove license metadata or disable contract validation as a workaround.

## Validation

Start a conversation in an organization permitting models with discovered license
metadata. Runtime resolution must accept the Control Plane response instead of
returning "Weaver runtime resolution is unavailable or incomplete".

## Rollback

Reverting the SDK fix restores the failure when authorized offers contain license
metadata. This change introduces no data migration.

## Limitations

The regression check validates runtime catalogue parsing, not a complete model
inference. Existing images must be rebuilt to receive the fix.

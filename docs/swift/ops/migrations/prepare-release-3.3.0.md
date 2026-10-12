---
schema: 1
title: "Prepare the v3.3.0 release notes and operator guide"
impact: none
configuration: none
configuration_reason: "Only release documentation and ordering of existing migration procedures change; no application or deployment configuration changes."
no_action_reason: "This contribution prepares the user-facing notes and consolidated operator guide. All upgrade actions are declared by the included migration notes, with no additional action from release preparation itself."
---
## Applicability

Fred operators preparing an upgrade from v3.2.0 to v3.3.0.

## Prerequisites

Review the consolidated migration guide and all applicable source procedures before deployment.

## Configuration

Release preparation introduces no configuration changes. Apply the configuration removals declared by the included retirement procedures.

## Upgrade

Follow the generated v3.3.0 guide. Its operational impact is minor because integrations must be adapted and the retired surfaces require preparation. Library patch versions are separate from the paired code/chart release version.

## Validation

Verify that the guide is generated from the complete release range and that the UI release notes show v3.3.0. Check the applicable upgrade validations in the included procedures.

## Rollback

This documentation contribution changes no data. Follow the combined rollback instructions for the application changes in the guide.

## Limitations

Preparing these documents does not publish libraries, images, charts or tags. Customer-specific file exports, integration inventories and staging validation remain operator responsibilities.

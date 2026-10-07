---
schema: 1
title: "Align frontend npm package candidates on alpha.4"
impact: none
configuration: none
configuration_reason: "Only npm release metadata and documentation change; Fred configuration keys, chart values and defaults are unchanged."
no_action_reason: "Fred deployments consume the canonical frontend sources, not these npm archives; aligning an unpublished token version does not change deployed behavior."
---

## Applicability

Existing Fred deployments upgrading to this release. This change aligns the
unpublished design-token candidate with UI and iframe SDK at 0.1.0-alpha.4.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional deployment action is required. External npm
package adoption is separate: after publication, upgrade UI and design tokens
together to alpha.4 and follow the existing token migration notes.

## Validation

Check that the three manifests under libs/frontend and their workspace lockfile
entries declare 0.1.0-alpha.4. Prepare fresh archives and run the existing release
validation workflow before publishing.

## Rollback

Revert the version-alignment commit before publication. No data migration is
introduced; published npm versions must not be overwritten.

## Limitations

This change does not publish packages. Earlier UI/token combinations and
compatibility aliases are outside the accepted scope of this prerelease.

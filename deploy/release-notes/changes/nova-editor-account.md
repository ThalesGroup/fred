---
schema: 1
title: "Add a separate Nova editor for the ingestion exercise"
impact: none
configuration: none
configuration_reason: "Only the optional Nova provisioning fixture and its documentation change."
no_action_reason: "Existing deployments require no upgrade action. Operators may explicitly reimport the regenerated Nova bundle to add the test editor."
---
## Applicability

Optional local Swift/Weaver coexistence exercise using `make bundle-migration`.

## Prerequisites

Check the shared SSO for an unrelated `nova.editeur` identity before import.
Use the existing Weaver platform admin for provisioning.

## Configuration

No runtime configuration changes. The editor has Member on Nova and Editor on
Pilote, with no platform or Owner role. Existing responsible-person roles remain
unchanged.

## Upgrade

Regenerate the bundle and explicitly import it through Provisioning. Replay is
additive and preserves existing passwords and grants. No rebuild is required.

## Validation

The offline bundle regression and ZIP role checks pass. Confirm the editor's
roles after import and stop before ingestion to capture the storage baseline.

## Rollback

Reverting the fixture does not remove an imported identity or its grants.

## Limitations

Preparation creates no live account. This fixture neither migrates Swift data nor
proves storage isolation; the editor's browser journey remains to be validated.

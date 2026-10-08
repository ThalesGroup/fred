---
schema: 1
title: "Correction: enableAllResourceSpaces is no longer a supported frontend flag"
impact: none
after: [retire-mon-espace]
configuration: none
configuration_reason: "No configuration key, default or chart value changes in this correction; it only supersedes a sentence of the published 2910 note. The flag's removal itself is declared by retire-mon-espace."
no_action_reason: "Nothing to do beyond retire-mon-espace, which already tells operators to remove enableAllResourceSpaces from their overlays."
---
## Applicability

Operators following the published `2910-remove-unused-task-tray` note (v3.2.0)
while upgrading past the release that retires Mon espace. That note lists
`enableAllResourceSpaces` among the three supported
`platform.frontend.feature_flags`; this is no longer true.

## Prerequisites

None: this note corrects guidance only, and the procedure it points to lists
its own prerequisites.

## Configuration

Under `platform.frontend.feature_flags`, keep only `enableApplications` and
`enableInformationSystems`. Do not keep `enableAllResourceSpaces`: the chart and
the generated configuration schemas no longer accept it. The `retire-mon-espace`
note gives the full procedure.

## Upgrade

Follow `retire-mon-espace`. Read the 2910 note's mention of three supported
flags as two.

## Validation

`/control-plane/v1/frontend/bootstrap` exposes `enableApplications` and
`enableInformationSystems`, and no longer `enableAllResourceSpaces`.

## Rollback

Not applicable: this note changes no behaviour, only the guidance.

## Limitations

The published 2910 note is left as released for v3.2.0, as published notes are
immutable; this note supersedes its flag list.

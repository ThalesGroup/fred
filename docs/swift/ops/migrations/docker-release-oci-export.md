---
schema: 1
title: "Restore Docker release publication with provenance and SBOM reports"
impact: none
configuration: none
configuration_reason: "Only release CI changes; application configuration and chart values are unchanged."
no_action_reason: "The fix restores image publication; deployed services and database schemas are unchanged."
---

## Applicability

Docker release publication with maximum provenance and CycloneDX reports.

## Prerequisites

No additional deployment prerequisites.

## Configuration

No deployment configuration changes are required.

## Upgrade

Deploy Fred normally; no operator action is required.

## Validation

Verify all images publish with provenance, each image has a non-empty CycloneDX
report, and the code release contains the committed migration guide.
The image list includes the Knowledge Flow PyMuPDF variant.

## Rollback

Revert the workflow correction; no database or application rollback is needed.

## Limitations

This CI fix does not change the operator procedures of an already tagged release.

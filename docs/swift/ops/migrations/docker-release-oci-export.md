---
schema: 1
title: "Restore Docker release publication with provenance and SBOM reports"
impact: none
configuration: none
configuration_reason: "Only release CI changes; application configuration and chart values are unchanged."
no_action_reason: "The fix restores image publication and supports retrying an existing approved tag; deployed services and database schemas are unchanged."
---

## Applicability

Docker release publication, including recovery after an exporter failure.

## Prerequisites

Release maintainers must merge the CI fix before recovering an existing tag.

## Configuration

No deployment configuration changes are required.

## Upgrade

Deploy Fred normally. For a failed publication, release maintainers follow the
recovery command in [Release strategy](../../RELEASE-STRATEGY.md#recovering-a-failed-docker-publication).
The approved code/chart tags remain on their original commit.

## Validation

Verify all images publish with provenance, each image has a non-empty CycloneDX
report, and the code release contains the committed migration guide.

## Rollback

Revert the workflow correction; no database or application rollback is needed.

## Limitations

Recovery rebuilds the original application sources using the corrected workflow.
It does not publish Helm charts or Python packages, and does not change the
operator procedures of an already tagged release.

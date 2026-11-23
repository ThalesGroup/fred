---
schema: 1
title: "Keep Trivy CVE reports when image SBOM generation takes longer"
impact: none
configuration: none
configuration_reason: "Only the pull-request Trivy workflow changes; application images and deployment settings are unchanged."
no_action_reason: "CI retains the vulnerability report before generating license and SBOM evidence; deployed Fred components are unchanged."
---

## Applicability

Pull-request image scans, especially the large Knowledge Flow PyMuPDF image.
Deployed Fred instances are not affected.

## Prerequisites

No additional prerequisites.

## Configuration

No deployment configuration changes are required.

## Upgrade

Deploy Fred normally; no operator action is required.

## Validation

The PyMuPDF Trivy job uploads its CVE report after scanning the image and has
15 minutes to generate its CycloneDX SBOM. The report remains available if the
later license or SBOM step fails.

## Rollback

Revert the CI workflow change; no data migration is involved.

## Limitations

A longer timeout does not guarantee that the SBOM scan completes if the runner
or image analysis fails for another reason.

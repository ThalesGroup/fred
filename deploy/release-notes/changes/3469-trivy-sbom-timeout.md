---
schema: 1
title: "Keep Trivy CVE reports when image SBOM generation takes longer"
impact: none
configuration: none
configuration_reason: "Only the pull-request Trivy workflow changes; application images and deployment settings are unchanged."
no_action_reason: "CI retains the vulnerability report before later image checks and SBOM generation; deployed Fred components are unchanged."
---

## Applicability

Pull-request Docker image builds, including fred-agents and all Weaver Knowledge Flow image variants.
Deployed Fred instances are not affected.

## Prerequisites

The existing shared Trivy installation action and Docker image matrix.

## Configuration

No deployment configuration changes.

## Upgrade

Normal source integration suffices. The CycloneDX command uses --timeout 15m; the vulnerability report uploads right after the scan, before the import check and the license/SBOM step.

## Validation

Inspect the workflow ordering and image-selection tests. The report remains available if a later check, license or SBOM step fails. A GitHub Actions scan was not run locally.

## Rollback

Revert the workflow change if required; no application migration is involved.

## Limitations

The timeout does not guarantee that a particular image scan will finish. Existing isolated Knowledge Flow image validation is preserved.

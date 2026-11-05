---
schema: 1
title: "Allow longer Trivy SBOM scans while retaining vulnerability reports"
impact: none
configuration: none
configuration_reason: "Only CI scan duration and artifact ordering change; deployment configuration and application data are unchanged."
no_action_reason: "Only CI scan duration and artifact ordering change; deployment configuration and application data are unchanged."
---

## Applicability

Pull-request Docker image builds, including fred-agents and all Weaver Knowledge Flow image variants.

## Prerequisites

The existing shared Trivy installation action and Docker image matrix.

## Configuration

No deployment configuration changes.

## Upgrade

Normal source integration suffices. The CycloneDX command uses --timeout 15m; vulnerability reports upload before the license/SBOM step.

## Validation

Inspect the workflow ordering and image-selection tests. A GitHub Actions scan was not run locally.

## Rollback

Revert the workflow change if required; no application migration is involved.

## Limitations

The timeout does not guarantee that a particular image scan will finish. Existing isolated Knowledge Flow image validation is preserved.

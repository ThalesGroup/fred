---
schema: 1
title: "Generate local application image SBOMs"
impact: none
configuration: none
configuration_reason: "Adds local Make and Trivy tooling only; application configuration keys and defaults are unchanged."
no_action_reason: "SBOM generation is a developer command; existing deployments, data and APIs upgrade normally."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional deployment prerequisites. Developers using the command need
Docker, jq and either native Trivy or its Docker image, as documented in README.md.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

With the published application images available locally, run `make sbom` or
`make sbom TRIVY_MODE=docker` and check for non-empty CycloneDX reports in
`target/sbom/`.
Add `CVES=true` to include detected vulnerabilities in those reports.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Local reports cover packages detectable inside the images; they do not
inventory source-only or build-stage dependencies.

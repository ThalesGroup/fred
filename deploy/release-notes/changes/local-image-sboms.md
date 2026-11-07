---
schema: 1
title: "Generate application image SBOMs locally and on release tags"
impact: none
configuration: none
configuration_reason: "Adds a local Make target and a release CI report; application configuration keys and defaults are unchanged."
no_action_reason: "SBOM generation is a developer command and a release CI artifact; Fred components, data and APIs are unchanged."
---
## Applicability

Fresh Fred installations and developers generating image SBOMs.

## Prerequisites

No additional deployment prerequisites. The command needs jq, Docker and images
already built, as documented in deploy/README.md. Trivy runs only from its Docker image.

## Configuration

No configuration changes are required.

## Upgrade

Install Fred normally; no additional operator or user action is required.

## Validation

Build the images, then run `make sbom` as described under "Image SBOMs" in
deploy/README.md and check for non-empty CycloneDX reports in `target/sbom/`.
Release-tag CI generates one report with CVEs in each image job after its push.

## Rollback

Revert the change if required; no application migration is involved.

## Limitations

Local reports cover packages detectable inside the images; they do not
inventory source-only or build-stage dependencies.

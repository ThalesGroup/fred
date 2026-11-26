---
schema: 1
title: "Publish coherent v5 development charts after successful image builds"
impact: minor
configuration: production
configuration_reason: "Fred images can now be pinned by digest; development charts supply these pins and consumers follow a numbered development version range."
after: [v5-processing-transport]
---

## Applicability

Fresh v5 test platforms consuming the standard Fred chart, including monitor.

## Prerequisites

A successful Weaver image-and-chart publication, existing platform Secrets and
instance values. The factory uses Helmfile 1.8.1 to resolve the latest OCI dev chart.

## Configuration

Development charts use version `5.0.0-dev.<run-id>.<attempt>` and supply
`applications.<name>.image.digest` for every built-in image. Digests override tags.
Keep these defaults; override platform settings only. To select an image variant,
override both repository and digest, or explicitly clear the digest to use a tag.
The archive's `files/image-digests.json` includes the optional PyMuPDF variant.
See [development publication](../../README.md#development-charts).

## Upgrade

Run the factory's existing `make k3d-app FRED=weaver APP=fred` to consume the latest
successful development build. Use `RELEASE=<exact-chart-version>` to select a
particular build. Publication does not deploy a cluster. No data upgrade from an
incompatible development installation is supported.

## Validation

Confirm the installed chart version and check that workloads, init containers and
SQL hooks reference its image digests, including monitor. Validate the application
journeys on the target platform; local packaging checks do not prove deployment.

## Rollback

Select a previously accepted exact chart version and compatible instance values.
This restores image selection only, not database state; prepare a fresh database
when development schemas are incompatible.

## Limitations

Development charts are not tagged releases and carry no attached operator report.
Paired `code/v*` and `chart/v*` releases retain their report validation. Mutable
`v5-dev` aliases remain available and can advance partially on a failed image build;
the dev chart is published only after the complete build succeeds.

---
schema: 1
title: "Identify version 5 development images by their major version"
impact: minor
configuration: none
configuration_reason: "The CI publication alias and Helm check examples change; versioned chart defaults and application configuration schemas are unchanged."
after: [weaver-initial-release]
---

## Applicability

Development platforms following the images published from the `weaver` branch.
Versioned releases and Swift's `swift-dev` publication are unchanged.

## Prerequisites

Wait for all six `v5-dev` image publications to succeed before updating a platform.

## Configuration

In platform-owned values, replace `weaver-dev` with `v5-dev` wherever it is used
as `applications.<name>.image.tag`. Keep component repository names unchanged.
Versioned deployments retain their exact release tags and matching chart.

## Upgrade

Apply the updated values and arrange an image refresh and rollout. The old
`weaver-dev` alias is no longer published; its existing images remain in GHCR.
See the [publication conventions](../../README.md#image-publication).

## Validation

Check that the rendered workloads select `v5-dev` and that their image revisions
match the successful publication's source commit. A tag rename alone does not
restart existing workloads.

## Rollback

Restore the previously accepted image digests or an explicit release version.
No database change is introduced by this publication rename.

## Limitations

This change does not rename branches, namespaces, databases or platform URLs.
It does not deploy a platform. `v5-dev` remains mutable and is intended for
development; use exact release versions for preproduction and production.

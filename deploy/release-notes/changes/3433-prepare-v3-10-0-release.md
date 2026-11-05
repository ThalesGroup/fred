---
schema: 1
title: "Review Swift v3.10.0 release preparation for Weaver"
impact: none
configuration: none
configuration_reason: "The upstream release text and capability manifest patch versions are retained; Weaver package and chart versions stay at 5.0.0."
no_action_reason: "The upstream release text and capability manifest patch versions are retained; Weaver package and chart versions stay at 5.0.0."
---

## Applicability

Weaver integrations of Swift commit 541f3275d. The public release history describes Swift v3.10.0, not a Weaver release.

## Prerequisites

Use matched Weaver 5.0.0 components and their existing supported migration chains.

## Configuration

No model-profile YAML catalog is restored. Weaver model sources and organization policy remain owned by Rust Control Plane.

## Upgrade

Deploy the merged Weaver components normally. Capability manifest versions carry the upstream patch increments; lockfiles are resolved from the merged Weaver manifests.

## Validation

Check package and chart versions remain 5.0.0, and inspect the generated pod inventory after deployment.

## Rollback

Use the existing Weaver rollback procedure. This release-preparation commit changes no persisted schema.

## Limitations

No Swift-to-Weaver data upgrade is certified by this note. The retired Swift operator-guide corpus and its release aggregate are not restored.

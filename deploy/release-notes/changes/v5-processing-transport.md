---
schema: 1
title: "Align v5 processing defaults with runtime transport validation"
impact: minor
configuration: production
configuration_reason: "Processing URLs and platform issuers now use HTTPS defaults; HTTP remains an explicit local override."
after: [v5-standard-chart-and-monitor]
---

## Applicability

Fresh v5 platforms using the standard chart, including the first alpha.

## Prerequisites

A reachable TLS ingress or gateway for Control Plane, a trusted identity issuer
and object storage. The Control Plane HTTP Service itself does not terminate TLS.

## Configuration

Replace `https://your.host/control-plane/v1` and
`https://identity.example.test/realms/app` with your platform addresses. Keep the
issuer consistent across security settings and processing/preparation identities.
Both processing implementations retain their HTTPS validation. See
[processing transport](../../charts/fred/README.md#your-values-file) for the
explicit local HTTP overrides; the k3d factory owns that local-only posture.

## Upgrade

Use the corrected chart for a fresh installation. No runtime validation is relaxed
and no database change is introduced.

## Validation

Check that the rendered processing settings pass both application validators,
then verify ingestion on the target platform. Helm schema validation alone does
not execute application transport validators.

## Rollback

Restore a previously accepted values file with reachable, transport-compatible
addresses. Do not revert to HTTP without the deliberate local-only opt-in.

## Limitations

Placeholder URLs pass configuration validation but must be replaced with real,
reachable platform endpoints before deployment. No deployment is performed here.

---
schema: 1
title: "Organization conversation diagnostics with owner consent"
impact: minor
configuration: production
configuration_reason: "An organization Admin enables capture and grants organization_observer; runtime private storage must support erasure."
---

## Applicability

Weaver deployments with a registered Python runtime and its preparation/workload identity.
Capture is disabled until an organization Admin enables it.

## Prerequisites

Initialize a fresh Weaver PostgreSQL schema and apply the packaged runtime migrations.
Runtime object storage must support reads, writes and erasure. Use the existing
workload registration and lifecycle worker; there is no OpenFGA dependency.

## Configuration

The organization Admin sets capture, sampling, retention and the storage cap,
and assigns the `organization_observer` role. Observers inspect organization
metadata; reading content additionally requires revocable owner consent covering
the exchange. Admin or platform roles alone do not grant content access.

## Upgrade

Use Weaver's standard fresh-schema deployment. Keep capture disabled until the
runtime, Control Plane and frontend are deployed together. There is no Swift
mixed-replica upgrade protocol or local authentication bypass.

## Validation

Grant an observer in one organization, enable capture, and run a conversation.
Check that metadata is visible only in that organization, content is unavailable
before owner sharing, and revocation closes it again. Delete the conversation:
diagnostics become unavailable immediately and deletion completes after stored
evidence is erased. The chat never offers to keep diagnostics.

## Rollback

Disable capture before reverting the deployment. Follow Weaver's schema policy;
do not remove conversation ownership or erasure constraints.

## Limitations

Capture is best effort. Storage or queue saturation may leave partial evidence,
reported by the inspector. OpenTelemetry span identities support correlation;
private HTTP/SSE evidence is not automatically exported to an OTLP collector.

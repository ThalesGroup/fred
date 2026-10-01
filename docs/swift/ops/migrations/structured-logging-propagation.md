---
schema: 1
title: "Correlate admitted delegated calls across Fred services"
impact: minor
configuration: none
configuration_reason: "Existing delegation switches govern diagnostic context; no new option is introduced."
---
## Applicability

Delegated first-party runtime REST/MCP calls and Fred receivers accepting delegated grants.

## Prerequisites

Deploy the output and local-context layers first. Existing workload provisioning and delegated authentication must already be valid.

## Configuration

No new setting. Retain existing `security.delegation` activation. Proxies must permit the bounded `X-Fred-Log-Context` header where delegated calls pass; its schema and exact bounds are in observability §6.1.

## Upgrade

Upgrade sender and receiver in either order. An older receiver ignores metadata; an older sender simply supplies none. Updated delegated transports stop following redirects to keep context and authority at their configured destination.

## Validation

Follow a delegated request by correlation ID across runtime, tool mount and inner route. Request IDs must differ per receiver; admitted principal/grant identity must win. Invalid metadata must leave valid business responses unchanged. Check an ordinary bearer call and disabled delegation for absence of inherited fields. Focused offline tests cover real request building, MCP HTTP traffic, shared-client isolation and redirect confinement.

## Rollback

Roll back this layer on either side. The other side continues valid authentication and business calls without shared diagnostic context. No data migration is required.

## Limitations

Context is diagnostic metadata, never authority. Legacy bearer forwarding, external/no-token tools and token endpoints do not propagate it. Unsupported MCP transports remain unsupported. GKE/proxy and collector validation was not performed; run the severity/timestamp/field-filtering canary during rollout.

---
schema: 1
title: "Expose agent pods through an optional Gateway API HTTPRoute"
impact: none
configuration: local
configuration_reason: "Only the optional agent-pod chart values and schema change; existing pod values and Fred chart values remain valid without changes."
no_action_reason: "The option is disabled by default, so a normal chart upgrade renders the same resources; Gateway activation is an optional later step."
---
## Applicability

Deployments that use Fred's published `agent-pod` chart. Existing releases remain
unchanged when `httpRoute.enabled` is omitted or false.

## Prerequisites

Optional activation requires a Gateway API v1 controller and a Gateway listener
that accepts HTTPRoutes from the agent pod namespace and the browser-facing
hostname. The pod's `configuration.app.base_url` and Fred's
`runtime_catalog_sources[].ingress_prefix` must be the same canonical path.

## Configuration

To activate the route, set `httpRoute.enabled: true`, `httpRoute.parentRefs`
with the Gateway name and namespace, and `httpRoute.hostnames` with the Fred
browser hostname in the agent pod chart values. Set `httpRoute.requestTimeout`
when streaming needs a longer request timeout, if the Gateway controller
supports it. The chart forwards the pod's base path to its own Service.
No new Secret or Fred Control Plane setting is introduced.

## Upgrade

Upgrade the `agent-pod` chart normally. Current values render no HTTPRoute.
For optional activation, add the values above and upgrade that pod's release
using the chart version that includes this feature. A separately maintained
HTTPRoute for the same pod path should be removed during the switch so route
ownership remains clear.

## Validation

Render the release with `helm template` and confirm the HTTPRoute matches the
pod base path and targets its Service. After activation, check that the route
is accepted by the Gateway and that browser chat requests reach the agent pod.

## Rollback

Set `httpRoute.enabled: false` and upgrade, or restore the previous chart
version. No data migration is involved.

## Limitations

The chart cannot grant Gateway listener permissions or install Gateway API
CRDs. Request timeout support depends on the Gateway controller.

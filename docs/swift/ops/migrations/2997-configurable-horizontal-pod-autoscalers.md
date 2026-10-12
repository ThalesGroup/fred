---
schema: 1
title: "Optional Helm-managed Horizontal Pod Autoscalers"
impact: minor
after: [000-v3-4-0-release-preparation]
configuration: production
configuration_reason: "The Fred chart adds applications.<name>.autoscaling settings and their generated schema; optional activation requires cluster metrics and container resource requests."
---
## Applicability

Fred installations using the Helm chart, including deployments whose HPA resources
are currently managed manually. Autoscaling is disabled by default for every
application; ordinary upgrades require no activation steps.

## Prerequisites

For optional activation, the cluster must support `autoscaling/v2` and expose a
working Kubernetes resource metrics API. Set container resource requests for each
resource used by a utilization metric: CPU for the supplied examples, memory if
selecting a memory policy. Ensure cluster capacity supports the chosen limits.

When `fred-agents` can scale above one replica, its
`configuration.storage.object_store` must already use shared storage (`gcs` or
`minio`) with the required credentials and access to existing objects. The chart
rejects local object storage with an enabled HPA's `maxReplicas > 1`.

## Configuration

In the deployment's Helm values overlay, configure
`applications.<name>.autoscaling.enabled`, `minReplicas`, `maxReplicas`, `metrics`
and optional `behavior`. Set `applications.<name>.resources.requests` for the
selected metrics and ensure the target application and its Deployment are enabled.
The supplied policies are starting examples; review them for the actual workload.
See [the chart guidance](../../../../deploy/charts/README.md#horizontal-pod-autoscaling).

## Upgrade

Deploy normally with autoscaling disabled to retain chart-managed replica counts.

For optional activation, prepare the prerequisites and render the chart with the
deployment's values before upgrading. If an HPA already targets the Deployment,
record its policy and arrange its replacement or Helm ownership transfer before
activation; avoid competing autoscalers and resource ownership conflicts. Enable
autoscaling in the overlay and upgrade the release. The chart then omits the
Deployment's `spec.replicas`, allowing the HPA to manage the replica count.

## Validation

With autoscaling disabled, confirm the rendered chart contains no HPA resources.
After activation, confirm the rendered HPA targets the intended Deployment with
the chosen limits and metrics, and that the Deployment omits `spec.replicas`.
In the cluster, use `kubectl describe hpa <application-name> -n <namespace>` to
check available metrics and scaling conditions; exercise representative load and
confirm replicas stay within the configured bounds.

## Rollback

Disable the application's autoscaling and set its intended fixed `replicaCount`
in the overlay before upgrading, or roll back to the previous Helm release.
Verify the Helm-managed HPA is removed and the fixed replica count is restored.
Restore any previous manually managed HPA if it was replaced during activation.
This feature introduces no data migration; retain any shared storage configured
for `fred-agents` and its existing objects.

## Limitations

Only chart-managed Deployments support these HPAs, with CPU or memory resource
utilization metrics. Missing resource requests or unavailable metrics prevent
effective scaling. The example limits and behavior are not workload sizing
guarantees; enabling a previously disabled worker is a separate deployment choice.

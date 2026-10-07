## Why

The Fred Helm chart deploys the Knowledge Flow worker Deployments with fixed replica counts. Operators currently create HorizontalPodAutoscalers manually in GKE, so scaling policy is not versioned with the release values.

Tracking: to be linked to the existing GitHub issue or created before implementation.

## What Changes

- Add optional per-application HPA configuration to chart values, including replica bounds, resource metrics, and Kubernetes scaling behavior.
- Render an `autoscaling/v2` HorizontalPodAutoscaler targeting the configured application's Deployment.
- Add the supplied CPU thresholds and scaling policies as opt-in examples for the four Knowledge Flow worker roles in the chart's default values.
- Validate and document the new values; leave autoscaling disabled by default so existing installations retain fixed replica counts.

## Capabilities

### New Capabilities

- `helm-horizontal-pod-autoscaling`: optional, values-driven HPAs for chart-managed application Deployments.

## Impact

Fred Helm chart values, JSON schema, templates and chart documentation. No application runtime or Kubernetes API changes beyond rendering standard `autoscaling/v2` resources.

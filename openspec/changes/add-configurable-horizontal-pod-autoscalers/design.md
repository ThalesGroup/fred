## Context

`deploy/charts/fred/templates/deployment.yaml` renders Deployments from `applications.<name>`, and the chart values schema rejects unknown keys. Knowledge Flow's common and extraction worker Deployments are separately configurable; extraction workers inherit shared settings at render time. The supplied GKE policies use CPU utilization and per-role replica and rate limits.

## Goals / Non-Goals

**Goals:**
- Let each chart application opt into a Kubernetes HPA through its values.
- Preserve fixed replica behavior unless autoscaling is explicitly enabled.
- Support the supplied `autoscaling/v2` CPU targets and scale-up/down behavior.

**Non-Goals:**
- Enable autoscaling for every deployment by default.
- Introduce external/custom metrics or provider-specific controller resources.
- Change the application resource requests or worker concurrency settings.

## Decisions

- Place optional autoscaling settings on each `applications.<name>` entry so a policy can be set independently for each Deployment.
- Render an HPA only when that application's deployment and autoscaling are enabled. Use `applicationName` for its target and resource name.
- Keep the chart's `replicaCount` as the initial Deployment replica count; Kubernetes HPA owns subsequent scaling while present.
- Include the four supplied worker policies as disabled examples in the chart's default values. Environments opt in through their own Helm values, so the portable defaults remain inactive.
- Extend the chart's authoritative values schema and chart guide alongside the values and template.

## Risks / Trade-offs

- CPU utilization requires CPU requests on target containers; verify the worker values resolve requests before enabling the policies.
- HPA and a GitOps controller that continuously enforces Deployment replicas can conflict; operators must configure ownership consistently.
- HPA resources require the cluster's metrics API to report CPU usage.

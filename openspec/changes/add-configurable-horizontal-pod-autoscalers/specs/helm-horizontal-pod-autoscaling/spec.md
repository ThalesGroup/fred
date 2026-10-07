## Purpose

Define optional, values-driven HorizontalPodAutoscalers for applications deployed by Fred's Helm chart.

## Requirements

### Requirement: Optional per-application HPA

The chart SHALL render an `autoscaling/v2` HorizontalPodAutoscaler for an application only when that application's autoscaling is enabled and its Deployment is enabled. The HPA SHALL target that application's Deployment and SHALL use the configured minimum replicas, maximum replicas, metrics and optional behavior. When autoscaling is omitted or disabled, the chart SHALL NOT render an HPA and the Deployment SHALL continue to use `replicaCount`.

#### Scenario: Autoscaling is disabled by default

- **WHEN** chart values omit or disable application autoscaling
- **THEN** no HPA is rendered for that application
- **AND** its Deployment uses the configured replica count

#### Scenario: Application HPA is enabled

- **WHEN** an enabled Deployment has autoscaling enabled with replica bounds and CPU utilization target
- **THEN** the chart renders an `autoscaling/v2` HPA targeting the Deployment's configured application name
- **AND** the HPA contains the configured bounds, metric target and behavior

#### Scenario: HPA cannot target a disabled Deployment

- **WHEN** autoscaling is enabled for an application whose Deployment is disabled
- **THEN** chart rendering fails with an actionable validation error

### Requirement: Knowledge Flow worker policy examples

The chart's default values SHALL provide disabled, independent CPU-based HPA examples for the common, extraction-fast, extraction-medium, and extraction-rich Knowledge Flow workers using their respective replica bounds, CPU utilization targets, scale-up policies, and scale-down stabilization and policies.

#### Scenario: Render the four worker HPAs

- **WHEN** deployment values enable autoscaling for the Knowledge Flow worker Deployments and the chart is rendered
- **THEN** each of the four workers has an HPA targeting its corresponding Deployment
- **AND** each HPA reflects the policy configured for that worker role

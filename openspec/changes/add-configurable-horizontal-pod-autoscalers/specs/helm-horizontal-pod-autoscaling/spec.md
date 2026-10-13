## Purpose

Define optional, values-driven HorizontalPodAutoscalers for applications deployed by Fred's Helm chart.

## ADDED Requirements

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

### Requirement: HPA policy examples for chart Deployments

The chart's default values SHALL provide disabled CPU-based HPA policy examples for every chart-managed Deployment. The common, extraction-fast, extraction-medium, and extraction-rich Knowledge Flow workers SHALL use their respective replica bounds, CPU utilization targets, scale-up policies, and scale-down stabilization and policies supplied for those roles. Other Deployments SHALL have independently configurable example policies. All examples SHALL remain disabled by default.

#### Scenario: Render the four worker HPAs

- **WHEN** deployment values enable autoscaling for chart Deployments and the chart is rendered
- **THEN** each enabled Deployment has an HPA targeting its corresponding Deployment
- **AND** each HPA reflects that application's configured policy

#### Scenario: Scaling Fred Agents above one replica with local storage

- **WHEN** Fred Agents autoscaling is enabled with `maxReplicas` greater than one and its filesystem backend is local
- **THEN** chart rendering fails with guidance to configure shared storage

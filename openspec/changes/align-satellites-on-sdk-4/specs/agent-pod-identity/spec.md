# agent-pod-identity

## ADDED Requirements

### Requirement: An agent pod SHALL declare its own identity

Every `fred-runtime` agent pod SHALL set `app.runtime_id` in its configuration.
The field has no default: a pod configuration without it MUST fail to start
rather than fall back to a shared or derived value.

The value MUST be a lowercase slug — alphanumerics and dashes, starting with a
letter. A display string such as `Fred default agents` MUST be rejected.

#### Scenario: A pod configuration without runtime_id fails to start

- **GIVEN** a pod configuration whose `app:` block has no `runtime_id`
- **WHEN** the pod starts
- **THEN** startup fails with a validation error naming `runtime_id`

#### Scenario: A non-slug runtime_id is rejected

- **GIVEN** a pod configuration with `runtime_id: "Fred default agents"`
- **WHEN** the configuration is validated
- **THEN** validation fails on the slug pattern

### Requirement: Telemetry SHALL be attributed to the declaring pod

A pod's `runtime_id` SHALL be the `service` identity in both durable streams —
the log records it writes and the KPI events it emits. Two pods running the same
runtime MUST NOT report the same `service` value.

#### Scenario: Two pods are distinguishable in telemetry

- **GIVEN** two agent pods with `runtime_id` `fred-agents` and `fred-samples-agents`
- **WHEN** both emit KPIs and logs
- **THEN** their records carry `service="fred-agents"` and
  `service="fred-samples-agents"` respectively, in both streams

#### Scenario: A log line joins to its own KPI

- **GIVEN** a pod that has written both a log record and a KPI event
- **WHEN** the two are matched on `service`
- **THEN** they resolve to the same pod

### Requirement: A deployed pod SHALL carry runtime_id through its configmap

A Helm-rendered agent pod configuration SHALL include `app.runtime_id`, and its
value SHALL equal the `runtime_id` that the control-plane catalog declares for
the same pod.

#### Scenario: Rendered configmap and catalog agree

- **GIVEN** a chart that renders an agent pod configmap and a control-plane
  `runtime_catalog_sources` entry for that pod
- **WHEN** both are rendered
- **THEN** the pod's `app.runtime_id` equals the catalog entry's `runtime_id`

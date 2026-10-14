## Purpose

Gives every pod built on Fred's libraries — agent pods and Knowledge Base pods — an
official, published Helm chart, so it deploys on any cluster from its image and values alone.

## ADDED Requirements

### Requirement: Published generic pod charts

Fred SHALL publish an `agent-pod` chart and a `knowledge-base` chart as OCI artifacts, under
the same registry path and with the same version as each `fred` chart release. Neither chart
SHALL contain code, names or defaults specific to one pod.

#### Scenario: Install a pod from the published chart

- **WHEN** an operator runs `helm install` on `oci://ghcr.io/thalesgroup/fred-helm/agent-pod`
  at a released version, with a pod image and a values file
- **THEN** the pod runs with that image and that configuration, and nothing from another
  pod's repository is required

#### Scenario: A released Fred version carries both charts

- **WHEN** a `chart/v<version>` tag is published
- **THEN** `fred`, `agent-pod` and `knowledge-base` are all available at `<version>`

### Requirement: The operator supplies the image

The charts SHALL have no default image. Rendering SHALL fail with a message naming the
missing value when the image repository or tag is not set.

#### Scenario: No image given

- **WHEN** `helm template` runs without `image.repository` or `image.tag`
- **THEN** rendering fails and the error names the missing value

### Requirement: Pod configuration is validated at install time

`configuration` SHALL be mounted unchanged as the pod's configuration file. The chart's values
schema SHALL validate it against the configuration model of the library the pod is built on,
so that a misspelled or misplaced key fails before anything is deployed. The `knowledge-base`
chart SHALL also accept top-level sections the model does not declare, because the SDK loads a
pod's subclass of its model from the same file; every section the model declares stays strict.

#### Scenario: Misspelled configuration key

- **WHEN** a values file sets a key the pod configuration model does not define
- **THEN** `helm install` and `helm template` refuse the values and name the key

#### Scenario: Knowledge Base section of its own

- **WHEN** a Knowledge Base values file adds a top-level `webdav` section next to the SDK's
- **THEN** the chart renders it into the configuration file, and a misspelled key inside
  `knowledge_base` is still refused

#### Scenario: Valid configuration

- **WHEN** the configuration matches the model
- **THEN** the pod receives exactly that configuration as its configuration file

### Requirement: Credentials by reference

The charts SHALL read credentials only from Kubernetes Secrets, either a Secret the operator
names or environment variables read from existing Secrets. No credential SHALL be rendered
into a ConfigMap. Rendering SHALL fail when M2M is enabled and neither a Secret is named nor
an environment variable of the name the configuration gives the M2M secret is provided.

#### Scenario: Credentials missing

- **WHEN** the configuration enables machine-to-machine authentication and no Secret source
  is set
- **THEN** rendering fails and names the ways to provide one

### Requirement: Agent pod exposure and registration

The `agent-pod` chart SHALL expose the pod's HTTP port through a Service, expose its metrics
port when the configuration enables Prometheus metrics, and optionally route the pod's base
URL through an Ingress. After install, it SHALL print the `runtime_catalog_sources` entry that
registers the pod in Fred, filled in with this release's runtime id, service address and
ingress prefix.

#### Scenario: Install notes give the registration

- **WHEN** an agent pod is installed
- **THEN** the notes print a `runtime_catalog_sources` entry whose `runtime_id` equals
  `configuration.app.runtime_id` and whose `base_url` reaches this release's Service

### Requirement: Knowledge Base pod lifecycle

The `knowledge-base` chart SHALL run the pod's `run` command as a long-lived workload and its
`publish` command as a Job after each install, upgrade and rollback, which the operator can
disable. It SHALL create a Service only for metrics.

#### Scenario: Declaration published on upgrade

- **WHEN** a Knowledge Base release is upgraded with publishing enabled
- **THEN** a Job runs `publish` once, and the long-lived workload keeps running `run`

### Requirement: Install documentation ships with the chart

Each chart SHALL include a README, readable with `helm show readme`, that gives the install
command, what Fred must provide, the required values, the credentials and the addresses to
override.

#### Scenario: Read the documentation of a published chart

- **WHEN** an operator runs `helm show readme` on a published pod chart
- **THEN** they read which values they must set for their deployment

## Purpose

States what a Fred application's own Helm chart must provide, so that any provider's
application installs, registers and is configured the same way on any cluster.

## ADDED Requirements

### Requirement: Fred documents the application chart contract

Fred's guide for application providers SHALL state the contract an application's chart meets
and SHALL point to a published chart that meets it as the worked example.

#### Scenario: A provider packages a new application

- **WHEN** a provider reads the application section of Fred's forking guide
- **THEN** they find every point of this contract and a reference chart to start from

### Requirement: Application workloads stay inside the cluster

An application chart SHALL deploy the UI, and the service when the application has one, as
workloads behind ClusterIP Services, in any namespace, with no Ingress of its own: Fred's
frontend gateway is the only way in.

#### Scenario: Default install exposes nothing

- **WHEN** an application chart is installed with its default values
- **THEN** it creates no Ingress and no Service of type NodePort or LoadBalancer

### Requirement: The host origin is required

An application chart SHALL require the origin users open Fred at, and SHALL refuse to render
when it is missing or is not a bare origin.

#### Scenario: Host origin with a path

- **WHEN** the host origin is set to `https://fred.example.com/app`
- **THEN** rendering fails and names the expected form

### Requirement: Credentials by reference

An application chart SHALL read credentials only from Kubernetes Secrets the operator names
or references, and SHALL refuse to render when its service needs credentials and none is
given.

#### Scenario: No credentials

- **WHEN** an application with a service is rendered without any Secret source
- **THEN** rendering fails and names the ways to provide one

### Requirement: The install prints the registration

An application chart's notes SHALL print its registration for Fred's values — the
`registrations.applications.<app_id>` entry, catalog fields and `gateway` — with this
release's fully qualified Service addresses.

#### Scenario: Registration after install

- **WHEN** an application is installed in namespace `acme-apps`
- **THEN** the notes give `ui_upstream` and `service_upstream` as
  `<service>.acme-apps.svc.cluster.local` addresses, under one `app_id`

### Requirement: Validated values and documentation

An application chart SHALL ship a values schema that refuses unknown keys and a README,
readable with `helm show readme`, giving the install command, what Fred must provide, the
required values, the credentials and the addresses to override.

#### Scenario: Misspelled value

- **WHEN** a values file contains a key the chart does not define
- **THEN** `helm install` refuses it and names the key

### Requirement: Local deployment uses the same chart

The local k3d instance SHALL install the chart an application publishes, with only instance
values (fred-deployment-factory's `k3d-apps/<app>/` for Fred's open-source applications, the
application's `deploy/k3d/` otherwise), so that the local deployment exercises the chart
operators receive.

#### Scenario: Local deployment

- **WHEN** a developer runs `make k3d-app APP=<app>` or `make k3d-app DIR=<the application's checkout>`
- **THEN** the release is the application's own chart with only the instance's k3d values

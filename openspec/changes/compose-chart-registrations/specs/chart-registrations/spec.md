## Purpose

Defines how the fred chart takes the applications and Knowledge Base publishers a deployment serves, so that each one is declared once, by its own values file, and any number of them compose.

## ADDED Requirements

### Requirement: Registrations compose across values files

The fred chart SHALL take a deployment's registrations from `registrations.applications`, keyed by `app_id`, and from `registrations.knowledgeBasePublishers`, keyed by `client_id`. Entries from several values files MUST all be registered, without any file restating another's entries. An entry set to `null` MUST be unregistered.

#### Scenario: Two applications from two files

- **WHEN** the chart is rendered with one values file registering `thanos` and another registering `evaluation`
- **THEN** both applications are registered with the control plane and with the frontend gateway

#### Scenario: Removing one entry

- **WHEN** a later values file sets `registrations.applications.evaluation` to `null`
- **THEN** `evaluation` is registered nowhere and the other applications remain

#### Scenario: Nothing registered

- **WHEN** the chart is rendered with its default values
- **THEN** the control plane registers no application and no publisher, and the frontend gateway serves no application

### Requirement: One declaration feeds both halves of an application

The chart SHALL derive an application's control-plane catalog entry and its frontend-gateway entry from the same `registrations.applications.<app_id>` entry. The catalog entry MUST carry the entry's fields without `gateway`, under that `app_id`. The gateway entry MUST carry `gateway`'s fields under that `app_id`. Both MUST be ordered by key, so an unchanged set of registrations renders identically.

#### Scenario: Catalog and gateway agree

- **WHEN** `registrations.applications.thanos` declares its catalog fields and `gateway.ui_upstream`
- **THEN** the control plane's `application_sources` contains `thanos` with those catalog fields and no gateway field, and `FRONTEND_APPLICATIONS_JSON` contains `thanos` with that `ui_upstream`

#### Scenario: Stable rendering

- **WHEN** the same registrations are rendered twice, from values files given in a different order
- **THEN** the rendered control-plane configuration and frontend environment are identical

### Requirement: Knowledge Base publishers are registered by client

The chart SHALL register each `registrations.knowledgeBasePublishers.<client_id>` entry as a control-plane publisher with that `client_id` and the entry's `prefix`.

#### Scenario: Publisher registered

- **WHEN** `registrations.knowledgeBasePublishers.kb-fred.opentext.prefix` is `fred.opentext`
- **THEN** the control plane's `knowledge_bases.publishers` contains that client with that prefix

### Requirement: Invalid registrations are refused before deployment

The chart's values schema SHALL refuse an unknown key in a registration entry, an application entry without its required catalog fields or without `gateway.ui_upstream`, and a publisher entry without `prefix`.

#### Scenario: Misspelled field

- **WHEN** an application entry contains `ui_prefx`
- **THEN** rendering fails and names the field

#### Scenario: Application without a gateway

- **WHEN** an application entry has no `gateway.ui_upstream`
- **THEN** rendering fails

### Requirement: The former registration values are refused

The chart SHALL refuse to render values that register through the control plane's `platform.application_sources`, its `knowledge_bases.publishers`, or a `FRONTEND_APPLICATIONS_JSON` entry in the frontend's `env` or `extraEnvVars`. The message MUST name the `registrations` key to use instead.

#### Scenario: Former application list

- **WHEN** values set `applications.control-plane-backend.configuration.platform.application_sources`
- **THEN** rendering fails with a message naming `registrations.applications`

#### Scenario: Former gateway variable

- **WHEN** values set `FRONTEND_APPLICATIONS_JSON` in `applications.frontend.env`
- **THEN** rendering fails with a message naming `registrations.applications.<app_id>.gateway`

#### Scenario: Former publisher list

- **WHEN** values set `applications.control-plane-backend.configuration.knowledge_bases.publishers`
- **THEN** rendering fails with a message naming `registrations.knowledgeBasePublishers`

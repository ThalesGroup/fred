# Model routing Specification

## Purpose

Defines how a pod turns model catalog sources into routable profiles and exposes their identity and metadata for administrator controlled access.

## Requirements

### Requirement: A model catalog can discover chat models from a compatible endpoint

The catalog SHALL combine static YAML profiles and optional OpenAI-compatible discovery. By default, a configured source SHALL request `GET {base_url}/models` and read identifiers from `data[].id`. An administrator MAY override that URL; the effective URL MUST end in `/models`, and its parent SHALL become the inference base for generated profiles. The pod SHALL produce stable identities for valid identifiers. Static-only catalogs SHALL retain existing behavior.

#### Scenario: Mixed catalog

- **GIVEN** static chat profiles and a configured discovery source
- **WHEN** the source returns valid identifiers
- **THEN** both static and discovered models are advertised and routable

#### Scenario: Discovery-only catalog

- **GIVEN** a configured source returning two valid model identifiers and a declared default matching one of them
- **WHEN** the pod starts
- **THEN** both models have stable chat profile and capability identities, and the declared model is the pod's chat default

#### Scenario: Static catalog

- **GIVEN** a catalog with no discovery source
- **WHEN** the pod starts and serves its model catalog
- **THEN** its profiles and model entries are the same as before, without a discovery request

#### Scenario: Mixed gateway inventory

- **GIVEN** an allowlist naming a valid chat model and a gateway response containing excluded malformed or duplicate entries
- **WHEN** the pod starts
- **THEN** it validates and loads the selected chat model without treating excluded entries as profiles

#### Scenario: Changed endpoint

- **GIVEN** an administrator saves a different OpenAI-compatible `/models` URL for a configured source
- **WHEN** a pod next serves its catalog or a managed chat turn
- **THEN** it uses a verified inventory from that URL and routes generated profiles through its parent inference URL without a restart

### Requirement: Advertised discovered models match routable models

The pod SHALL advertise the same successfully resolved inventory it uses for chat routing. It SHALL NOT advertise a newly returned remote model until that model is routable. On a refresh failure, it SHALL preserve the last successful inventory. If startup discovery fails, it SHALL keep static profiles available so a saved administrator URL can be applied on a managed turn.

#### Scenario: Remote list changes after startup

- **GIVEN** a running pod with a resolved discovered inventory
- **WHEN** an administrator successfully refreshes the model list
- **THEN** the newly returned model is advertised and routable without a restart

#### Scenario: Discovery fails

- **GIVEN** an opted-in source times out or returns a malformed response
- **WHEN** the pod starts
- **THEN** static profiles remain available and a later managed turn can apply a saved administrator URL

### Requirement: Discovered model metadata is optional and advisory

The pod SHALL preserve each upstream model identifier as its wire name. It SHALL show a supplied human-readable name and supported context or token limit metadata in the admin Models view when those fields are valid. The absence of such fields SHALL leave the model selectable by identifier and SHALL NOT imply a context size or reasoning aptitude. Remote metadata SHALL NOT grant a team access or enable reasoning.

#### Scenario: Basic OpenAI model list

- **GIVEN** a response containing only the standard model fields including `id`
- **WHEN** an administrator opens the Models view
- **THEN** the model appears with its identifier and activation controls, and unknown limits are left undisplayed

#### Scenario: Extended model metadata

- **GIVEN** a response containing a valid display name and context window
- **WHEN** an administrator opens the Models view
- **THEN** those values appear as model details without changing model activation

### Requirement: Administrators can name advertised models after discovery

The admin Models view SHALL provide a display-name field for an advertised model. A platform administrator SHALL be able to save or clear a name through an authorized API. A saved name SHALL persist across requests and pod restarts and take precedence over gateway metadata in the admin view, team model choices and chat model picker. Clearing it SHALL restore the gateway name or existing identifier fallback. Naming SHALL NOT change the upstream wire id, routing identity or model access grants.

#### Scenario: Name a discovered model

- **GIVEN** a discovered model with a gateway name and no saved admin name
- **WHEN** a platform administrator saves a different display name in the Models view
- **THEN** the admin list and chat picker show the saved name immediately, while inference continues using the upstream id

#### Scenario: Clear a saved name

- **GIVEN** a discovered model with a saved admin name
- **WHEN** a platform administrator clears the name
- **THEN** the admin list and chat picker return to the gateway name, or the identifier fallback if the gateway did not provide one

### Requirement: Discovery uses existing access controls

Every discovered model SHALL enter the existing model capability catalog without an initial access grant. Administrators SHALL be able to enable it through the existing default-on and team controls. A turn SHALL remain subject to the existing model access and routing checks. A stored selection confirmed removed by a successful refresh SHALL route to the separate platform fallback without altering the saved choice. Other unknown or unauthorized selections SHALL retain existing access and drift handling.

#### Scenario: New model is not granted automatically

- **GIVEN** a newly discovered chat model
- **WHEN** a team attempts to use it before an administrator grants access
- **THEN** the existing model access check denies its use

#### Scenario: Previously selected model disappears

- **GIVEN** a stored selection for a discovered profile confirmed removed and an available platform fallback
- **WHEN** a chat turn resolves that policy
- **THEN** it routes to the platform fallback and keeps the stored selection unchanged

### Requirement: Administrators can distinguish manual and discovered models

The Models admin view SHALL separate manually declared models from models returned by discovery. The source of each model SHALL come from profiles actually added by the pod's discovery resolution and SHALL be included in the control-plane admin response. Both sections SHALL retain the same activation and team controls. If an advertised discovery source lacks registered state for URL management, the discovery status SHALL name that source rather than claiming no discovery is configured.

#### Scenario: Mixed model list

- **GIVEN** a pod advertises one static model and one discovered model
- **WHEN** an administrator opens Features > Models
- **THEN** each model appears in its corresponding section with its existing controls

#### Scenario: Static profile with a discovery-like identifier

- **GIVEN** a manually declared profile whose identifier resembles a generated discovery profile
- **WHEN** the Models view renders after discovery
- **THEN** that profile remains in the manual section

#### Scenario: Discovered models without registered source state

- **GIVEN** the capability list contains a discovered model and the discovery status has no source
- **WHEN** the Models view renders
- **THEN** it shows the discovered model and explains that its source is not registered for URL management

#### Scenario: One of several sources is not registered

- **GIVEN** two sources advertise discovered models and only one has registered URL state
- **WHEN** the Models view renders
- **THEN** it names the unregistered source while showing the registered source's controls

### Requirement: Administrators can override a discovery URL

The Models admin view SHALL show each source's YAML and effective URL, last successful check, and refresh result. Opening the view SHALL request a fresh inventory. Overrides SHALL persist and take effect without restarting pods. The view SHALL show new and confirmed removed model counts before model rows. New models SHALL start without a platform default-on grant. Confirmed removed models SHALL remain visible as unavailable, without new activation or selection. A failed refresh SHALL preserve the last successful inventory and SHALL NOT mark any model removed. Clearing an override SHALL restore the YAML URL.

#### Scenario: Save a URL

- **GIVEN** a discovery source configured in a pod and a platform administrator
- **WHEN** the administrator saves a valid `/models` URL
- **THEN** subsequent admin catalog reads and managed chat turns use that URL without restarting the pod

#### Scenario: Refresh fails

- **GIVEN** an attempted URL that times out or returns an invalid inventory
- **WHEN** the administrator saves it
- **THEN** the write reports failure, keeps the prior saved URL and verified inventory, and records no new removals

#### Scenario: Saved URL after a pod restart

- **GIVEN** a saved override and an unavailable YAML discovery endpoint
- **WHEN** the pod starts and a managed turn resolves its binding
- **THEN** startup succeeds and the pod loads models from the saved override before routing that turn

#### Scenario: Restore the YAML URL

- **GIVEN** a saved override
- **WHEN** the administrator clears it
- **THEN** subsequent catalog reads and managed chat turns use the source's YAML URL

#### Scenario: Inventory changes

- **GIVEN** a last successful inventory containing A and B
- **WHEN** a successful refresh returns B and C
- **THEN** the summary shows C as new and A as removed, C is disabled by default, and A remains visible as unavailable

### Requirement: A confirmed removed model falls back to the platform default

The platform SHALL provide a fallback chat binding independent of its forced chat binding. On a managed turn, when the selected profile is confirmed removed by a successful source refresh, the pod SHALL use the fallback, report the actual routed model, and keep the stored choice unchanged. A failed refresh, unknown profile, disabled model, or access denial SHALL NOT count as a confirmed removal. An unavailable fallback SHALL fail explicitly.

#### Scenario: Selected model disappears

- **GIVEN** a saved selection confirmed removed and an available platform fallback
- **WHEN** the next managed turn executes
- **THEN** it uses the fallback while the saved selection remains unchanged

#### Scenario: Discovery outage

- **GIVEN** a selected model in the last successful inventory
- **WHEN** the next refresh fails
- **THEN** it is not marked removed and the disappearance fallback is not applied

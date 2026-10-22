# Model routing Specification

## Purpose

Defines how a pod turns model catalog sources into routable profiles and exposes their identity and metadata for administrator controlled access.

## Requirements

### Requirement: A model catalog can discover chat models from a compatible endpoint

The catalog SHALL accept an optional OpenAI-compatible source whose configured inference base URL also serves `GET /models`. It SHALL read model identifiers from the response's `data[].id` and produce a stable chat profile for each distinct valid identifier. A catalog containing only static profiles SHALL retain its existing behavior. A discovery-only catalog SHALL be able to designate a chat default by upstream model identifier without defining any profile by hand.

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

### Requirement: Advertised discovered models match routable models

The pod SHALL use one successfully resolved inventory for its chat routing and model catalog response. It SHALL NOT advertise a newly returned remote model until that model is routable by the pod. If an opted-in source cannot be read or returns an invalid or ambiguous inventory at startup, the pod SHALL fail startup with an actionable error rather than advertise or route a partial inventory.

#### Scenario: Remote list changes after startup

- **GIVEN** a running pod with a resolved discovered inventory
- **WHEN** the remote list gains a new model without a pod restart
- **THEN** the pod does not advertise or route that model

#### Scenario: Discovery fails

- **GIVEN** an opted-in source times out or returns a malformed response
- **WHEN** the pod starts
- **THEN** startup fails and names the discovery source without exposing its credential

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

Every discovered model SHALL enter the existing model capability catalog without an initial access grant. Administrators SHALL be able to enable it through the existing default-on and team controls. A turn SHALL remain subject to the existing model access and routing checks. A model removed from the source after a pod restart SHALL not silently fall back to another model when referenced by a stored policy.

#### Scenario: New model is not granted automatically

- **GIVEN** a newly discovered chat model
- **WHEN** a team attempts to use it before an administrator grants access
- **THEN** the existing model access check denies its use

#### Scenario: Previously selected model disappears

- **GIVEN** a team policy referring to a discovered profile that is no longer in the resolved inventory
- **WHEN** a chat turn resolves that policy
- **THEN** the existing profile drift handling refuses the turn without substituting the pod default

## MODIFIED Requirements

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

## ADDED Requirements

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

# Spec Delta

## ADDED Requirements

### Requirement: Azure APIM discovery authenticates with pod-local credentials

A discovery source configured for Azure APIM SHALL use an Entra client-credentials token and the pod's APIM subscription key for model-list and model-detail requests. It SHALL NOT use `OPENAI_API_KEY` for that source or expose either credential in the catalog, admin response, persisted state, or logs. Sources without Azure APIM configuration SHALL retain their existing Bearer-key behavior.

#### Scenario: List and detail succeed with Azure APIM

- **GIVEN** an Azure APIM source with valid non-secret connection settings and both pod-local secrets
- **WHEN** the pod resolves `/models` and fetches a selected model's `/models/{id}` detail
- **THEN** both requests use an Entra access token and APIM subscription key for the configured gateway

#### Scenario: Missing credential fails closed

- **GIVEN** an Azure APIM source without its client secret or subscription key
- **WHEN** the pod attempts discovery or model detail
- **THEN** the operation fails without contacting the gateway or disclosing the missing secret's value

#### Scenario: Existing source is unchanged

- **GIVEN** a source configured without Azure APIM authentication
- **WHEN** the pod resolves discovery and fetches model detail
- **THEN** it continues to use `OPENAI_API_KEY` as its Bearer credential

### Requirement: Azure APIM discovered models are routable

An Azure APIM source SHALL generate chat profiles with the existing `azure-apim` provider and its configured non-secret inference settings. A model SHALL be advertised only when its generated profile can be constructed for inference. Static profiles and source-specific model filtering SHALL retain their current behavior.

#### Scenario: Discovered chat model is selected

- **GIVEN** an Azure APIM `/models` response with an allowed chat model and valid inference settings
- **WHEN** the pod advertises and selects that model
- **THEN** inference uses the model's wire identifier through the Azure APIM provider with pod-local credentials

#### Scenario: Incomplete inference settings

- **GIVEN** an Azure APIM source missing a setting required by the provider
- **WHEN** the catalog is validated
- **THEN** configuration fails before any unroutable discovered model is advertised

## MODIFIED Requirements

### Requirement: A model catalog can discover chat models from a compatible endpoint

The catalog SHALL combine static YAML profiles and optional named OpenAI-compatible discovery sources. When present, `discovery` SHALL be a nonempty list of sources, including for one endpoint; source IDs SHALL be unique. An explicitly configured pod chat default SHALL remain in `default_profile_by_capability` and refer to a manually declared profile. When no chat default is configured and exactly one manual chat profile exists, the pod SHALL use that profile as its effective chat default. Discovered profiles SHALL NOT count toward this inference; zero or multiple manual chat profiles SHALL leave the pod without an inferred chat default. By default, each configured source SHALL request `GET {base_url}/models` and read identifiers from `data[].id`. A platform administrator MAY override a standard source URL; the effective URL MUST end in `/models`, and its parent SHALL become the inference base for that source's generated profiles. An Azure APIM source MAY use an administrator override only when its URL remains on the configured origin and under the configured APIM resource path. Its configured Azure APIM inference settings SHALL remain authoritative. The pod SHALL produce stable identities for valid identifiers. Static-only catalogs SHALL remain usable without a discovery request.

#### Scenario: Mixed catalog

- **GIVEN** static chat profiles and a configured discovery source
- **WHEN** the source returns valid identifiers
- **THEN** both static and discovered models are advertised and routable

#### Scenario: Discovered models with a manual default

- **GIVEN** a configured source returning two valid model identifiers and a manually declared chat default
- **WHEN** the pod starts
- **THEN** both discovered models have stable chat profile and capability identities, and the manual profile remains the pod's chat default

#### Scenario: Sole manual chat profile

- **GIVEN** a catalog with one manual chat profile and no explicit chat default
- **WHEN** the pod serves its catalog or routes an unselected chat turn
- **THEN** it advertises and uses that manual profile as its effective chat default

#### Scenario: Sole manual chat profile with discovery

- **GIVEN** one manual chat profile, discovered chat profiles, and no explicit chat default
- **WHEN** the pod resolves discovery and routes an unselected chat turn
- **THEN** it advertises and uses the manual profile as its effective chat default

#### Scenario: No unambiguous manual chat profile

- **GIVEN** zero or multiple manual chat profiles and no explicit chat default
- **WHEN** the pod serves its catalog
- **THEN** it advertises no chat default, regardless of discovered profiles

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

#### Scenario: Several sources in one catalog

- **GIVEN** two discovery sources with distinct IDs and URLs in the same pod catalog
- **WHEN** both return valid models, including a shared wire model ID
- **THEN** each model retains a distinct source-owned identity and appears under its own URL management status

#### Scenario: Independent source revisions

- **GIVEN** a pod has two named sources and source B has a later refresh revision than source A
- **WHEN** the pod applies A's saved URL or rolls back an unsuccessful A activation
- **THEN** A changes according to its own revision and B's inventory, URL and revision remain intact

#### Scenario: Azure APIM source uses its configured endpoints

- **GIVEN** an Azure APIM discovery source with a configured `/v1/models` URL and inference settings
- **WHEN** the pod resolves discovery and advertises an eligible model
- **THEN** discovery uses that URL and inference uses the configured Azure APIM provider route


### Requirement: Platform administrators can override a discovery URL

The Models admin view SHALL show each source's YAML and effective URL, last successful check, and refresh result. Opening the view SHALL request a fresh inventory. Only a platform administrator SHALL edit a source URL; an Azure APIM override SHALL remain on the configured origin and under the configured APIM resource path; a feature manager MAY refresh its active URL. The pod SHALL independently reject a changed URL from a caller without platform management permission. Overrides SHALL persist and take effect without restarting pods. The view SHALL show new and confirmed removed model counts before model rows. New models SHALL start without a platform default-on grant. Confirmed removed models SHALL remain visible as unavailable, without new activation or selection. A failed refresh SHALL preserve the last successful inventory and SHALL NOT mark any model removed. If an agent pod catalog cannot be verified, the view SHALL show its identity and URL as a warning without persisting a source error; it SHALL still flag unregistered sources advertised by verified pods. Clearing an override SHALL restore the YAML URL.

#### Scenario: Save a URL

- **GIVEN** a discovery source configured in a pod and a platform administrator
- **WHEN** the administrator saves a valid `/models` URL
- **THEN** subsequent admin catalog reads and managed chat turns use that URL without restarting the pod

#### Scenario: Delegated feature manager refreshes the active URL

- **GIVEN** a feature manager without platform management permission
- **WHEN** they refresh discovery or inspect its source settings
- **THEN** the current URL is used and displayed, but its edit controls are unavailable

#### Scenario: Changed URL requires platform management permission at the pod

- **GIVEN** a caller without platform management permission
- **WHEN** they call the pod refresh endpoint with a URL different from the active source URL
- **THEN** the pod denies the request before contacting the new host

#### Scenario: A stale prepared token cannot restore an old URL

- **GIVEN** a feature manager prepared a catalog for URL A and an administrator later activated URL B
- **WHEN** the feature manager activates or rolls back the old token
- **THEN** the pod keeps URL B unless the caller has platform management permission

#### Scenario: Saved override after pod restart

- **GIVEN** a saved override and a restarted pod that has only loaded its YAML URL
- **WHEN** a feature manager requests refresh before the override is restored
- **THEN** the pod denies the URL change until a managed turn restores it or a platform administrator refreshes it

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

#### Scenario: Agent pod catalog cannot be verified

- **GIVEN** a configured pod is unreachable while another pod still responds
- **WHEN** an administrator refreshes the Models view
- **THEN** the view warns which pod catalog could not be checked, retains the last verified inventory, and confirms no removals or source failure from this outage

#### Scenario: Azure APIM URL changes within its gateway

- **GIVEN** an Azure APIM source and a platform administrator
- **WHEN** the administrator submits another `/models` URL under the configured APIM resource path on the same origin
- **THEN** the pod refreshes that URL with the existing APIM credentials and keeps the configured inference route

#### Scenario: Azure APIM URL cannot redirect credentials

- **GIVEN** an Azure APIM source and a platform administrator
- **WHEN** the administrator submits a `/models` URL outside the configured origin or resource path
- **THEN** the pod rejects the change before acquiring or sending any credentials, and the current inventory remains available

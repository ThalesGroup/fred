## MODIFIED Requirements

### Requirement: A model catalog can discover chat models from a compatible endpoint

The catalog SHALL combine static YAML profiles and optional named OpenAI-compatible discovery sources. When present, `discovery` SHALL be a nonempty list of sources, including for one endpoint; source IDs SHALL be unique. If a pod chat default is configured, it SHALL remain in `default_profile_by_capability` and refer to a manually declared profile. By default, each configured source SHALL request `GET {base_url}/models` and read identifiers from `data[].id`. A platform administrator MAY override each URL; the effective URL MUST end in `/models`, and its parent SHALL become the inference base for that source's generated profiles. The pod SHALL produce stable identities for valid identifiers. Static-only catalogs SHALL retain existing behavior.

#### Scenario: Mixed catalog

- **GIVEN** static chat profiles and a configured discovery source
- **WHEN** the source returns valid identifiers
- **THEN** both static and discovered models are advertised and routable

#### Scenario: Discovered models with a manual default

- **GIVEN** a configured source returning two valid model identifiers and a manually declared chat default
- **WHEN** the pod starts
- **THEN** both discovered models have stable chat profile and capability identities, and the manual profile remains the pod's chat default

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

## ADDED Requirements

### Requirement: Admin model binding selection uses advertised chat models

The admin Models view SHALL keep separate Catalog and Discovery tabs. The platform binding editor SHALL group selectable chat models by source, offering models whose effective provider settings can be represented by a validated platform `ModelBinding` and whose chat profiles are available across the relevant pods. It SHALL put manual provider and settings entry behind an advanced disclosure. Only platform administrators SHALL change or delete a platform binding. When all pods report their chat default state, a deployment with no usable pod chat default and no platform binding SHALL show a single-action modal every time a platform administrator selects the Models view, without suppressing it in browser storage. The dialog SHALL explain that a platform binding overrides team choices. The fallback description SHALL explain its use when a selected discovered model disappears or is decommissioned.

#### Scenario: Choose a discovered model

- **GIVEN** a discovered chat model advertised with a safe binding
- **WHEN** the administrator selects and saves it in the platform binding editor
- **THEN** its provider, wire name and inference settings are saved without manual form entry

#### Scenario: Unsupported catalog settings

- **GIVEN** a catalog model with settings outside the platform binding contract
- **WHEN** the administrator opens the model selector
- **THEN** that model is omitted from the selector and advanced manual configuration remains available

#### Scenario: No manual catalog and no platform binding

- **GIVEN** a deployment advertising only discovered models without a saved platform binding
- **WHEN** the administrator opens the Models view
- **THEN** a modal explains that a platform choice is required and offers to open the model binding editor without a postpone action

#### Scenario: Revisit without a default

- **GIVEN** an administrator dismissed the no-default warning without setting a binding
- **WHEN** the administrator selects the Models view again
- **THEN** the modal warning appears again

#### Scenario: Manual models without a declared default

- **GIVEN** a pod advertises manual models but declares no chat default and no platform binding exists
- **WHEN** a platform administrator opens the Models view
- **THEN** the required-choice modal appears

#### Scenario: Manual default declared

- **GIVEN** a pod declares a manual chat default and no platform binding exists
- **WHEN** a platform administrator opens the Models view
- **THEN** no required-choice modal appears

#### Scenario: Unverified inventory

- **GIVEN** an agent pod is unreachable and its manual models cannot be verified
- **WHEN** a platform administrator opens the Models view
- **THEN** the no-default modal is withheld until the inventory can be verified

#### Scenario: Delegated feature manager

- **GIVEN** a feature manager without platform administrator permission
- **WHEN** they open the Models view or attempt a direct platform binding write
- **THEN** they see no binding editor action and the write is denied

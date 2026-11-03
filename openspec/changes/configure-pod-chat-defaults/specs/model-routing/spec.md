## ADDED Requirements

### Requirement: Platform administrators can configure a chat default for each agent pod

The Models administration view SHALL provide a "Model defaults" panel with "Agent pods" first and "Platform" second. The Platform tab SHALL retain the manual provider/name/settings form for the global forced binding and explain that it imposes one model on all managed exchanges. The Agent pods tab SHALL show each configured enabled agent pod and offer only advertised chat profiles whose model is platform-enabled in a pod-specific default selector; the fallback selector SHALL further limit choices to manual chat profiles. The API SHALL reject new selections for models without platform-wide activation. Each selector SHALL initially show that pod's effective YAML value when one exists; a saved admin override SHALL replace the displayed selection. An existing YAML or saved choice that is no longer activated SHALL remain visible as the effective setting but SHALL NOT be offered as a new choice. Only platform administrators SHALL save or clear pod overrides. Saved pod settings SHALL persist without modifying the pod YAML.

#### Scenario: Different pod defaults

- **GIVEN** two configured pods with different chat catalogs
- **WHEN** an administrator selects a different available chat profile for each pod
- **THEN** each pod routes unselected managed turns to its own selected default

#### Scenario: No admin override

- **GIVEN** a pod with a YAML chat default and no saved admin pod default
- **WHEN** a managed turn selects no higher-precedence model
- **THEN** the YAML chat default is selected in that pod's admin dropdown and used for routing, as before

#### Scenario: Reset a pod override

- **GIVEN** a saved admin default for a pod
- **WHEN** the administrator clears it
- **THEN** the dropdown returns to the effective YAML chat default and the pod resumes using it

#### Scenario: Discovered default disappears

- **GIVEN** a saved discovered pod default that is no longer in the current pod catalog and a manual YAML default
- **WHEN** a managed turn starts
- **THEN** it uses the pod's manual fallback, or its manual YAML default when no fallback override exists, and the admin view identifies the saved selection as unavailable

#### Scenario: Choice precedence

- **GIVEN** a saved admin pod default and a valid user, instance, team or pod-agent model choice
- **WHEN** a managed turn starts
- **THEN** the higher-precedence choice wins; an existing global platform binding still wins over all choices

#### Scenario: Write protection

- **GIVEN** a feature manager without platform-administrator permission or a profile absent from the selected pod
- **WHEN** they try to save a pod default
- **THEN** the API rejects the write and leaves the previous default intact

#### Scenario: Inactive model is not selectable

- **GIVEN** a pod advertises an activated model and an inactive model
- **WHEN** an administrator opens the pod default or fallback selector
- **THEN** only the activated model is offered, and a direct API write selecting the inactive model is rejected

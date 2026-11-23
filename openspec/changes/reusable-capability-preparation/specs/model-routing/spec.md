# Spec Delta

## ADDED Requirements

### Requirement: Model catalog does not advertise a PPT vision capability flag

The model catalog SHALL expose routable model identities and routing metadata without a `supports_vision` field. Agent and platform PPT vision settings SHALL not filter or select chat profiles by vision support.

#### Scenario: Catalog and effective model responses

- **WHEN** a client reads available models, an effective model or the pod catalog
- **THEN** the response contains no `supports_vision` property or derived vision-profile list

#### Scenario: Legacy catalog configuration

- **GIVEN** a catalog configuration still contains a `supports_vision` value during rollout
- **WHEN** the pod loads it
- **THEN** model routing remains usable, the legacy value is ignored, and no vision metadata is advertised

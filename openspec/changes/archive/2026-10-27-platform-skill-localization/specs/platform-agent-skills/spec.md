## ADDED Requirements

### Requirement: Packaged skill presentation follows the interface language

The frontend SHALL display French or English titles and descriptions for packaged skills using i18n, with English or authored fallback. Runtime catalog and load provenance SHALL distinguish packaged skills from custom homonyms. Canonical names, commands, copied text, stored selection identity, English model metadata, bodies and argument hints SHALL remain unchanged.

#### Scenario: Localized invocation and historical activity
- **WHEN** the interface language changes between French and English
- **THEN** menus, composer/history badges, detail metadata, load activity and administration use the corresponding title and description
- **AND** commands and selection payloads retain their canonical names

#### Scenario: Custom homonym or missing translation
- **WHEN** a custom source uses a packaged name or reliable packaged provenance is absent
- **THEN** the frontend retains authored metadata rather than applying an unrelated translation

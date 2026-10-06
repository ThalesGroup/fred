## MODIFIED Requirements

### Requirement: A generic status badge preserves evaluation status display

StatusBadge SHALL render a label and exactly one of `success`, `error`, `warning`, `info`, or `neutral` using paired design-system color tokens. It MUST NOT depend on domain states or act as a removable input chip. Hosted applications SHALL own their domain-specific labels and tone mappings; the shared atom MUST remain available after retiring the built-in evaluation views.

#### Scenario: All badge tones render in both themes
- **WHEN** a consumer renders each supported tone in light and dark themed roots
- **THEN** each label remains readable with token-based foreground/background pairing and no remove action

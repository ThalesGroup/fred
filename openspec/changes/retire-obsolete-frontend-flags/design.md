## Context

See proposal.md for motivation and specs/frontend-feature-flags/spec.md for the observable contract. The control-plane Pydantic model generates both the configuration schema and bootstrap OpenAPI shape. The frontend TypeScript client and Helm chart schema are generated from those sources. The chart and local configuration already use only current flags; the chart can list the remaining default-off flags explicitly.

## Goals / Non-Goals

**Goals:**
- Remove retired fields at the Pydantic source and propagate the change through generated contracts.
- Keep the typed feature-flag object, current flags, default-off behavior, and shared frontend hook.

**Non-Goals:**
- Change application authorization, resource-space behavior, or the reserved information-systems flag.
- Replace the feature-flag mechanism with a generic untyped map.

## Decisions

- Delete the retired fields from `FrontendFeatureFlags` instead of filtering them after serialization. This makes configuration validation, bootstrap output, and generated clients agree on one source of truth.
- Regenerate `configuration.schema.json`, `values.schema.json`, OpenAPI, and the frontend client with existing repository commands; list the supported default-off flags in chart values. Generated files will not be hand-edited.
- Assert the exact set of supported bootstrap flags in the focused backend test. This guards both removal and continued support for current flags.

## Risks / Trade-offs

- [Existing private overlays include retired keys] They will fail strict chart validation. Update the operator migration note to direct removal of those keys before deploying the new chart.
- [Generated output changes beyond the two fields] Review the generated diff and keep only source-derived changes.

## Migration Plan

Operators remove retired flag keys from any private control-plane values overlay before upgrading. Install the chart and code together. There is no data migration. Rollback uses the previous chart and code; removed keys do not need to be restored.

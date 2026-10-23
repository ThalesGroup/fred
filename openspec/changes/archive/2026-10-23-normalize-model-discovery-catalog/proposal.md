## Why

The draft discovery feature uses two YAML keys for one or several endpoints and puts a competing chat default on a discovery source. A single optional list and the existing manual default keep deployment configuration predictable.

## What Changes

- **BREAKING for the unmerged discovery configuration:** `discovery` accepts only a nonempty list of endpoint mappings; `discoveries` and a lone `discovery` mapping are removed.
- Remove `default_model_id` from discovery sources. Keep the existing `default_profile_by_capability` string mapping and manual chat profile fallback.
- Preserve static catalogs without discovery, including their current default selection and routing behavior.
- Offer platform administrators a picker grouped by Catalog and Discovery for the platform binding, while keeping provider and settings entry in an advanced section. A verified deployment with no pod chat default and no platform binding requires a choice whenever the admin opens Models, including when manual models exist without a declared default. Binding writes require platform administrator permission because the advanced URL can redirect provider credentials.

## Capabilities

### Modified Capabilities

- `model-routing`: Define the optional list form and manual default for discovered catalogs.

## Impact

The agent catalog parser, sample YAML and Helm values, runtime and control-plane catalog projections, admin UI, routing tests, and operator documentation change. Existing static deployments need no YAML migration. The discovery option remains in the draft PR and has not shipped.

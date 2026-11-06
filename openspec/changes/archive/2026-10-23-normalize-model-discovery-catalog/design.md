## Context

The pod catalog already normalizes configured sources through `discovery_sources`, and consumers use that list. The unmerged draft accepted both `discovery` as a mapping and `discoveries` as a list. It also supported a source-local default that could compete with the manual default.

## Goals / Non-Goals

**Goals:** Keep static catalogs unchanged while making every opted-in discovery configuration use one list-shaped key. Keep chat default selection in the existing manual profile mapping.

**Non-Goals:** Selecting a discovered model as the pod default or changing the platform binding's existing routing precedence.

## Decisions

- Parse `discovery` only as a nonempty list when configured. Preserve the absent or `null` form for Helm's disabled default. Reject duplicate source IDs. The alternative mapping form would make a one-source deployment differ from a multi-source deployment and complicate edits.
- Keep `default_profile_by_capability` as a map of capability to static profile ID. Remove `default_model_id` from source configuration and its runtime fallback path. The alternative computed discovered profile ID is opaque and unstable under source or upstream ID changes.
- Continue using the existing normalized `discovery_sources` property internally, so refresh and URL override paths operate on the same source list regardless of length.
- Advertise a validated `ModelBinding` for each chat model whose effective settings fit the platform binding contract. Remove process-wide HTTP tuning from this projection and omit bindings with unsupported or inconsistent profile settings. Control-plane only offers a model if its chat profile is available across the relevant pods.
- Keep the Catalog and Discovery inventory tabs. The platform binding drawer starts with a selector grouped by Catalog and Discovery and places the existing provider/settings editor in a collapsed advanced section. A deployment with no pod chat default and no saved binding opens a single-action dialog every time a platform admin selects the Models view, provided all pods reported their default state. The refresh response derives that state from `default_chat_profile_id`; an older pod or an unreachable pod leaves the result unknown. The dialog explains that the chosen binding overrides team choices and opens the binding editor; it is not suppressed between visits.
- Restrict writes and deletion of the platform binding to platform administrators. Its advanced URL can redirect provider credentials, just like a discovery URL override. Feature managers retain the read-only model list and existing feature controls.
- Describe the manual fallback in terms of its trigger: a selected discovered model that disappears or is decommissioned.

## Risks / Trade-offs

- Draft deployments using the earlier discovery syntax need to convert it to the list form. This option has not shipped; existing static catalogs load unchanged.
- An opted-in catalog with no manual default can list discovered models, but a turn without another selected model has no pod default and fails explicitly.

## Migration Plan

Update the example catalog and Helm values before rollout. For one source, wrap its mapping in a list under `discovery`; for several, rename `discoveries` to `discovery`. Keep or set a manual `default_profile_by_capability.chat`. No change is needed for static-only deployments.

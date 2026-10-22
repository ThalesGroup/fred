## Why

An agent with no template of its own builds on the Fred template shipped with ppt_builder. A deployment cannot swap that template for its own visual identity without a code release. GitHub issue #2987 records the broader direction, platform-wide capability settings; this change is its first slice.

## What Changes

- In Admin > Features, a settings action on the ppt_builder row opens a drawer where a capability manager (platform admin or feature manager) can:
  - upload a platform default `.pptx`, within the same size limit as an agent template;
  - follow its background analysis;
  - review its slides and adjust them as an author does for an agent template (rename, include or exclude, change the type); these pattern edits are saved with the platform template and apply to every agent that builds on it;
  - choose the vision model that labels it, the platform's default model unless changed, or rules only;
  - re-run the analysis;
  - reset to the Fred template.
- The Fred template is always there underneath: it cannot be removed, and "Reset" goes back to it.
- New resolution order for building a deck:
  1. the agent's own template;
  2. the platform default template, with the manager's pattern edits;
  3. the built-in Fred template.

  A replacement takes effect only once its analysis has succeeded. While it is analysed, or if its analysis fails, agents keep the previous platform template (the Fred template when there was none). A platform analysis never blocks or suspends agents.
- The agent form shows "Template set by the administrator" with the file name when the agent has no template and a platform default is in effect, and its review shows that template's slides.
- Pattern edits saved on an agent with no template of its own are no longer applied. Pattern ids are positional, so they would hit unrelated slides of whatever template is in effect. The agent form never offered editing in that state. Such an agent builds with the manager's pattern edits of the platform template instead.
- fred-sdk: capability routes can check the organisation-level "manage capabilities" permission, and can get a model port that does not depend on a team.
- Control plane: the admin capability list exposes each capability's route base URL and which models support vision, so the admin page can reach the capability pod and offer vision models.
- Out of scope:
  - a per-team default template;
  - a platform default for the vision model that labels agent templates (agent labelling is unchanged);
  - the generic `platform_settings_fields` manifest pattern (#2987, part 2).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ppt-builder`:
  - adds platform default template requirements;
  - updates template resolution and the agent form's no-template state.

  The capability spec is introduced by the in-flight `ppt-builder-capability` change, in the same PR. That change is archived first, so this delta applies on top of it.

## Impact

- **fred-sdk:** `CapabilityTeamAuthorizer` gains a capability-manager check, and capability routes get a dependency for a teamless model port. Both need dated entries in `RUNTIME-EXECUTION-CONTRACT.md` §8, plus updates to `AUTHORING.md` and the `add-fred-capability` skill.
- **fred-runtime:** implements both, as an organisation permission check and a routed model port without a team.
- **ppt_builder capability:**
  - new `/platform*` routes;
  - one Alembic revision in its own migrations: nullable `template_filename` and `overrides_json` columns;
  - template resolution in the middleware, through a pod-local snapshot.
- **Control plane:** `CapabilityEnablementItem` gains `route_base_url` and `vision_profile_ids`, with a `CONTROL-PLANE-PRODUCT-CONTRACT.md` entry and a regenerated `controlPlaneOpenApi.ts`.
- **Frontend:**
  - a platform panel registry for capability plugins;
  - the FeaturesPage settings action;
  - the ppt_builder platform drawer;
  - the agent form's default template line;
  - a regenerated ppt_builder client;
  - i18n fr/en.
- **Docs:**
  - Help Center fr/en, for capabilities (admin side) and agents;
  - the #2679 migration note: operations impact, with an optional activation and a capability table migration.
- **Delivery:** ships inside the ppt_builder PR (#2679), not after it.

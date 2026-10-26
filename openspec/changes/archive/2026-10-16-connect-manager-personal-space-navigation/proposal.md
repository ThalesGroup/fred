## Why

After demo provisioning, Priya can see Demo and fredlab through manager, but the
existing personal-space navigation has no manager consumer. Restore that entry
without redesigning Fred or introducing a manual space-creation workflow. The completed prerequisite establishes that a person belongs to at most one organization
on a Fred instance and enters that organization automatically after admission.

Tracking: [#3092](https://github.com/ThalesGroup/fred/issues/3092), on
`weaver`. This is the navigation prerequisite to the separate Resources
integration, not the broader `simplify-corpus-authorization` conversion.

## What Changes

- Reuse the existing personal-space entry, shared navigation components, labels,
  avatars, search and styles. Keep the existing manager organization/team/project
  inventory; do not add a separate manager UI or creation button.
- Open the personal space of that organization, creating it only on that
  explicit navigation action and only with an explicit creation entitlement. Repeated visits reuse the same UUID and never
  repair revoked roles. Login, consent, import and list requests remain read-only
  with respect to personal-space creation.
- Extend the existing `POST /me/personal-space` contract to return an accessible
  existing space (200) or a newly created space (201). Both return generated types.
- Expose the managing organization in the generated membership response so
  personal spaces can be associated with their organization without inheriting
  that organization's content or guessing from identifiers.
- Keep team/project selection and the selected-space detail on manager data;
  cover Priya's first visit, repeat visit, account switch and access refusals.

No Resources, agents, conversations, settings or other product page is activated
by this lot. No document data, quota or task API is added. Those consumers remain
unmounted; no empty substitute page is introduced. The current selected-space
detail remains the destination until its next complete feature is connected.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `control-plane-provisioning`: extend the imported-person journey with existing
  personal-space navigation and current-authority reuse of that space.

## Impact

Manager personal-space service/API and generated OpenAPI; frontend manager slice,
Home navigation, selected-space handling and their tests; existing browser journey.
The implementation updates arc42 chapters 2, 3, 4, 9 and relevant A1-A3 references,
plus the migration note. The unique-organization prerequisite shipped in `1ccb47962`. This lot adds the
organization-only `personal_space_creator` role, declarable in bundles and managed
by existing organization role endpoints, plus an additive pinned-model upgrade.
The developer authorized implementation and publication of the preceding lot;
this new lot ends with a local commit.

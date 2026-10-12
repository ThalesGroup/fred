---
schema: 1
title: "Agents marketplace UI: publish from the agent card, browse, like and import, admin Marketplaces page"
impact: none
configuration: none
configuration_reason: "Frontend pages, translations and Help Center content only; no configuration keys, defaults or chart values change."
no_action_reason: "The UI uses endpoints the marketplace backend notes already cover; it takes effect with the normal frontend deployment and publication stays off until a platform admin enables it."
after: [3044-agent-marketplace]
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure; the
control plane and agent pods from `3044-marketplace-publication-settings` and
`3044-agent-marketplace` are deployed.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

- **Administration > Marketplaces** lists every team following Default
  (publishing off, quota 5).
- With publication enabled for a team, its editors see **Publish to the
  marketplace** in an agent card's menu; the published agent appears on
  **Marketplace > Agents**, where another user can like it, open its details
  and import it into one of their teams.
- The Duplicate dialog prefills `<name> (copie 1)` / `<name> (copy 1)`, and
  "Copy to..." names a conflicting copy in the user's interface language.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.

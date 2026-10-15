---
schema: 1
title: "Platform access whitelist lists individual exceptions and adds people through a dialog"
impact: none
configuration: none
configuration_reason: "One optional query parameter and a new sort order on an existing administration endpoint, plus frontend changes; no configuration key, default or chart value changes."
no_action_reason: "The new query parameter is optional and defaults to the previous behaviour; no schema or stored data changes, and the control-plane backend and frontend follow the coordinated release rollout."
---
## Applicability

Fred deployments where platform access administration is available (user sign-in and permission checks enabled).

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required. There is no database migration.

Two behaviours of `GET /admin/platform/access/users` change for anyone calling it directly:

- It accepts the optional query parameter `exceptions_only` (default `false`). When `true`, the returned page and `total` cover only users holding an individual exception.
- Without `exceptions_only`, rows are now ordered by username without regard to case, users without a username last, then by user id. They were previously ordered by user id. With `exceptions_only=true`, the most recently granted exceptions come first, that alphabetical rule breaking ties. A script paging through this endpoint keeps working; only the order of rows differs.

- Its `query` search now ignores accents as well as case ("helene" finds "Hélène" and the reverse). No database extension is needed.

The response shape does not change.

## Validation

As a platform administrator, open Platform access > Users: the table lists only the whitelisted users (people holding an individual exception), the most recently added first, each with the date they were added, the origin of that entry and, behind an "Other access" chip, what else gives the person access. Use "Add users" to search for a person who is not listed, add them, and check that they appear at the top of the table.

## Rollback

Use the normal rollback procedure; this change introduces no data migration. Roll the frontend back together with the control-plane backend: a frontend from this release talking to an older backend would have its filter ignored and would list every known user in the Users tab.

## Limitations

The list is filtered on individual exceptions only. People admitted by the rule, by an authorized team or as platform administrators are not listed unless they also hold an individual exception. The filtered listing sorts the set of individual exceptions by grant date on each request without a dedicated index; this is expected to stay cheap for a few thousand exceptions.

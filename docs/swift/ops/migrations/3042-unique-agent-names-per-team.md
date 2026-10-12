---
schema: 1
title: "Make agent names unique within each team"
impact: minor
configuration: none
configuration_reason: "No configuration key, chart value or permission changes; the rule is enforced by a database index and the control-plane API."
---
## Applicability

All Fred deployments. Only teams or personal spaces holding two or more agents
whose names differ at most by case or surrounding spaces are affected.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

To know beforehand which agents will be renamed, run this read-only query on
the control-plane database:

```sql
SELECT team_id, lower(trim(display_name)) AS name, count(*) AS agents
FROM agent_instance
GROUP BY team_id, lower(trim(display_name))
HAVING count(*) > 1;
```

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The control-plane database migration of the deployment
(revision `a4d85307ea0e`) trims every agent name, keeps the name of the oldest
agent of each colliding group and renames the others `<name> (2)`,
`<name> (3)`… in creation order, then adds the unique index. No agent is
deleted.

## Validation

The query above returns no row. In a team, creating an agent with the name of
an existing one (in another case) is refused under the name field.

## Rollback

Use the normal rollback procedure. Downgrading the control-plane migration
drops the index; renamed agents keep their new names.

## Limitations

Renamed agents keep their new names; users rename them if they prefer another
one. Names are compared with ASCII and Unicode case folding by PostgreSQL.

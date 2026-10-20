---
schema: 1
title: "Pod charts (knowledge-base, agent-pod) can be used as a Helm dependency"
impact: none
configuration: local
configuration_reason: "Only the generated agent-pod and knowledge-base values schemas change, to accept the `global` key Helm passes to a subchart; the Fred chart values and schema are untouched, and existing pod chart values validate as before."
no_action_reason: "Releases of the agent-pod and knowledge-base charts render the same resources; the knowledge-base README and install notes now name the `knowledge_bases.publishers` entry Fred already required."
---
## Applicability

Existing Fred deployments upgrading to this release, and charts that wrap the
agent-pod or knowledge-base chart as a dependency.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

`helm template` of a chart that declares `knowledge-base` (or `agent-pod`) as a
dependency succeeds with schema validation on; a misspelled key under the
dependency's values is still refused.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.

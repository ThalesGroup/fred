---
schema: 1
title: "Publish generic agent-pod and knowledge-base Helm charts"
impact: none
configuration: local
configuration_reason: "The new values files and schemas belong to the two new pod charts and to fred-sdk's generated Knowledge Base configuration schema; the fred chart, its values and every Fred configuration file are unchanged."
no_action_reason: "The new charts are additive: nothing deployed uses them until an operator installs a pod from them, so existing releases upgrade normally."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required. Agent pods and
Knowledge Base pods deployed from their own charts keep running unchanged; moving one to
`oci://ghcr.io/thalesgroup/fred-helm/agent-pod` or `knowledge-base` is optional and done
per pod.

## Validation

`helm show readme oci://ghcr.io/thalesgroup/fred-helm/agent-pod --version <version>`
prints the chart's install documentation.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.

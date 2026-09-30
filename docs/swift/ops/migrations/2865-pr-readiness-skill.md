---
schema: 1
title: "Add a repository PR readiness skill"
impact: none
configuration: none
configuration_reason: "This change only adds agent workflow instructions; application and Helm configuration are unchanged."
no_action_reason: "The skill is documentation for contributors and changes no deployed code, data, or runtime behavior."
---

## Applicability

Fred contributors may use the new skill while preparing or diagnosing a pull request. Existing deployments are unaffected.

## Prerequisites

No operator prerequisites are needed because this change adds only repository guidance.

## Configuration

No deployment configuration changes are required.

## Upgrade

Deploy Fred normally; the skill does not run in the deployed application.

## Validation

Validate the skill front matter with the skill validator and confirm it is discoverable through the repository skills directory.

## Rollback

Revert the documentation commit if the contributor workflow needs to be withdrawn; no application rollback is required.

## Limitations

The skill reports evidence available at the time it runs. It cannot replace manual acceptance work or make a red GitHub check green without a fix.

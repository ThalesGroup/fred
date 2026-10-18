---
schema: 1
title: "Align agent form tests with model reads and required usage"
impact: none
configuration: none
configuration_reason: "Only frontend test fixtures change; application configuration is unchanged."
no_action_reason: "No shipped application code or data changes; the correction only restores isolated test setup."
---
## Applicability

Frontend development and CI tests for the agent form.

## Prerequisites

No operator prerequisite applies because only test fixtures change.

## Configuration

No configuration changes apply because production code and settings are unchanged.

## Upgrade

Normal deployment is sufficient; no operator action is required.

## Validation

Run the agent form name, assistant and assistant-flow tests. Model query hooks
are isolated in the two unit suites, and name tests fill the required usage
statement before asserting whether Create is enabled.

## Rollback

Revert the test-only commit. Application behavior and data are unaffected.

## Limitations

This corrects test setup; it changes no UI behavior or Redux integration.

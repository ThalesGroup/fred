---
schema: 1
title: "Separate cached React consumer integration coverage from unit tests"
impact: none
configuration: none
configuration_reason: "Only test selection, CI orchestration and developer documentation change; production configuration is unchanged."
no_action_reason: "No shipped runtime code, APIs or stored data change."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Run `make -C libs/frontend test` without a React consumer cache. After
`make -C libs/frontend consumer-provision-react`, run
`npm --prefix libs/frontend run test:consumer:integration`; the published-token
archive regression must pass. CI runs the same regression after provisioning.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.

---
schema: 1
title: "Extend live validation of document access and conversation changes"
impact: none
configuration: none
configuration_reason: "Only the validation harness, tests and documentation change; deployed service configuration is unchanged."
no_action_reason: "No runtime behavior, schema or stored data changes are shipped. The new tests run against an existing deployment."
---
## Applicability

Operators and developers running the live validation campaign.

## Prerequisites

Running Fred services, demo identities and teams, Knowledge Flow ingestion and
embeddings, and the public test assistant with the `document_access` capability.
See `validation/README.md`.

## Configuration

Use the existing validation endpoint variables to target the intended deployment.
No chart or service configuration changes are required.

## Upgrade

Deploy normally. No migration or production data repair is included.

## Validation

Run `make validation-report`. Document access, revocation and conversation
freshness appear as a separate report group. Known defects can produce failures;
this change adds detection, not the product corrections.

## Rollback

Revert the validation change. The campaign cleans up its own disposable fixtures;
it does not change demo memberships or existing documents.

## Limitations

The HTTP tests do not cover browser upload state or inject OpenFGA outages.

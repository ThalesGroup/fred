---
schema: 1
title: "Prepare Fred v3.17.0 and audit dependency updates"
impact: none
configuration: none
configuration_reason: "Release notes, Python package versions and lockfiles do not change deployment configuration; the covered dependency updates change only frontend packages and Python lockfiles."
no_action_reason: "The covered frontend and Python dependency updates require no data migration or configuration change. This preparation takes effect through the normal release rollout; other in-range notes describe its required database migration and optional theme activation."
covers:
  - fecfa951da39daa32acc2914c0b781ccfcb8750c
  - b21209ad699ee94fbf223a0f9f5e89568fc998ec
  - 969c873f34ccb462b768cc37a650a2b00b94a6cb
---

## Applicability

Fred deployments upgrading from v3.16.0 to v3.17.0.

## Prerequisites

Follow the prerequisites in the other in-range migration notes.

## Configuration

No configuration changes are required by the release preparation or the covered dependency updates.

## Upgrade

Deploy the release normally after completing the required steps in the other in-range notes. The covered updates change i18next, KaTeX and locked Python dependencies for Knowledge Flow and the Word template capability; they do not add an operator step.

## Validation

Verify the frontend loads localized text and mathematical notation, Knowledge Flow starts, and a configured Word template remains available in chat.

## Rollback

Use the rollback instructions in the other in-range notes. The covered dependency updates introduce no data migration.

## Limitations

No additional deployment limitations identified for the covered updates.

---
schema: 1
title: "Organize Fred architecture around domains and user journeys"
impact: none
configuration: none
configuration_reason: "Only architecture documentation and its navigation, including the root README, change; no application or deployment settings change."
no_action_reason: "This documentation reorganization changes no runtime behavior, data or APIs."
---
## Applicability

Readers of Fred's architecture documentation.

## Prerequisites

No deployment prerequisites.

## Configuration

No configuration changes.

## Upgrade

No deployment action. Start reading at `docs/architecture/README.md`.

## Validation

Follow the architecture link near the top of the root README. Run
`make -C docs/architecture check` and follow the domain and journey links.

## Rollback

No runtime or data rollback applies.

## Limitations

Empty domain sections define an editorial structure, not implemented behavior.

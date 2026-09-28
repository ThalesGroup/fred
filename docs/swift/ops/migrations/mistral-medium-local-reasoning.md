---
schema: 1
title: "Fix reasoning requests for the local Mistral Medium profile"
impact: none
configuration: local
configuration_reason: "The bundled fred-agents models_catalog.yaml enables Mistral Medium reasoning and sets top_p to 1.0; production chart values have no Mistral Medium profile."
no_action_reason: "Production configuration and stored data are unchanged; ordinary deployment is sufficient."
---

## Applicability

Fred developers using the bundled Mistral Medium profile in the local agent pod.

## Prerequisites

No prerequisites beyond the normal local startup procedure.

## Configuration

The local profile declares `supports_thinking: true`, `reasoning_effort: high`,
and `top_p: 1.0`. The platform admin's existing per-model toggle still controls
whether reasoning is active. Production chart values are unaffected.

## Upgrade

Deploy or restart the local agent pod normally so it reloads the catalog.

## Validation

Enable reasoning for Mistral Medium in the platform admin UI, then complete a
short chat turn using that model without a model API error.

## Rollback

Restore the prior catalog and restart the local pod. No data migration is involved.

## Limitations

This change only updates the bundled local profile. Deployments that define
Mistral Medium in their own catalog must configure the profile separately.

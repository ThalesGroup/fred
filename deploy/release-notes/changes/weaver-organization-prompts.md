---
schema: 1
title: "Organization common prompts and agent creation settings"
impact: minor
configuration: none
configuration_reason: "Settings use existing organization Owner roles, model policy and runtime registration; no environment variable, secret or chart setting is added."
---

## Applicability

Fresh Weaver installations using matching Control Plane, Agent Pod, SDK and frontend
versions. This change does not provide a data upgrade from Swift or older Weaver.

## Prerequisites

Use compatible components: the runtime admission binding now carries the
organization common prompt, and agent creation uses Weaver model admission.

## Configuration

The organization Owner manages the two prompt tabs. Technical administration alone
does not grant this authority. The common prompt follows the execution space's
organization, including personal spaces and invited users. No local override exists.
Creation-assistant model selection uses existing organization and space policy;
conversation-title settings remain in their existing model policy.

## Upgrade

Initialize an empty database through the normal immutable migration chain, including
`0039_organization_prompt_settings.sql`, and deploy the matching components.
Do not rewrite SQLx history or reset shared data as part of this change. An unsaved
common prompt uses the relevant runtime's default; saving an empty string explicitly
suppresses that block. Saved text survives runtime default changes.

## Validation

With an organization Owner, save a common prompt and check a new agent turn in that
organization. Verify another organization remains independent and a paused turn
keeps its admitted text on resume. Check the creation-assistant meta-prompt, model
and reasoning settings by generating a draft in an authorized destination space.
Restoring the meta-prompt must preserve its model and reasoning choices. A generated
draft must not create an agent until the user saves the form.

## Rollback

Restore mutually compatible application and database state. Do not roll back only
the runtime contract or edit migration checksums. No automatic reverse migration
or data-preserving downgrade is supplied.

## Limitations

Runtime defaults can differ; the administration page identifies their provenance.
Missing defaults are reported as unavailable, not empty. Managed Graph invocation
APIs apply the common prompt; extensions calling a model directly outside those
APIs own their prompt composition. Local technical checks do not replace developer
UI reception or acceptance on a deployed platform.

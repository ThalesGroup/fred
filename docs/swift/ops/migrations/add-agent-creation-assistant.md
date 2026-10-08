---
schema: 1
title: "Creation assistant: draft an agent from a plain-language description"
impact: minor
configuration: local
configuration_reason: "Comments only: apps/fred-agents/config/models_catalog.yaml and deploy/charts/fred/values.yaml document the new optional reasoning_efforts profile field with a commented GPT-5.1 example; no key, value or default changes, so production values are unaffected. The assistant's model and reasoning effort are chosen in the admin UI, and without a choice each pod's default chat profile applies."
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. Each draft calls one chat model once:
the profile a platform admin picks in **Platform prompts > Creation
assistant**, else the pod's default chat profile. Its reasoning follows
the admin **Reasoning** setting (Off by default): for a profile declaring
`supports_thinking`, any level but Off keeps the profile's own
`reasoning_effort` (else its single listed level; with neither, the admin page
shows reasoning as unavailable for it), unless the profile lists selectable
levels in the new optional `reasoning_efforts` field, which then picks the
nearest listed level for the assistant's call only. No action is needed: no shipped profile
declares levels, so every thinking profile keeps an on/off switch. To offer
levels, list only those the provider accepts (for example
`reasoning_efforts: [low, medium, high]` on a GPT-5.1 profile with
`supports_thinking: true`; Mistral accepts only `high`). A pod refuses to start
if the field is set without `supports_thinking`, is empty, or leaves out the
profile's own `reasoning_effort`. Agent chat ignores the field. When reasoning is on and the call fails fast or is still running
after 23 seconds, the same call without reasoning starts beside it and the first usable draft wins. Drafts do not appear in `llm.call_latency_ms`, which stays limited
to agent model calls.

Token usage: each draft emits a new KPI event,
`agent.creation_assistant_completed`, with the calling user, the team and
`input_tokens`/`output_tokens`. The existing token-usage presets and the
analytics views built on them (per user and per team; over time, by model and
by agent) now count these events too, so token totals rise by the drafts'
usage after the upgrade; message, conversation and activity counts do not.
Dashboards or exports that read `agent.turn_completed` directly are
unchanged.

Pods read the admin settings from the control plane at
`platform.control_plane_url` (already set for managed agents) with the
caller's token. A pod without it drafts with its own defaults.

## Upgrade

The control plane adds one Alembic migration (`93427a5fe874`), which creates
the empty `creation_assistant_settings` table. It holds the optional admin
settings of the assistant (instructions override, model, reasoning effort
defaulting to `off`); no existing data changes.

1. Apply the control-plane database migrations as for any release that ships
   one (`alembic upgrade head`, run by the usual migration job or start-up).
2. Deploy the control plane and agent pods normally. Until a pod is upgraded,
   only the creation assistant answers 501 for its agents, and the admin
   **Creation assistant** tab reports that the default text is unavailable.
   Until the control plane is upgraded, upgraded pods draft with their own
   defaults.

## Validation

As a team editor, call
`POST /control-plane/v1/teams/{team_id}/agent-templates/{template_id}/draft-agent`
with a short `description`: the answer contains a non-empty `system_prompt`
and short `name`, `role` and `description`.
In the UI, the agent form header shows **Assistant** once a template
is chosen; applying a draft fills the ticked fields.
As a platform admin, `GET /control-plane/v1/admin/platform/creation-assistant`
returns `is_default: true`, the pod's built-in text and the selectable
`model_options`, and the admin **Platform prompts** page shows a
**Creation assistant** tab.

## Rollback

Use the normal rollback procedure. The migration's downgrade drops
`creation_assistant_settings`, losing only the saved settings; leaving the
table in place is harmless for the previous release.

## Limitations

A draft, settings read included, must finish within 50 seconds on the pod.
With reasoning on, Mistral Medium took 22 to 47 seconds per draft in testing,
against 7 to 10 seconds without; turn reasoning off if drafts are too slow. Ingresses with a read
timeout below 60 seconds may cut slow drafts short. A model chosen by an admin
that a pod no longer serves falls back to that pod's default chat profile.

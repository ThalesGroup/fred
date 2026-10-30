---
schema: 1
title: "Name new conversations with a generated title and choose its model"
impact: minor
configuration: none
configuration_reason: "The title uses the existing chat models, and its optional dedicated model is chosen in the admin UI and stored in the control-plane database; no configuration keys or defaults change."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

The control-plane database must accept the Alembic revision `b5d2e8f7c031`.

## Configuration

No configuration changes are required.

## Upgrade

Apply the control-plane Alembic migrations before starting the new control plane, as for any release that adds a revision. The revision adds one nullable column, `creation_assistant_settings.title_model_profile_id`. Existing rows keep NULL, which follows the platform chat model. The runtime contract gains one optional request field (`runtime_context.auto_title`) and one stream event (`session_title`).

## Validation

Start a new conversation and send a long first message. While the answer is streaming, the sidebar and the chat header switch to a short generated title (3 to 8 words) instead of the beginning of the message. Later messages do not change the title. Renaming the conversation by hand still works and is kept.

To choose the title model, open the features admin page, then Model defaults and the Platform tab. This needs the right to edit the platform prompt. Reload the page and check that the choice is kept. Start a new conversation as a plain team member: the title is generated, and the runtime log shows no `session_title_failed` event.

## Rollback

Restore the previous images. The extra column is ignored by earlier versions, and titles that were already generated stay as they are. To remove the column, run the Alembic downgrade to `f28c3e9ab641`.

## Limitations

Each new conversation makes one extra small call on the title model, or on the platform chat binding or pod default chat model when none is chosen. Its input is bounded to 600 characters and the title is short. If that call fails, or is still running 2 s after the answer ends, the conversation keeps the beginning of the first message as its title. A chosen model that a pod no longer offers falls back to that pod's default chat model, with a warning in the runtime log. Conversations created before the upgrade keep their current titles.

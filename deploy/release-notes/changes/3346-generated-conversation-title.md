---
schema: 1
title: "Name new conversations with a generated title"
impact: minor
configuration: none
configuration_reason: "The title reuses the chat model admitted for the first turn."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

The runtime and frontend must be upgraded together so the title event is recognized and saved.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the runtime and frontend together. The runtime accepts the optional `auto_title` context field and streams a `session_title` event. The frontend saves the generated title to the space-scoped conversation.

## Validation

Start a new conversation with a long first message. The sidebar and chat header should switch to a short generated title during the answer or shortly after it. Later messages should keep that title. Rename it manually and verify it stays unchanged.

## Rollback

Restore the previous runtime and frontend images. Existing generated titles remain saved.

## Limitations

Each new conversation may make one extra bounded model call using its admitted chat model. Input is limited to 600 characters. If generation fails or remains pending two seconds after the answer ends, the initial message-derived title remains. Existing conversations keep their titles.

---
schema: 1
title: "Vision chat models see the newest attached images on every turn"
impact: minor
configuration: none
configuration_reason: "The runtime reuses each model profile's existing supports_vision flag and Knowledge Flow its existing content store; no configuration key or default changes."
---
## Applicability

Existing Fred deployments upgrading to this release. Only ReAct agents whose
chat model profile declares `supports_vision` are affected.

## Prerequisites

Review the token budget and provider rate limits of every model profile that
declares `supports_vision`: conversations with images now use more input tokens.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. Knowledge Flow now keeps a bounded preview of each new
chat image (long edge at most 1568 px, JPEG for photos, PNG otherwise, never the
original) at `chat-attachment-previews/{document_uid}` in its content store, and
deletes it with the attachment.

Every model call of a vision agent now carries the conversation's 5 newest
images, on every turn. A 681x451 chart costs about 475 prompt tokens on
mistral-medium-latest, a 1568 px photo several times more; a turn with tool
calls pays them once per model call. Provider prompt caching reduces this from
the second turn. These tokens count in the per-user and per-agent token usage
views like any input token.

## Validation

With a vision model, attach a chart and ask two follow-up questions: fred-agents
logs `[VISION] 1 image(s) selected for the model requests` on each turn, and
Knowledge Flow answers `GET /knowledge-flow/v1/fast/preview/...` with 200.

## Rollback

Use the normal rollback procedure. The previous version does not delete
previews with their attachment: after a rollback, delete the
`chat-attachment-previews/` prefix in the Knowledge Flow content store.

## Limitations

Images attached before the upgrade have no preview: they answer from their
description, and each costs one 404 lookup per vision turn while it is among
the 5 newest images. A preview over 4 MiB is not kept. A preview of an
attachment never saved (browser closed between upload and save) is not deleted
with the session.

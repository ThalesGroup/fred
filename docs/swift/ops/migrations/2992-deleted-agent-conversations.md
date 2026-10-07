---
schema: 1
title: "Read-only conversations after managed agent deletion"
impact: none
configuration: none
configuration_reason: "The fix uses existing session runtime snapshots and browser ingress configuration. No configuration keys or database schemas change."
no_action_reason: "Deploy the updated Control Plane and frontend together. No data migration, backfill or operator action is required."
---

## Applicability

Saved conversations keep their history and become read-only after agent deletion.

## Prerequisites

Existing browser ingress routes to the runtime history endpoint must remain available.

## Configuration

No local or production configuration changes.

## Upgrade

Deploy the Control Plane and frontend from the same revision to expose and consume
`SessionDetails.agent_deleted` and `messages_url`.

## Validation

Open a conversation, delete its agent, then reload it. Verify history and the
`(deleted)` label remain visible, execution actions are disabled, and a live
agent conversation still accepts messages.

## Rollback

Roll back the application images together. No stored conversations are changed
by this fix; the previous deleted-agent history limitation would return.

## Limitations

Legacy sessions without a runtime snapshot can use a still-existing instance.
After its deletion, routing cannot be recovered reliably and the UI explicitly
shows history as unavailable. No runtime is guessed and no backfill is performed.

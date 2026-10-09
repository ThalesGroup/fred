---
schema: 1
title: "Read-only conversations after managed agent deletion"
impact: minor
configuration: none
configuration_reason: "The fix uses existing runtime snapshots and browser ingress routes. No configuration keys change."
---

## Applicability

Saved conversations keep their history and become read-only after agent deletion,
with a preserved agent name, a localized deletion suffix and visibly disabled chat composer.

## Prerequisites

Existing browser ingress routes to the runtime history endpoint must remain
available. Back up the Control Plane database before upgrading.

## Configuration

No local or production configuration changes.

## Upgrade

Run the normal Control Plane Alembic upgrade before deploying the updated backend
and frontend together. Revision `c82f6a91d043`, following `aac66348e27b`, adds nullable
`session_metadata.agent_display_name` and backfills names for agents still present
in the same team. The migration updates conversation metadata in place and leaves
activity timestamps unchanged. Its backfill runs once over existing sessions;
plan the usual database migration window for large installations.

The updated backend captures names at session creation and refreshes them to the
latest name in the same transaction as agent deletion. The frontend consumes the
additive name field and `SessionDetails.agent_deleted` / `messages_url`.

## Validation

Open a conversation, rename its agent, delete the agent, then reload the list and
conversation. Verify the latest name remains visible with the localized deletion suffix in both,
history is readable, and the disabled composer explains read-only mode. Hover or
focus the sidebar entry to read the deletion explanation. Confirm another live
agent conversation still accepts messages.

## Rollback

Roll back the application images together; the nullable column may remain in place.
If a schema downgrade is required, stop updated application readers/writers first
and downgrade the Control Plane to `aac66348e27b`. Only the display-name snapshots
are dropped; sessions and runtime history remain. The previous deleted-agent
history limitation would return with older application images.

## Limitations

Names of agents already deleted before this migration cannot be reconstructed;
those conversations use a localized generic name with the same read-only state.
Legacy sessions without a runtime snapshot can use a still-existing instance.
After its deletion, routing cannot be recovered reliably and the UI explicitly
shows history as unavailable. No runtime is guessed.

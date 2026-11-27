---
schema: 1
title: "Cancel and report interrupted managed chat streams"
impact: minor
configuration: none
configuration_reason: "The runtime, browser and Control Plane use existing routing, authentication and database settings."
---
## Applicability

Fred deployments with managed chat.

## Prerequisites

Use the existing Control Plane Alembic migration mechanism.

## Configuration

The existing runtime, model client and frontend configuration apply.

## Upgrade

Apply the Control Plane migrations through revision `a81d6c5072e4` before starting
the upgraded Control Plane. The migrations add a nullable result and indexed
references for the current stream and result segments. Deploy the upgraded
runtime and frontend with the usual procedure.

## Validation

In a local test environment, cut a managed chat connection before its terminal
event. Check the localized message in the open chat, `chat_stream_interrupted`
in `fred-agents`, and release of the affected provider HTTP request. Compare the
Stream interrupted catalogue result with Stop requested on a separate captured
turn that you stop using the chat button.

## Rollback

Roll back the applications with the usual procedure. The nullable columns can
remain in place during rollback. Downgrade the schema only after all upgraded
Control Plane replicas have stopped. Downgrading removes the new result values.

## Limitations

The runtime releases Fred's HTTP resources for the interrupted model call. The
model platform controls its own generation and billing lifecycle.

The result is recorded for new captured turns. Stop requested requires delivery
of the browser's stop signal.

---
schema: 1
title: "Inspect and export masked conversation trace evidence"
impact: none
configuration: none
configuration_reason: "The existing trace operator permission, runtime storage and capture settings govern masked reads."
no_action_reason: "The Runtime projects masked JSON from retained artifacts on demand. Existing captures need no backfill, and the original consent and storage formats continue to work."
---

## Applicability

Deployments that enable conversation trace capture.

## Prerequisites

Use a platform administrator or trace reader account and a retained trace.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the Control Plane, Runtime and frontend through the normal deployment procedure.

## Validation

Open an unshared trace and select an HTTP attempt, its LangChain evidence and an
SSE frame. Verify that masked LangChain input still colors alternating messages.
The turn tree shows recorded tool names and outcomes. Tool payloads and model
tool definitions remain masked. Toggle annotations and confirm Copy returns
valid JSON in either state. Use Copy as on an available masked provider request
and supply the provider URL before running the snippet.

Choose Masked export for a shared conversation and verify that the ZIP has
masked payloads and separate annotations. Select a mix of shared and unshared
conversations and choose Full export. Originals appear only where consent
covers them. For a single unshared conversation, Full export is disabled.

## Rollback

Use the normal rollback procedure. Stored originals use the same storage and consent formats.

## Limitations

Masked HTTP JSON requires a complete body of at most 4 MiB. Unknown or unreadable payloads can leave metadata only. Copied HTTP JSON may need edits before replay when required values are masked.

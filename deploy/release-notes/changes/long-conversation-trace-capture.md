---
schema: 1
title: "Bounded evidence for long conversation traces"
impact: minor
configuration: none
configuration_reason: "The organization capture settings and existing runtime object storage apply."
---

## Applicability

Organizations with conversation diagnostics enabled.

## Prerequisites

Use the standard Weaver conversation diagnostics deployment and private runtime
object storage with erasure support.

## Configuration

No additional deployment option. Compressed evidence blocks use the existing
organization retention and storage cap.

## Upgrade

Deploy Control Plane, runtime and frontend together using the fresh Weaver schema.
Keep capture disabled until rollout validation.

## Validation

Inspect a long managed conversation, including a paused and resumed turn. Check
paged model/tool/HTTP/SSE evidence and span parent links. Revoke consent and verify
that subsequent content reads are refused. Deleting the conversation erases all
its diagnostic blocks through the same lifecycle.

## Rollback

Disable capture before reverting deployment. Keep conversation ownership and
erasure constraints intact.

## Limitations

Queue, process or storage failures may leave incomplete evidence. The inspector
reports known degradation; capture does not make the chat depend on diagnostics.

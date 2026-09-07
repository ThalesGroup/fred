## Context

ReAct receives two independent failure signals on a `ToolMessage`: LangGraph's
`status == "error"` and Fred's typed `ToolInvocationResult.is_error`. The runtime event
adapter previously consulted only the artifact signal. In addition, a runtime provider
can return either a bare `ToolInvocationResult` or `(content, artifact)`; validating the
artifact's type establishes shape, not Fred provenance.

`ToolObservabilityMiddleware` already uses the correct OR classification. Fred's shared
tool renderer already owns conversion of a trusted `ToolInvocationResult` into text.

## Goals / Non-Goals

**Goals**

- Make ReAct event classification agree with tool observability.
- Keep exception and wrapper text out of user-facing events.
- Establish an explicit provider-error trust boundary without changing public types.

**Non-goals**

- Workspace persistence, objective retention, corpus construction, Deep Agents parity,
  or HITL changes; those remain in GitHub issue #2568.
- A provenance field on the public `ToolInvocationResult` contract.
- Changes to successful provider results.

## Decisions

### D1 — Either failure signal is authoritative

The event adapter uses a true OR:

```python
status_is_error = message.status == "error"
artifact_is_error = artifact is not None and artifact.is_error
is_error = status_is_error or artifact_is_error
```

A fallback expression would incorrectly ignore `status` whenever a non-error artifact is
present. This rule matches `ToolObservabilityMiddleware`.

### D2 — Provider error detail is removed at provider resolution

`ToolInvocationResult` is a shape contract, not a provenance marker. The
runtime-provider resolver therefore normalizes an error artifact into a new Fred-owned
result containing only the fixed generic message and `is_error=True`. It drops provider
blocks, sources, UI parts, and paired content before LangChain binding. Both bare and
tuple provider returns use this path.

This keeps the later event renderer simple: any typed error artifact reaching it is
Fred-owned. Adding public provenance metadata would widen the SDK contract for an
internal boundary and is unnecessary.

### D3 — One renderer feeds both user-facing events

For a Fred-owned typed error, the runtime renders the artifact and removes only Fred's
presentation prefix. Every other failed message becomes the same bounded generic text;
raw `message.content` is never inspected. The result feeds both
`ToolResultRuntimeEvent.content` and `FinalRuntimeEvent.content`.

## Risks / Trade-offs

- Provider-authored detailed error messages become generic. This is deliberate because
  neither provider tuple member proves it is safe for users; full exceptions remain in
  server-side observability.
- The change adds no I/O, awaits, shared state, retries, or label dimensions. Its added
  work is one small model reconstruction only on provider error paths.

## Migration Plan

No data or API migration. Rollback is a plain revert, although that would restore both
the false-success classification and provider-error disclosure risk.

## Open Questions

None for this slice. Remaining #2568 product work is tracked only on GitHub.

This checklist covers only the independently mergeable runtime correction in PR #2575.
All remaining planning, Workspace, corpus, and optional Deep Agents delivery is tracked
exclusively in GitHub issue #2568 and its linked dependencies.

## 1. ReAct tool-failure correctness

- [x] 1.1 Classify a tool result with the true OR of `ToolMessage.status == "error"`
      and `ToolInvocationResult.is_error`.
- [x] 1.2 Feed one trust-boundary renderer into both the per-tool and final runtime
      events; never inspect raw message content for an untyped failure.
- [x] 1.3 Mark returned typed error artifacts as errors in the tool tracing span.
- [x] 1.4 Sanitize both bare and tuple runtime-provider error artifacts before binding,
      dropping provider blocks, sources, UI parts, and paired content.
- [x] 1.5 Cover status/artifact disagreement, raw secret leakage, Fred-owned typed errors,
      span status, and provider-boundary sanitization with focused tests.
- [x] 1.6 Update `RUNTIME-EXECUTION-CONTRACT.md` §8.74 and validate this OpenSpec change.
- [x] 1.7 Run focused tests, `make code-quality`, `make test`, performance review, and an
      independent code review before push.

## Handoff

After this change merges, archive/sync this completed OpenSpec slice. Do not add future
#2568 tasks here; GitHub is the only live status and sequencing surface.

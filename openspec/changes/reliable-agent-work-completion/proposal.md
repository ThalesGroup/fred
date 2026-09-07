## Why

GitHub issue [#2568](https://github.com/ThalesGroup/fred/issues/2568) exposed a
reliability gap around multi-step work and real file publication. Investigation found
one independently mergeable runtime bug: a failed tool call could be reported as a
success when LangGraph set `ToolMessage.status == "error"` without a Fred error artifact.
The same path could also expose provider-controlled diagnostic content as user-facing
error text.

This OpenSpec change covers that completed runtime slice only. The remaining planning,
Workspace, corpus, and optional Deep Agents work is tracked exclusively in GitHub issue
#2568 and its linked dependencies, not in this repository checklist.

## What Changes

- ReAct classifies a tool call as failed when either `ToolMessage.status == "error"` or
  its Fred artifact has `is_error == true`.
- Untyped failures expose one bounded generic message instead of raw wrapper or exception
  text.
- Runtime-provider/MCP error artifacts are sanitized at their source boundary into a new
  Fred-owned generic error result; provider blocks, sources, UI parts, and paired content
  are discarded on the error path.
- Tool tracing spans report returned typed errors as failures, not only raised exceptions.

No Workspace API, planner, HITL, runtime event, or OpenAPI shape changes.

## Capabilities

### New Capabilities

- `agent-work-completion`: establishes the first black-box reliability rule for #2568:
  tool failures are classified truthfully and untrusted failure detail is never exposed.

### Modified Capabilities

None.

## Impact

- Runtime: `react_runtime.py`, `react_tool_binding.py`, `react_tool_rendering.py`, and the
  runtime-provider branch of `react_tool_resolution.py`.
- Tests: focused ReAct event, span-status, and provider-boundary regressions.
- Contract: compact current-state entry in `RUNTIME-EXECUTION-CONTRACT.md` §8.74.
- Tracking: all work beyond this slice remains solely in GitHub issue #2568.

# ISSUE-004 - V2 history windowing policy is inconsistent and hard-coded

Status: open
Owner: TBD
Target window: runtime hardening before production ramp

## Problem
The original concern (fully unbounded ReAct history) is no longer accurate in active V2 code: ReAct now trims history in the shared tool loop. However, the history policy is hard-coded and not runtime-configurable, and Deep runtime does not explicitly wire the same cap in this repository surface.

## Why it matters
- Behavior differs by runtime family instead of one explicit platform policy.
- History budget cannot be tuned per environment, model cost profile, or tenant constraints.
- Production tuning becomes code-change-driven rather than config/policy-driven.

## Current evidence
- `libs/fred-runtime/fred_runtime/react/react_tool_loop.py`: defines `_V2_MAX_HISTORY_MESSAGES = 10` and passes it to `build_tool_loop(..., max_history_messages=...)`.
- `libs/fred-runtime/fred_runtime/support/tool_loop.py`: applies trimming only when `max_history_messages` is provided.
- `libs/fred-runtime/fred_runtime/deep/deep_runtime.py`: builds Deep agents via `create_deep_agent(...)` without an explicit `max_history_messages` equivalent in this layer.
- `libs/fred-sdk/fred_sdk/contracts/models.py`: `conversation_history_max_turns = 20` applies to graph conversational state carry-forward, which is a different mechanism than ReAct message-loop windowing.

## Scope
- Active paths:
  - V2 ReAct tool-loop message window policy.
  - V2 Deep runtime parity with ReAct history policy.
  - Runtime-level policy/config contract for history budgeting.
- Not in scope:
  - Legacy `AgentFlow` paths under `ignored/`.
  - Claim that ReAct is currently fully unbounded (not true in active code).

## Proposed fix
- Introduce one runtime policy field for history window size (for example in runtime policy/config surface), with a safe default.
- Ensure ReAct and Deep both apply the same policy (or document intentional divergence explicitly).
- Add lightweight observability on effective history size per turn to support production tuning.

## Acceptance checks
- [ ] One documented policy controls V2 history window size without code edits.
- [ ] ReAct and Deep apply equivalent history-budget behavior (or have explicit documented rationale when different).
- [ ] Tests cover policy propagation and bounded message lists for both runtimes.
- [ ] Runtime logs/metrics expose effective trimmed history size for debugging and cost control.

## Promotion
Promoted to: none
Notes: This is a scoped correction of the original concern: the remaining issue is policy consistency/configurability, not absence of ReAct trimming.
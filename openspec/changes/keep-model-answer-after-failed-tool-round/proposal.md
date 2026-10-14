## Why

GitHub issue [#2588](https://github.com/ThalesGroup/fred/issues/2588): when every tool
call of a ReAct round fails, the runtime suppresses the model's streamed text and replaces
its final answer with the tool error (often the generic "This step failed unexpectedly and
could not be completed."). The model's own answer, written after it saw the failure, is
thrown away. This was observed with Deep's filesystem gate (a 12,392-character synthesis
lost) and twice on 2026-10-14 with `ppt_builder`: the per-turn tool-call cap blocked the
13th call and an 8,590-character answer was replaced by the generic message, and a tool
revision request (`is_error=True`) replaced the model's answer with the raw tool text. Every
ReAct or Deep agent with tools is exposed, and the cap case breaks the documented promise in
`tool_pacing.py` ("a normal answer, never a crash").

## What Changes

- The model's own non-empty answer produced after a wholly-failed round is the final
  response; its deltas stream normally.
- The tool error (Fred-owned typed text or the generic message, unchanged §8.74 boundary)
  becomes the final response only when the model produced no answer after the failure.
- Failed calls keep `is_error=True` on their tool-result events, so the trace still shows
  exactly which calls failed.
- The runtime no longer needs a policy-refusal marker (#2588's open question): a policy
  refusal and a genuine failure are handled by the same rule.

No runtime event, SDK type, OpenAPI shape, or configuration changes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-work-completion`: the final-event clause of the untrusted-failure scenario now
  applies only when no model answer follows the failure; a new requirement states that a
  model answer after a failed round is kept.

## Impact

- Runtime: `libs/fred-runtime/fred_runtime/react/react_runtime.py` (shared by ReAct and
  Deep runtimes).
- Tests: `libs/fred-runtime/tests/test_react_tool_error_final_2244.py`.
- Docs: `RUNTIME-EXECUTION-CONTRACT.md` dated entry superseding the final-response half of
  §8.42 and §8.74; one migration note (`impact: none`).

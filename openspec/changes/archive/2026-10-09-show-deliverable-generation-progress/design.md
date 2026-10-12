## Context

The existing ReAct loop emits each tool call only after the model has completed its arguments. A short preparation tool therefore appears before the long publication payload is composed. The frontend already animates executing tool rows and records completed results.

## Goals / Non-Goals

**Goals:** Keep the extra call small and side-effect-free, make the two calls ordinary independent rows, and preserve the existing publication contract.

**Non-Goals:** No custom composition state, timer, activity label, or changes to tool-row animation. Preparation does not generate the payload itself.

## Decisions

### Capability-owned preparation calls

Keep one short-title tool per deliverable capability. Its static acknowledgement creates no document, preview, or workspace file and asks the model to compose the publication arguments in the next round. Revisions repeat the call; direct publication remains valid. PPT preparation follows the configured-template gate.

### Existing tool trace

Do not change the frontend. The preparation and publication calls use the current tool trace, status, and animation.

## Risks / Trade-offs

- The preparation call adds one model round, tokens, and a tool-budget slot. Measure these separately from the publication call.
- The preparation call completes quickly; there is no continuous animation while the following model round builds the long payload. State this limit in the PR and demonstrate it accurately.
- Models can ignore tool-order instructions. The configured model run verifies the expected sequence, not universal compliance.

## Migration Plan

Deploy the agent pod through the normal path. There is no persistent data migration. Older callers may still invoke the publication tools directly.

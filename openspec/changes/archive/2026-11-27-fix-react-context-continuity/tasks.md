# Tasks

## 1. Reusable compaction

- [x] 1.1 Add a pure budgeted message helper with caller-supplied measurement, completed-turn projection, and protected active turn; verify focused tests cover large tool results, unchanged fitting history, and tool-call pairs.

## 2. ReAct integration

- [x] 2.1 Apply the helper to both ReAct history limits and reject protected context that exceeds either limit; verify middleware tests cover the continued task, explicit error, and unchanged checkpoint.
- [x] 2.2 Update the runtime execution contract to describe compaction and its budget-independent helper; verify the documented order matches the middleware.

## 3. Integration checks

- [x] 3.1 Run focused runtime tests, root code quality, and a full branch review against `swift`; record the results in the draft PR.

## Workflow follow-up

- Sync the delta spec and archive this change after review requirements are met.

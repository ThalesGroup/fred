## 1. ReAct and Deep model input

- [ ] 1.1 Add a shared UTC date instruction and dedicated model-call middleware in both fixed ReAct/Deep frames, including Deep children; verify focused tests capture the final model request with no tracer, with an admin override, and after capability middleware.
- [ ] 1.2 Defer `{today}` rendering in ReAct/Deep agent templates and attached context prompts to the same model call; verify focused tests show a consistent new date in the instruction and token after simulated UTC midnight, including a retry, while an admin override keeps its literal token.

## 2. Graph model input

- [ ] 2.1 Supply the same date instruction through Graph `NodeContext.invoke_model` and `invoke_structured_model`; verify focused streaming and structured-call tests capture the effective messages, leave caller messages unchanged, and keep an authored `{today}` literal.

## 3. Documentation and verification

- [ ] 3.1 Update `docs/swift/design/PROMPTS.md`, the creation assistant's prompt-authoring guidance, and the required operator migration note; verify they state that `{today}` is optional for explicit placement in ReAct/Deep templates, date awareness needs no token, admin and Graph tokens remain literal, and rollout needs updated pods but no prompt or data migration.
- [ ] 3.2 Run the focused runtime tests, `openspec validate --strict`, migration check, and one root `make code-quality` near completion; record exact outcomes and resolve relevant failures.
- [ ] 3.3 Review model-call cost and concurrency with the performance reviewer, then audit the full branch against `swift` and obtain an independent read-only review; verify findings are resolved or documented before readiness.
- [ ] 3.4 Reconcile the change artifacts with the final implementation, sync and archive the spec, and verify the archived capability and draft PR reflect the delivered behavior.

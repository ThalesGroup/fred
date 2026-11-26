## 1. ReAct and Deep model input

- [x] 1.1 Add a shared UTC date instruction and dedicated model-call middleware in both fixed ReAct/Deep frames, including Deep children; verify focused tests capture the final model request with no tracer, with an admin override, and after capability middleware.
- [x] 1.2 Remove the built-in `{today}` token from the SDK registry and runtime renderer, including internal extra-token overrides; verify focused tests show the text remains literal in existing agent templates and attached context prompts while other safe tokens still render and the middleware supplies the date after UTC midnight and on retry.

## 2. Graph model input

- [x] 2.1 Supply the same date instruction through Graph `NodeContext.invoke_model` and `invoke_structured_model`; verify focused streaming and structured-call tests capture the effective messages and leave caller messages unchanged.

## 3. Documentation and verification

- [x] 3.1 Remove `{today}` from the three bundled agent prompts and the creation assistant's prompt-authoring guidance. Update `docs/swift/design/PROMPTS.md` and the required operator migration note; verify they explain the retired token, literal existing stored text, UTC-only date behavior, Graph helper coverage, and updated-pod rollout without prompt or data migration.
- [x] 3.2 Run the focused runtime tests, `openspec validate --strict`, migration check, and one root `make code-quality` near completion; record exact outcomes and resolve relevant failures.
- [x] 3.3 Review model-call cost and concurrency with the performance reviewer, then audit the full branch against `swift` and obtain an independent read-only review; verify findings are resolved or documented before readiness.
- [ ] 3.4 Reconcile the change artifacts with the final implementation, sync and archive the spec, and verify the archived capability and draft PR reflect the delivered behavior.

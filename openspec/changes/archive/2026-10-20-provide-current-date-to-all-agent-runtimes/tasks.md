## 1. Runtime context

- [x] 1.1 Generate a shared current UTC date instruction at call time.
- [x] 1.2 Inject it into ReAct/Deep system prompts and both Graph model invocation paths without mutating stored prompts or caller messages.
- [x] 1.3 Remove the superseded generic prompt date lines while keeping the `{today}` token renderer.

## 2. Verification and documentation

- [x] 2.1 Cover saved prompt overrides, Graph streaming and structured messages, and date refresh with focused tests.
- [x] 2.2 Update prompt documentation and migration guidance; validate the OpenSpec change and run relevant checks.
- [x] 2.3 Review the full PR, reconcile the spec, and archive the change.

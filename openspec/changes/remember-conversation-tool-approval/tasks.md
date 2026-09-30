## 1. Scoped browser grants

- [ ] 1.1 Add local-storage helpers keyed by user, agent instance, and conversation, with validated tool names and safe failure behavior; verify storage and isolation with focused tests.
- [ ] 1.2 Clear grants when a conversation is deleted; verify the deletion path removes only that conversation's key.

## 2. Managed HITL behavior

- [ ] 2.1 Render neutral, vertically stacked HITL choices and the third approval action only for tool approvals with named pending calls; verify question skip and approval actions in the component test.
- [ ] 2.2 Make the third action resume as `proceed` and remember only displayed gated tool names after the runtime accepts the resume; verify the outgoing payload and storage timing.
- [ ] 2.3 Auto-resume a later approval only when every gated name has a stored grant, after the current stream settles; verify same-tool, mixed-batch, different-conversation, and failed-resume cases.

## 3. Contracts and verification

- [ ] 3.1 Align the existing agent-question OpenSpec and compact UX contract with the final shared layout; verify `openspec validate --strict` for both HITL changes.
- [ ] 3.2 Manually verify approval reuse and question Skip/close in the managed UI, then run targeted tests, frontend typecheck, and root `make code-quality` before updating the draft PR.

# Tasks

## 1. Durable delivery

- [x] 1.1 Promote each pending update through the existing user event before the model call; verify ordered ranks and clocks with focused persistence tests.
- [x] 1.2 Await a delivery receipt after checkpoint persistence; verify the ordering on ReAct and Deep, cross-store visibility, and failed persistence cases.

## 2. Ordinary turn behavior

- [x] 2.1 Remove interim reply generation, fallback, continuation, and special provider settings; verify tool use, final answers, stop requests, and `ask_user` with focused ReAct and Deep tests.
- [x] 2.2 Remove obsolete reply handling in the history and stream consumers; verify historical messages remain readable and no extra assistant message appears after a steer.
- [x] 2.3 Update the runtime contract and managed-conversation spec to match final-answer behavior; verify OpenSpec validation.

## 3. Integration

- [x] 3.1 Exercise multiple steer timings against Mistral Small and Medium and OpenAI Sol, Terra, and Luna; record provider, model, tool, rank, final-answer, and error outcomes in the PR.
- [x] 3.2 Run targeted quality checks and an independent branch review, then update the draft PR with results and remaining limits.

## Workflow follow-up

- Sync and archive the OpenSpec change after verification and review.

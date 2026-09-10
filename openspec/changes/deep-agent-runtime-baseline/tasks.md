## 1. Dispatch and capability wiring (committed on this branch)

- [x] 1.1 `agent_app.py` dispatches `DeepAgentDefinition` to `DeepAgentRuntime` instead of
      `ReActRuntime` — verified by `test_deep_agent_dispatch.py` (fails pre-fix, passes post-fix).
- [x] 1.2 `DeepAgentRuntime.build_executor` threads the selected capability block's tools, MCP prompt
      groups and middleware into the compiled graph — verified by
      `test_deep_build_executor_wires_capability_middleware`.
- [x] 1.3 Deep reuses `TracingKpiMiddleware`/`ToolObservabilityMiddleware` — verified by
      `test_middleware_leads_with_observability_then_hitl_when_filesystem_enabled` and live-observed
      `[LLM][CALL]`/`agent.tool.invocation.*` log/audit lines on a real Deep turn.

## 2. Fred HITL parity: capability and operator approval

- [x] 2.1 `FredHitlMiddleware` composed into Deep's middleware list, same relative order as
      `build_react_platform_middleware_frame` — verified by
      `test_middleware_places_capability_middleware_before_observability` and
      `test_middleware_threads_capability_hitl_into_fred_hitl_middleware` (implemented in the
      working tree).
- [x] 2.2 A capability `HitlSpec` binding no-ops, pauses+resumes on `proceed`, and pauses+skips on
      `cancel` — verified by `test_deep_agent_hitl_integration.py` driving a real compiled
      `deepagents.create_deep_agent` graph with a real LangGraph `interrupt()`/`Command(resume=...)`
      (implemented in the working tree).
- [x] 2.3 Removed `DeepAgentRuntime.build_executor`'s build-time rejection of an enabled operator
      `ToolApprovalPolicy`. Routes through the already-shared `FredHitlMiddleware` — no new
      mechanism; `approval_policy` was already threaded into that middleware for Deep. Verified by
      `test_deep_build_executor_no_longer_rejects_operator_tool_approval` (implemented in the working
      tree).
- [x] 2.4 Added focused operator-policy tests for Deep mirroring the capability-HITL coverage (no-op
      via `test_deep_hitl_tool_outside_operator_list_skips_gate`, pause+proceed via
      `test_deep_hitl_operator_policy_gates_named_tool_and_resumes_on_proceed`, pause+cancel via
      `test_deep_hitl_operator_policy_cancel_skips_the_tool`) through a real compiled `deepagents`
      graph, matching ReAct's own `test_hitl_operator_policy_gates_named_tool` coverage. Existing
      capability-HITL tests preserved unchanged (implemented in the working tree).
- [x] 2.5 Added the mandatory Fred transport-level Deep HITL test
      (`test_deep_hitl_transport_level_pause_is_observable_and_resumes_on_proceed`,
      `test_deep_hitl_transport_level_cancel_executes_the_tool_zero_times`): a real compiled Deep
      agent wrapped in a real `_TransportBackedReActExecutor` — not a hand-driven `astream` loop
      against the bare graph — confirms all four required behaviors: the tool call pauses, an
      `AwaitingHumanRuntimeEvent` carrying a `HumanInputRequest` is emitted, resuming via
      `ExecutionConfig(interrupt_id=..., resume_payload={"choice_id": "proceed"})` executes the tool
      exactly once, and resuming with `"cancel"` executes it zero times. The existing direct
      compiled-graph `Command(resume=...)` tests remain, now understood as necessary but not
      sufficient alone (implemented in the working tree).
- [x] 2.6 Committed the `deep_runtime.py`, test and `RUNTIME-EXECUTION-CONTRACT.md` changes
      implementing 2.1-2.5 in `02ebf3c3`.

## 3. Filesystem-tool-name overlap

- [x] 3.1 `test_deep_hitl_filesystem_tool_name_overlap_does_not_collide` stays as an implementation
      regression test, not a delta-spec requirement — no shipped capability gates a filesystem tool
      today (design.md D3). No spec change needed for it; briefly explained in design.md instead.

## 4. Cleanup

- [x] 4.1 Fixed `test_deep_agent_dispatch.py`'s 2 `basedpyright` `reportIncompatibleVariableOverride`
      errors (base class `instances` retyped `ClassVar[list[Any]]`; each subclass narrows with its
      own `ClassVar[list[Specific]]`) and its 1 `reportUnreachable` warning (inline
      `# pyright: ignore[reportUnreachable]` on the intentionally-unreachable `yield` that makes
      `_NullExecutor.stream` an async generator) — `basedpyright tests/test_deep_agent_dispatch.py`
      reports 0 errors, 0 warnings, 0 notes.
- [x] 4.2 Compacted RUNTIME-EXECUTION-CONTRACT.md's §8.76-8.77 (220 lines of accreted chronology,
      including a mid-section amendment) into one ~38-line §8.76 architecture/invariant summary
      linking to the two OpenSpec capabilities. Trimmed the matching comments/docstrings in
      `deep_runtime.py`, `test_deep_agent_middleware.py` and `test_deep_agent_hitl_integration.py`
      that referenced the old section numbers or re-narrated the fix's history.

## 5. Acceptance evidence

- [x] 5.1 Record the manual NOVA-DOC run (design.md D4): `fred.github.deep_assistant` (Deep) and
      `fred.github.assistant` (ReAct) both produced the identical correct answer (EUR 1,800,000
      excluding tax; 12 February 2027, 12:00 UTC) to the public NOVA-DOC factual question, verified
      via `session_history` in Postgres rather than the chat UI (#2588). Deep used approximately 14k
      input tokens against ReAct's approximately 10k on this one run. Both runs invoked only
      `search_documents_using_vectorization` — no filesystem tool call, no Workspace object, no
      S3/SeaweedFS write in either run. This is document-access/RAG parity evidence only; it is not
      filesystem, Workspace, or multi-step planning evidence, and must not be cited as such.

## 6. Quality, performance and review

- [x] 6.1 Ran `make code-quality` and offline `make test` in `libs/fred-runtime`. `make test`: 1181
      passed, 16 deselected, 0 failed. `make code-quality`: ruff lint, import order, format, and
      bandit all pass; the `detect-secret` step fails on a pre-existing fixture string in
      `test_react_tool_resolution.py` (untouched by this change, last modified 2026-09-07) unrelated
      to this diff — not fixed here, out of this change's scope.
- [x] 6.2 Ran `fred-performance-reviewer`. The HITL diff adds no I/O, client, blocking call or
      unbounded state. The review identified a pre-existing runtime-lifecycle cost that becomes live
      through Deep dispatch: synchronous per-turn graph construction measured 3.1 ms median for
      ReAct and 15.3 ms for Deep. Design D6 records why optimization and load testing are isolated
      into a separate investigation from `swift`, and why cross-binding graph caching is not yet
      considered safe.
- [ ] 6.3 Run an independent `/code-review` on the full diff and fix every blocking finding.

## 7. Move the durable behavioral record to OpenSpec

- [ ] 7.1 Once §§2-6 are complete and reviewed, sync/archive this change so `deep-agent-runtime` and
      `agent-human-approval` land under `openspec/specs/` as the durable behavioral record for Deep's
      runtime baseline and HITL parity.
- [ ] 7.2 Confirm `RUNTIME-EXECUTION-CONTRACT.md`'s Deep-related sections are trimmed to compact
      architecture/invariant statements with a link to the two synced OpenSpec capabilities, per
      design.md D5 — the runtime contract is no longer where this behavior's chronology lives.

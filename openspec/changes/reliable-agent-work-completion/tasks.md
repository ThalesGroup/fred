These tasks are grouped into independently mergeable gates, not one PR. Group 0 is a
blocking external dependency this change does not implement. Group 1 (PR A) may start
immediately, on the current branch. Group 2 (PR B) may not start until Group 0 is
satisfied. Group 3 targets the separate `fred-corpus` repository and produces a
specification only. Group 4 is a later, optional slice gated on Groups 1-3 landing.
Do not run these as one uninterrupted implementation pass.

## 0. External dependency gate — #2498 (not implemented by this change)

Design reference: `design.md` §3 (Scoped Workspace persistence), §Goals/Non-Goals.
This change does not implement, partially implement, or re-specify #2498. All four
operations (`list`, `read`, `write`, `link`) validate fail-closed once #2498 ships.

- [ ] 0.1 Before starting Group 2, verify GitHub issue #2498 is closed/merged and its
      four-operation Workspace surface is live in the target environment — verify by
      checking the issue status on GitHub and confirming `FredWorkspaceFs` no longer
      authenticates writes with the human bearer token (i.e. the code at
      `libs/fred-runtime/fred_runtime/integrations/v2_runtime/adapters.py` matches
      #2498's shipped state, not the state described in `design.md` §3). Do not
      proceed to Group 2 until this is true.

**Stop condition before Group 2:** #2498 merged and its fail-closed validation for all
four operations confirmed live. Group 1 and Group 3 do not depend on this gate.

## 1. PR A — Shared tool-result error-classification fix

**Scope:** may start immediately on the current `#2568` branch. This is the smallest
independently reviewable correctness PR in this change.

**Files likely touched:** `libs/fred-runtime/fred_runtime/react/react_runtime.py` (the
`is_error` derivation, per `design.md` Decision D1 — a true OR of `ToolMessage.status ==
"error"` and a returned artifact's `is_error`; also imports `render_tool_result` from
`react_tool_rendering.py` and replaces `_clean_tool_error_text()` with the trust-boundary
renderer per revised Decision D4 — no longer parses LangGraph's wrapper string);
`libs/fred-runtime/fred_runtime/react/react_tool_binding.py`
(tracing span reflects a returned `is_error=True` artifact — unaffected by this revision);
`libs/fred-runtime/fred_runtime/react/react_tool_resolution.py` **reverts** to its pre-change
form (the `_workspace_tool_failure` helper and both closures' `try`/`except` are removed —
superseded by the generic fix); `tests/test_react_tool_error_final_2244.py` (extended with
the untyped/raw-status-error and status-vs-artifact-disagreement cases, and their expected
content revised per D4's trust boundary — see 1.3-1.4, 1.10-1.12); a new, small
`tests/test_react_tool_binding_span_status.py` (no existing file covers this layer).

**Tests:** see 1.3-1.7, 1.10-1.12 below — all are required proof, not optional.

**Docs/contracts:** one dated entry in `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`
noting the fix (no `§` renumbering of unrelated content). No OpenAPI, `WorkspaceFsPort`,
or `RuntimeEvent` shape change.

**Generated clients:** none — no public contract changes.

**Performance review:** required. This touches the ReAct tool-call hot path
(`fred-performance-reviewer` skill), even though the change is a classification-expression
edit with no new I/O.

**Explicit non-goals:** no `WorkspaceFsPort` method added/removed/renamed; no change to
`FredWorkspaceFs`'s authentication or path-construction behavior (that is #2498's
territory); no change to any authored capability tool (they already classify errors
correctly); no source-specific `try`/`except` added to `_resolve_transport_declared_tool`
or any other resolver — the generic fix covers it with no resolver-level change; no change
to `ToolObservabilityMiddleware` itself, used only as the already-correct reference
implementation; no change to the round-level suppression logic's own structure
(`react_runtime.py:574-596`) beyond the one-line classification expression it consumes.

**Estimated LOC:** production ~5-10 lines net (a one-expression classification fix in
`react_runtime.py`, the small already-scoped span fix in `react_tool_binding.py`, minus
the ~35 lines reverted in `react_tool_resolution.py`); tests ~60-100 lines (extending one
existing file plus one small new file, replacing a larger standalone harness); generated
~0; docs ~10-15 lines (one dated entry).

- [x] 1.1 Revert `react_tool_resolution.py`: remove the `_workspace_tool_failure` helper
      and both built-in closures' `try`/`except`, back to the pre-change form — verify by
      diff that the file matches its state before this change's first implementation pass.
      Done: `git diff -- react_tool_resolution.py` is empty — exact revert confirmed.
- [x] 1.2 Fix `react_runtime.py`'s `is_error` derivation to a true OR of both signals,
      exactly matching `ToolObservabilityMiddleware`'s rule (`middleware/tool_observability.py:325-328`):
      ```python
      status_is_error = message.status == "error"
      artifact_is_error = artifact is not None and artifact.is_error
      is_error = status_is_error or artifact_is_error
      ```
      Not the fallback ternary `artifact.is_error if artifact is not None else message.status
      == "error"` — that form ignores `status` whenever an artifact exists. Verify by reading
      the diff and by task 1.4's regression case below.
      Done: `react_runtime.py:574-580` (line numbers shifted by the edit) replaced with the
      exact true-OR form. Confirmed `ToolMessage.status` defaults to `"success"` (never
      `None`/missing), so the comparison is always safe inside the existing
      `isinstance(message, ToolMessage)` guard.

      A first pass added text-cleanup logic here to keep the newly-classified
      untyped failures from leaking LangGraph's raw wrapper text; independent
      review found it insufficient (still leaked `repr(exc)`, and never
      covered `ToolResultRuntimeEvent.content`) and it was superseded by the
      trust-boundary design in task 1.10 (final, shipped implementation).
- [x] 1.3 Extend `test_react_tool_error_final_2244.py` with a raw/untyped case:
      `ToolMessage(status="error", artifact=None)` (no Fred artifact at all — the shape a
      built-in Workspace, transport-declared, or MCP tool failure now takes) still triggers
      the existing whole-round suppression — verify the final answer AND
      `ToolResultRuntimeEvent.content` for this call are both the bounded generic message
      (design.md D4), not raw tool-supplied text.
      Done: `test_raw_status_error_with_no_artifact_still_surfaces_as_final` updated to
      assert `_GENERIC_TOOL_FAILURE_MESSAGE` on both `FinalRuntimeEvent.content` and
      `ToolResultRuntimeEvent.content` (was `"boom"` before the D4 revision).
- [x] 1.4 Add the focused regression case the true-OR contract requires: a `ToolMessage`
      where `status == "error"` **and** a present artifact has `is_error == False` — verify
      the resulting `RuntimeEvent.is_error` is still `True` (the exact case the rejected
      fallback-ternary form would get wrong), **and** verify the final answer AND
      `ToolResultRuntimeEvent.content` are both the bounded generic message per design.md D4
      (an artifact with `is_error == False` is not the trusted typed-error case).
      Done: `test_status_error_with_non_erroring_artifact_still_classified_as_error`
      updated to assert `_GENERIC_TOOL_FAILURE_MESSAGE` on both events (was `"boom"`
      before the D4 revision).
- [x] 1.5 Add a partial-success-round case mixing one raw-status-error call (`artifact=None`)
      with one typed-artifact-success call — verify synthesis is retained (mirrors the
      existing typed-only partial-success tests in the same file, now proven for the
      untyped shape too).
      Done: `test_partial_round_raw_status_error_keeps_synthesis`.
- [x] 1.6 Confirm typed-artifact-error and successful-result cases remain covered by the
      existing file's `_error_result`/`_ok_result` tests — verify they still pass unchanged;
      no new test needed for these two shapes.
      Done: all 5 pre-existing tests in the file pass unchanged (8/8 total in the file).
      All 3 new tests (1.3-1.5) confirmed failing against the pre-fix `react_runtime.py`
      (via `git stash`) and passing post-fix; the 5 pre-existing tests were unaffected in
      both states.
- [x] 1.7 Add `tests/test_react_tool_binding_span_status.py`: a typed `is_error=True`
      artifact returned (not raised) marks the tool's tracing span `status="error"`; a
      successful call marks it `status="ok"` — verify both, confirmed failing/passing via
      `git stash` on `react_tool_binding.py`'s span-setting logic as in the first
      implementation pass.
      Done: 2 tests added, using a generic `FredRuntimeToolSpec` fixture (no Workspace
      dependency). Confirmed the error-case test fails pre-fix (`status="ok"` instead of
      `"error"`) and both pass post-fix. The oversized first-pass file
      `test_react_builtin_workspace_tool_errors.py` is deleted (superseded — its
      is_error-classification tests are now covered generically by
      `test_react_tool_error_final_2244.py`'s new cases, and its span tests moved here).
- [x] 1.8 Run `make code-quality` and `make test` in `libs/fred-runtime`; run the
      `fred-performance-reviewer` skill against the diff; run `/code-review` on the diff
      independently of the tests written alongside the fix — verify all three pass/report
      clean before marking this PR done.
      Done: `make code-quality` clean (ruff lint/import-order/format, bandit,
      basedpyright all 0 errors — 1 pre-existing unrelated warning in
      `__main__.py`). `make test` — 1151 passed, 1 pre-existing unrelated
      failure (`test_migrations.py::test_runtime_migration_tree_is_packaged_and_linear`),
      caused by a stray, untracked/gitignored `libs/fred-runtime/alembic/`
      directory predating this change. `fred-performance-reviewer` — no
      blocking findings; `render_tool_result` is now called a second time on
      the (already rare) error path, a bounded, cheap duplicate render, not a
      hot-path concern.

      Independent `/code-review` found and this task fixed a real regression:
      the trust-boundary renderer returned an empty string for a typed
      `is_error=True` artifact with no `blocks` — the shape `ppt_filler`,
      `html_artifact`, and `writable_document` return today (their real error
      message lives only in the paired string, not the artifact). Fixed with
      an empty-render fallback to the generic message (see task 1.10);
      re-reviewed clean, 0 findings.

      **Remaining, deliberately out of scope:** the true-OR classification
      expression is now hand-written in three places
      (`tool_observability.py`, `react_runtime.py`, `graph_runtime.py`);
      extracting a shared helper was raised by reviewers and not done here —
      it would touch files this change does not otherwise scope.
- [x] 1.9 Add the dated entry to `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`
      describing the generic convergence fix (not two Workspace-only catches) — verify the
      entry states what changed, why, and its scope (`react_runtime.py` and
      `react_tool_binding.py` only; no resolver changed), per the existing dated-entry
      convention in that file.
      Done: §8.74 rewritten as a compact current-state entry — classification
      (true OR), the trust-boundary error-text rendering (typed-artifact case
      rendered via `render_tool_result`, untrusted case uses the generic
      message in both runtime events), why the earlier wrapper-parsing pass
      was superseded, and the unfixed `fred-capability-*` empty-`blocks` gap
      (no tracking issue exists for it). `make code-quality`/`make test`
      re-run clean after this docs-only edit.
- [x] 1.10 Replace `_clean_tool_error_text()` with a trust-boundary renderer, per
      design.md's revised D4: one function that (a) for a `ToolMessage` whose artifact is
      an `is_error=True` `ToolInvocationResult`, derives the text via
      `render_tool_result(artifact)` (imported from `react_tool_rendering.py`) and strips
      only Fred's own `"Tool error:\n"` presentation prefix, never reading
      `message.content`; (b) for every other failing case (`status == "error"` without
      such an artifact, including a present artifact with `is_error=False`), returns one
      fixed bounded generic message without reading, parsing, or branching on
      `message.content` at all. Feeds both `ToolResultRuntimeEvent.content` and
      `last_tool_error`/`FinalRuntimeEvent.content` from this single function. Removes the
      LangGraph prefix/suffix-parsing branch and the `_LANGGRAPH_TOOL_CALL_ERROR_PREFIX`/
      `_SUFFIX` constants entirely — verify by diff that no code path inspects
      `message.content`'s shape for the untrusted case. Removes the three unit tests that
      exercised the old function directly (`test_clean_tool_error_text_strips_fred_prefix`,
      `test_clean_tool_error_text_strips_langgraph_default_template`,
      `test_clean_tool_error_text_passes_through_unrecognized_text`), replacing them with
      tests of the new renderer's two branches; updates tasks 1.3 and 1.4's test bodies to
      assert the bounded generic message instead of raw text. Any new comment stays within
      CLAUDE.md's 2-3 line rule.
      Done: `_user_facing_tool_error_text(artifact)` added to `react_runtime.py`
      (imports `render_tool_result`); `_clean_tool_error_text` and the LangGraph
      prefix/suffix constants deleted; `tool_result_content` computed once per
      message and fed to both `ToolResultRuntimeEvent.content` and
      `last_tool_error`. The trusted branch also falls back to the generic
      message when the artifact renders to no real text (empty `blocks` — see
      1.8). The 3 old unit tests replaced with 5 covering the new renderer:
      `test_typed_error_artifact_is_rendered_via_render_tool_result`,
      `test_untyped_failure_without_artifact_is_the_generic_message`,
      `test_untyped_failure_with_non_erroring_artifact_is_the_generic_message`,
      `test_typed_error_artifact_with_no_blocks_falls_back_to_generic_message`,
      `test_typed_error_with_empty_blocks_shows_generic_message_not_empty`.
- [x] 1.11 Add the required secret/token/path-leak regression test: inject an untyped
      `ToolMessage(status="error", artifact=None)` whose `content` contains a distinctive
      secret/token/path embedded in a LangGraph-shaped `repr(exc)` (e.g.
      `f"Error: ValueError('{secret}')\n Please fix your mistakes."`) — assert the
      resulting `RuntimeEvent.is_error` is `True`; assert neither
      `ToolResultRuntimeEvent.content` nor `FinalRuntimeEvent.content` contains the
      secret, the exception repr, the path, or the LangGraph instruction text; assert both
      equal only the bounded generic message.
      Done: `test_untyped_status_error_never_leaks_secret_or_langgraph_instruction`,
      secret `"sk-live-SECRET-TOKEN"` and path `"/etc/shadow"` embedded in a
      `ValueError(...)` repr inside the real LangGraph `"Error: ...\n Please fix your
      mistakes."` template; asserts `is_error is True`, asserts none of the secret,
      path, `"ValueError"`, or `"Please fix your mistakes"` appear in either event's
      content, and asserts both equal `_GENERIC_TOOL_FAILURE_MESSAGE` exactly.
- [x] 1.12 Add the artifact/`message.content`-divergence regression test named in the
      blocking review: a `ToolMessage(status="error", ...)` carrying both an
      `is_error=True` normalized `ToolInvocationResult` whose blocks render a safe Fred
      error string, and a `content` field set to a different, sensitive string (simulating
      `_resolve_runtime_provider_tool`'s `rendered_content`/artifact divergence, design.md
      D4) — assert both `ToolResultRuntimeEvent.content` and `FinalRuntimeEvent.content`
      equal the artifact's own rendered (prefix-stripped) text, and assert neither
      contains the sensitive `content` string.
      Done: `test_typed_error_ignores_divergent_message_content`, using new helper
      `_content_divergent_error_result` (artifact blocks render `"safe Fred error
      text"`, `content` set to a different `"sk-live-SECRET-TOKEN /etc/shadow"`
      string); asserts both events equal the safe rendered text and neither contains
      the sensitive string.

**Stop condition before Group 2:** PR A merged (independently of Group 0/#2498 — this
gate does not block Group 2, but should not be left open indefinitely alongside it).

## 2. PR B — ReAct objective retention and private Workspace persistence

**Blocked on:** Group 0 (#2498 merged and live).

**Scope:** the minimal change needed for the `agent-work-completion` spec's objective-
retention and durable-private-state requirements to hold against the existing ReAct
runtime, consuming #2498's shipped Workspace surface. Does not add a new planner, plan
database, or TODO domain; does not synchronize Deep Agents' `write_todos` with any
Workspace file (that pairing is explicitly out of scope, per #2328's own non-goals).

**Files likely touched:**
`libs/fred-runtime/fred_runtime/react/middleware/checkpoint_hygiene.py` (history-trimming
behavior — frozen first per 2.1, then adjusted only as much as needed);
`libs/fred-runtime/fred_runtime/support/tool_loop.py` (`trim_to_char_budget`/
`trim_to_human_boundary`, if the fix requires preserving the original objective across a
trim rather than changing the trim boundary itself); a capability or tool surface for
writing/reading the private working file via the now-hardened `WorkspaceFsPort`/
`FredWorkspaceFs` (exact shape decided against #2498's shipped four-operation contract at
implementation time, not pre-designed here per `design.md` §3/Decision D3).

**Tests:** a frozen-baseline test for current trimming behavior (2.1) before any change;
an objective-retention test reproducing `spec.md`'s "long-running turn does not lose the
original instruction" scenario; a durable-private-state test reproducing "private working
file survives to a later turn," using #2498's shipped Workspace write/read.

**Docs/contracts:** update `docs/swift/design/FILESYSTEM.md` if the private-working-file
mechanism introduces any new visible behavior beyond what #2498 already documents; dated
entry in `RUNTIME-EXECUTION-CONTRACT.md` if `CheckpointHygieneMiddleware`'s behavior
changes (frozen contract per that doc's own rules).

**Generated clients:** none expected — this consumes #2498's already-generated Workspace
client; regenerate only if this PR itself adds a new route (not expected).

**Performance review:** required — this touches the per-turn ReAct middleware frame
(`fred-performance-reviewer` skill), particularly any change to history-trimming logic.

**Explicit non-goals:** no new planner/orchestration API; no new TODO domain; no
synchronization between Deep's `write_todos` and any Workspace file; no change to HITL
(`FredHitlMiddleware`, the claim table) — retained as-is; no Workspace API surface change
beyond what #2498 already shipped.

**Estimated LOC:** production ~100-250 lines; tests ~200-400 lines (the baseline-freeze
test plus new scenario tests); generated ~0 (unless a new capability route is added, not
expected); docs ~20-50 lines.

- [ ] 2.1 Add a regression test locking `CheckpointHygieneMiddleware`'s current
      front-drop trimming behavior (design.md Decision D2) — verify this test passes
      against the pre-change code, establishing the baseline before any behavior change.
- [ ] 2.2 Identify and implement the smallest change that preserves the original
      multi-step objective across a trim (e.g. pinning the originating instruction, or
      an equivalent mechanism) — verify the "long-running turn does not lose the
      original instruction" scenario from `specs/agent-work-completion/spec.md` passes.
- [ ] 2.3 Implement a private-workspace-file write/read path for durable planning state,
      using #2498's shipped `list`/`read`/`write`/`link` Workspace operations — verify
      the "private working file survives to a later turn" scenario passes across two
      separate session turns for the same authorized binding.
- [ ] 2.4 Verify the "no gratuitous request for permission to continue" and "explicit
      continuation or re-planning after a recoverable tool failure" scenarios from the
      spec pass against the current ReAct HITL and tool-failure-suppression mechanisms
      unchanged — verify by scenario test, adding no new HITL code.
- [ ] 2.5 Verify cross-team/cross-user/cross-agent-instance isolation for the new
      private-workspace-file path is covered by #2498's own server-side isolation tests
      (do not re-implement isolation checks here) — verify by confirming those tests
      exist and pass in the #2498-provided surface this PR consumes.
- [ ] 2.6 Run `make code-quality` and `make test` in every touched project; run the
      `fred-performance-reviewer` skill; run `/code-review` on the diff — verify all
      pass/report clean before marking this PR done.

**Stop condition before Group 4:** PR B merged, and the `agent-work-completion` spec's
ReAct-only requirements (objective retention, tool-failure continuation, durable private
state, truthful artifact publication, history durability, source grounding, bounded
reliability) are all demonstrably passing against the existing ReAct runtime.

## 3. fred-corpus specification (separate repository — specify only, no implementation)

**Scope:** produces a specification document for a future, separate change in the
`fred-corpus` sibling repository. Nothing in this repository is implemented by this
group; `fred-corpus` is not accessed or modified.

**Deliverable:** a specification (in this change's own artifacts, or handed off as a
standalone document — decide at implementation time) describing:
`corpora/proposal-workflow/` with `source/` (request-for-proposal.pdf,
technical-and-security-requirements.pdf, bidder-profile.md,
references-and-capabilities.xlsx, staffing-and-availability.csv, response-template.docx)
and `validation/` (`GROUND-TRUTH-PROPOSAL.md`, `prompt-agent-work-completion.md`,
`dataset-proposal-workflow.json`), reusing the existing `Evaluation`/`EvaluationCase`
dataset schema (`docs/swift/rfc/AGENT-EVALUATION-RFC.md` §9.5) — no new evaluator schema.

**Non-goals:** no new evaluator/campaign runner; no dataset schema invention; no
implementation of the corpus documents themselves in this task group.

**Estimated LOC:** documentation/specification only, ~150-300 lines (the handoff spec);
zero production/test/generated code in this repository.

- [ ] 3.1 Confirm the exact acceptance-prompt text from GitHub issue #2568 is reused
      verbatim as the reference prompt, rather than paraphrased — verify by diffing
      against the issue body text.
- [ ] 3.2 Confirm the ground-truth structure records both factual expectations and the
      intentionally-absent evidence gap as a first-class, separately-labeled section —
      verify by reviewing the specification document for that explicit split.
- [ ] 3.3 Confirm the dataset file maps onto the existing `Evaluation`/`EvaluationCase`
      schema fields exactly (`schema_version`, `evaluation_id`, `name`, `version`,
      `team_id`, `created_by`, `origin`, `completeness`, `cases` with `external_id`/
      `input`/`expected_output`/`tags`) — verify by field-by-field comparison against
      `AGENT-EVALUATION-RFC.md` §9.5, with no additional top-level field introduced.
- [ ] 3.4 Hand off the completed specification for a separate `fred-corpus` change —
      verify by confirming the handoff document exists and needs no further
      clarification before someone can start that separate change.

**Stop condition:** specification complete and handed off; this group produces no code
in this repository and has no dependency on Groups 0-2.

## 4. Later PR — Deep Agents Workspace parity (optional, after ReAct + Workspace proven)

**Blocked on:** Group 2 (PR B) merged and its ReAct-only scenarios passing, and Group 0
(#2498) merged.

**Scope:** wire a Fred-backed/composite Workspace backend into `DeepAgentRuntime` so the
same black-box `agent-work-completion` scenarios hold for Deep Agents, per
`docs/swift/rfc/AGENT-FILESYSTEM-HARDENING-RFC.md` §9.8 (`CompositeBackend(default=
StateBackend(), routes={"/workspace/": FredWorkspaceBackend(...)})`). This group is
optional relative to #2568's own definition of done, which requires only that the ReAct
path meets the reliability gate.

**Files likely touched:** `libs/fred-runtime/fred_runtime/deep/deep_runtime.py` (pass an
explicit backend to `create_deep_agent` instead of the implicit `StateBackend()`); a new
adapter implementing `deepagents.backends.protocol.BackendProtocol` routed only for
`/workspace/*`.

**Tests:** the same `agent-work-completion` scenario suite built for PR B, re-run against
the Deep Agents runtime with no separate/weaker acceptance contract, per the spec's
"identical black-box expectations extend to Deep Agents when supported" requirement.

**Docs/contracts:** dated entry in `RUNTIME-EXECUTION-CONTRACT.md`; RFC §9.8's own status
line updated once implemented (per repository governance — an implemented RFC section is
folded into the compact doc, not left open).

**Generated clients:** none expected — reuses #2498's already-generated Workspace client.

**Performance review:** required — `DeepAgentRuntime` is on the agent execution hot path.

**Explicit non-goals:** no synchronization between Deep's built-in `write_todos` and the
Workspace `/workspace/*` route (explicitly excluded, per #2328); no sub-agent (#2529)
delegation fix — that code does not exist in this tree and remains out of scope unless
separately merged and explicitly required by a future change; no change to Deep's
explicit non-support for tool approval / `max_tool_calls_per_turn` (`NotImplementedError`
is retained).

**Estimated LOC:** production ~150-300 lines; tests ~200-350 lines; generated ~0; docs
~30-60 lines.

- [ ] 4.1 Confirm Groups 0 and 2 are both merged and passing before starting — verify by
      checking their stop conditions above are satisfied.
- [ ] 4.2 Implement the composite backend routing `/workspace/` to the Fred-backed
      adapter while leaving `StateBackend` as the default for ephemeral scratch —
      verify `create_deep_agent` receives an explicit backend argument (no longer
      implicit `None`).
- [ ] 4.3 Re-run the full `agent-work-completion` scenario suite against the Deep Agents
      runtime — verify every scenario from `specs/agent-work-completion/spec.md` passes
      identically to the ReAct run, with no Deep-specific relaxation.
- [ ] 4.4 Run `make code-quality` and `make test`; run `fred-performance-reviewer`; run
      `/code-review` — verify all pass/report clean before marking this PR done.
- [ ] 4.5 Fold RFC §9.8's implemented design into the compact doc and trim the RFC
      section accordingly, per repository governance's RFC-vs-doc rule — verify the RFC
      no longer describes this as "not yet built."

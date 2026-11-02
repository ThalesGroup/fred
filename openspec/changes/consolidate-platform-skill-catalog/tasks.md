## 1. Scope confirmation

- [x] 1.1 Obtain developer confirmation of proposal, design and acceptance scenarios, including retained `graph` identity/routes and the policy-review requirement; record the confirmation here before implementation. Developer replied "oui" on 2026-11-02 to the presented scope.

The developer additionally requested model-only `analyze-data` during implementation on 2026-11-02; its procedure stays unchanged.

## 2. Packaged procedures

- [x] 2.1 Merge numerical/chart guidance into `graph/SKILL.md` and extract `graph/references/mermaid.md`; verify the main procedure selects supported outputs and reads the packaged reference only for Mermaid, retaining all existing diagram families.
- [x] 2.2 Condense `compare-options` and the `summarize-document` core, add conditional complex-summary reference, and set model-only metadata for both and `analyze-data`; inspect the resulting procedures for preserved evidence/weighting/fidelity rules and an ordinary short path.
- [x] 2.3 Make minutes user-only and remove `data-visualization` and `verify-answer` resources; verify package discovery exposes the seven names and modes specified by the delta, without new aliases or custom-directory changes.

## 3. Consumers and regression coverage

- [x] 3.1 Update French/English graph presentation and affected consumer expectations; verify active menus follow eligibility while existing history/preview labels remain readable and old identities are not rewritten.
- [x] 3.2 Update `test_platform_skills.py`, `test_common_skill_content.py` and affected eligibility/native suites to cover actual package modes, denied fresh selections/loads, explicit minutes pins, and graph/summary reference delivery; group test execution after related edits.
- [x] 3.3 Reconcile active contract examples/docs and extend `platform-skills-evolution.md` with invocation changes, broadened graph policy, all-replica rollout and rollback; check current-behavior searches no longer promise retired commands or single-file graph guidance. Leave archives unchanged.

## 4. Verification and review

- [ ] 4.1 Run affected offline runtime suites and relevant frontend menu/history/presentation tests; record exact commands and outcomes here, including reference access for ReAct and native Deep and stale-selection behavior.
- [ ] 4.2 Inspect diagram, numerical chart, missing-renderer, short-summary and conflicting-source cases; distinguish instruction/transport evidence from any actually observed model output, with no unmeasured quality or latency claims.
- [ ] 4.3 Run required root code quality, affected typing checks and migration validation; record pass results and any demonstrated pre-existing limitations here.
- [ ] 4.4 Apply `audit-branch` against the actual PR target and obtain an independent read-only review of the implementation; record base/head, coverage, findings/dispositions and verification limits, including bounded resource loading and multi-replica behavior.

## 5. Delivery

- [ ] 5.1 Reconcile final artifacts, sync and archive through the repository OpenSpec procedures, and validate the resulting current skill spec; record any approved divergence.
- [ ] 5.2 Commit reviewable blocks, push to `codex/platform-skills-evolution`, update draft PR #3342 with scope/verification and link #3402; verify the published diff excludes unrelated work.

## Verification evidence

- 2026-11-02: Package discovery confirms seven canonical skills and the approved invocation matrix, including the developer's additional model-only analyze-data request. The graph core is 60 lines; its conditional Mermaid reference retains the existing 12 diagram families.
- Runtime focused suites: 151 passed, with one existing LangChain beta warning. Command: `.venv/bin/python -m pytest tests/test_platform_skills.py tests/test_common_skill_content.py tests/test_skill_eligibility.py tests/test_native_skill_policy.py tests/test_deep_skills_filesystem.py tests/test_native_skill_read_completeness.py -m 'not integration' --disable-socket --allow-unix-socket -q --no-cov` from `libs/fred-runtime`.
- Frontend focused suites: 215 passed. Command: `node_modules/.bin/vitest run src/rework/components/pages/ManagedChatPage/useComposerCommands.test.tsx src/rework/components/shared/molecules/SkillBadge/SkillBadge.test.tsx src/rework/components/shared/organisms/UserTurn/UserTurn.test.tsx src/rework/components/shared/organisms/AssistantTurn/AssistantTurn.skill-order.test.tsx --reporter=dot` from `apps/frontend`.
- Two initial runtime failures were old automatic minutes-loading fixtures. They now exercise the explicit minutes selection or an eligible visualization workflow; the current package's unselected native parent/child minutes denial has dedicated coverage.
- Full runtime run: 2397 passed, 23 deselected and one stale graph argument-hint assertion failed. After updating that expectation, `tests/test_react_prompting.py` passes all 64 tests. Root `make code-quality` passed across all modules on this pre-integration tree.
- A wheel built with the existing control-plane environment's `setuptools.build_meta.build_wheel` contains all seven skills and both new references, with neither retired resource. Manual procedure inspection covers Mermaid/numerical output selection, missing-renderer fallback, concise summary and conflicting-source traceability; no live model quality or latency claim is made.
- Independent review of `e228fe5736dad0383ced4ec9f93eba82012ef1af` plus this working tree against `origin/swift` at `fa363690ebac5d438904d1538450cacff3c48d56` found stale command help (corrected here) and a migration head conflict caused by target advancement. Integrating the target and verifying the re-parented migration remains pending. The reviewer ran 17 focused tests and checked routing, reference packaging, policy/history compatibility and bounded native loading; unchanged administration/telemetry areas reuse the earlier branch review evidence.

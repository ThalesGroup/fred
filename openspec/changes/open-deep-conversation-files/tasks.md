# Tasks

Slice 1 is implemented and verified below; later implementation tasks remain unchecked. The approved execution order is slices 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7, followed by integration close-out. This serial schedule is a quality/cost choice; the narrower technical blockers below do not authorize parallel implementation. See [design.md](design.md#implementation-sequencing-and-ownership) for shared contracts, ownership, and handoffs.

Use TDD within each slice: one meaningful failing behavior test, then the minimum implementation to pass it. Test through the public seams listed below, using independent expected outcomes from the acceptance scenarios. Avoid tautological assertions, private implementation coupling, and tests that only repeat type-system guarantees. Run the affected tests for red/green feedback; defer broad suites and quality checks to final validation or verified CI coverage at the integrated revision. Reuse valid results when their inputs have not changed.

## 1. Open a conversation text file from a parent or child

Blocked by: none. Delivers a complete read-only plain-text presentation path, including history and reopening. Seams: standard Deep tool execution, authenticated runtime file API, serialized UI parts/history, and rendered chat panel.

- [x] 1.1 Add the built-in typed conversation-file UI part and minimal read response models; verify serialization/history round trips, OpenAPI exposure, and consistent path/viewer/editability metadata without a presentation capability.
- [x] 1.2 Add conversation-bound read access beside the runtime filesystem route; verify authenticated ownership, team/historical-session routing, unknown/foreign sessions, traversal, forged references, and read-only mount policy without starting an agent execution.
- [x] 1.3 Register standard `open(path)` for parents and native children and propagate child artifacts through stream/history; verify both reach the panel with bounded metadata, no document-body injection, no execution pause, and no claim of browser acknowledgment.
- [x] 1.4 Regenerate runtime OpenAPI and frontend clients and add session/path-keyed dispatch with the reusable CodeMirror plain-text surface; verify deduplication, current-content reopening after reload, stale navigation responses, and actionable missing/denied/unsupported or unavailable-runtime states.
- [x] 1.5 Apply localization, theme tokens, accessible labels, and keyboard opening to this path; verify rendered loading/error/read-only states and an end-to-end parent/child open demonstration.

## 2. Edit a file and immediately continue the conversation

Blocked by: slice 1. Delivers source editing of the same authoritative file followed by a child reading the saved content. Seams: authenticated save/read APIs, filesystem mutation interface, editor/composer interaction, and subsequent agent reads.

- [x] 2.1 Add typed authorized file saves and regenerate clients; verify same-path session isolation, server-side mount editability, rejected `/.deep/` and forged saves, and no privileged authorization through a browser-supplied origin.
- [x] 2.2 Establish server-assigned mutation-source propagation at the shared filesystem boundary, separate from authorization origin; verify parent, child, concatenation, capability/helper, user, and independent-system attribution without changing full-write or exact-text-edit semantics.
- [x] 2.3 Implement serialized autosave and a reusable explicit flush operation; verify edits typed during an in-flight save remain dirty, failures preserve drafts, and successful saves become visible through the filesystem read interface.
- [x] 2.4 Flush conversation editors before message execution; verify immediate continuation starts once after saving, failures preserve both drafts and prevent execution, and navigation invalidates the pending submission.
- [x] 2.5 Implement bounded active-view refresh on relevant tool/run/save completion and focus; verify clean views observe parent/child/concatenation writes, dirty buffers survive refreshes, completed saves reconcile, and close/navigation cancels stale work. Verify localized save failures and no new read-before-overwrite guard.

## 3. Report external edits at the next user turn

Blocked by: slice 2. Delivers consecutive external edits -> durable consolidated history -> next-turn path-only notification -> agent discovery/read. Seams: filesystem mutation/read/list interfaces and user-turn execution/model-input boundary. Use a group-capable representation so slice 4 extends this implementation.

- [ ] 3.1 Persist consolidated external groups in runtime-owned storage outside the public diff directory; verify autosave collapse, independent background edits, same-content/net-zero saves, failed writes, and exclusion of agent/internal mutations through public filesystem behavior.
- [ ] 3.2 Seal intervals with the existing user exchange identity and publish full unified diffs; verify later-replica publication, retry/resume idempotency, writes after the boundary remaining pending, and explicit storage/quota or partial-save errors without acknowledging unpublished changes.
- [ ] 3.3 Publish flat single-group `.diff` files with authoritative original-path headers; verify create/delete headers, nested/equal basenames, encoded separators, Unicode, long paths, collision safety, and discovery through `ls` without an index or internal bookkeeping files.
- [ ] 3.4 Install static parent/child guidance and bounded path-only turn-start notifications; verify distinct source-file counts, no notification for no net changes, no document/diff content injection, filename quoting, and truncation retaining a complete history directory path.
- [ ] 3.5 Include pending data and published history in existing quotas and erasure; verify older diffs survive normal turns, eligible erasure removes all conversation-owned data, and no silent eviction or local-storage fallback occurs.

## 4. Preserve distinct human edits around agent writes

Blocked by: slice 3. Delivers editing during execution with distinct historical external segments. Seams: the same mutation and user-turn interfaces as slice 3, driven by interleaved writers.

- [ ] 4.1 Close external groups around successful parent/child/helper/concatenation writes; verify A-to-B externally, B-to-C by an agent, C-to-D externally produces only A-to-B and C-to-D in chronological order, and failed/no-op writes follow the agreed consolidation rules.
- [ ] 4.2 Publish stable numbered `.001.diff` segments when multiple groups remain; verify suffix-like source names, single/multiple-group collisions, numeric ordering at high segment counts, exact original headers, and unchanged published names on retries.
- [ ] 4.3 Exercise human editing during parent and child execution; verify immediate later reads observe saved content, notification occurs only at the next user-turn start, child/model steps do not advance the boundary, and retries do not consume the following turn's changes. Preserve the documented concurrent-replica limitations.

## 5. Review and export a Markdown report

Blocked by: slice 2 technically; scheduled after slice 4. Delivers file-backed Markdown editing and Markdown/Word export. Seams: rendered editor/export actions, authenticated export API, saved file reads, and legacy document APIs/UI.

- [ ] 5.1 Extract/reuse the existing Markdown editor with a file-backed adapter and retain its legacy adapter; verify saved edits reach subsequent agent reads, dirty-buffer/refresh behavior uses the common coordinator, and existing ReAct documents remain editable.
- [ ] 5.2 Reuse the existing converter for authorized file-backed Markdown download/Word export and regenerate API clients; verify export flushes pending saves and uses the latest saved filesystem content without a legacy document row, with localized errors and accessible actions.

## 6. Review HTML and edit highlighted source offline

Blocked by: slice 2 technically; scheduled after slice 5. Delivers restricted HTML preview/source editing and the supported offline source-language catalog. Seams: rendered preview/source actions, saved file reads, and built browser asset/network behavior.

- [ ] 6.1 Adapt the existing static HTML preview and add common source-editor switching; verify preview refresh, unchanged stored source, and script/network/sandbox restrictions, including downloadable/open-in-new-tab preview paths if retained.
- [ ] 6.2 Bundle the supported CodeMirror language catalog with filename/extension detection; verify the spec's representative languages load from Fred-hosted build assets with public-network access blocked and unknown text extensions fall back to plain text.
- [ ] 6.3 Verify keyboard source switching, localized loading/denied/missing/read-only/save-failure states, theme consistency, and enforcement of effective editability in both source and preview workflows.

## 7. Retire the demo bridge without breaking existing agents

Blocked by: slices 5 and 6. Delivers compatible retirement after replacement viewers work. Seams: capability catalog/configuration health, preparation/runtime assembly, and legacy/new conversation workflows.

- [ ] 7.1 Remove only `open_writable_document`, its registration/optional selection, importer tests, and obsolete copy-path references; verify saved retired selections do not suspend instances during Control Plane availability/config-health reconciliation or block preparation/execution, while unrelated missing IDs retain validation/suspension and no callable importer remains.
- [ ] 7.2 Preserve the main writable-document/HTML capabilities, legacy records/tables/routes/exports, and historical UI parts; verify a ReAct regression flow and a Deep Markdown/HTML workflow with no presentation capability selected, with no document migration.

## 8. Integration validation and close-out

Blocked by: all seven slices for final delivery. The archive dependency in 8.4 does not block implementation. Review checkpoints after slices 2 and 4 occur before proceeding to the next slice; final review covers the integrated change.

- [ ] 8.1 Obtain independent read-only reviews after slices 2 and 4; record base/head, covered seams, findings/dispositions, focused verification, and exclusions here or in the PR before continuing. Reuse valid evidence rather than rerunning unrelated checks.
- [ ] 8.2 Exercise the full offline parent/child write -> open -> human save -> next child read -> concatenate -> live refresh scenario with a large document; verify no parent document-body requirement and only bounded change-path metadata in model input.
- [ ] 8.3 At final integration, verify affected project tests, root `make code-quality`, and raw `basedpyright` where its baseline is non-empty, either locally or through equivalent successful CI jobs covering the integrated revision. Inspect actual CI coverage/results; run only uncovered required checks locally. Record commands/jobs, revision, outcomes, and limitations; keep default tests offline and mark real storage-provider tests as integration.
- [ ] 8.4 Before syncing/archiving this change, reconcile the completed `add-deep-agent-conversation-filesystem` delta's stale `/scratchpad/` requirements with implemented `/`, validate it, and sync/archive that foundation first; verify archive order without changing mounts or migrating data.
- [ ] 8.5 Update runtime execution contracts, relevant viewer guidance, and the operator migration note to match implemented APIs/coexistence; verify generated clients and docs agree and explicitly state no document migration is required.
- [ ] 8.6 Complete author and independent full-branch review against the actual PR target, plus applicable runtime performance review; resolve findings, record exact verification/exclusions, reconcile final artifacts, then sync/archive after 8.4 and all implementation/verification obligations are complete.
- [ ] 8.7 Push the integrated implementation and deliver a draft PR assigned to the requesting developer; verify it is conflict-free and required checks pass at its current head, with review evidence and remaining limitations recorded. Keep it draft for human review; do not merge automatically.

## Planning validation

The original independent planning review below predates the sequential-schedule revision.

- `openspec validate open-deep-conversation-files --strict`: passed.
- `git diff --cached --check` and artifact ASCII/local-link checks: passed.
- Independent read-only planning review against `13029601f` covered the proposed contracts and affected runtime, frontend, and capability-retirement consumers. Both findings were addressed: task 8.4 now blocks archival on reconciliation of the older filesystem delta; design, scenario, and task 7.1 now cover Control Plane suspension of saved retired selections.
- Application quality/test suites were not run because this change contains planning artifacts only. Implementation checks remain unchecked above; no runtime behavior is claimed as delivered.

- 2026-10-19 schedule revision: strict OpenSpec validation, whitespace, ASCII/local-link/task-reference checks, and `UV_CACHE_DIR=/tmp/fred-2706-uv-cache make migration-check` passed. Author review covered the six-file planning branch against `origin/swift` at `13029601f`, HEAD `61bfb560e` plus the design/tasks working changes: all original obligations retained, sequential dependencies consistent, and no product-scope changes or actionable findings. No new independent review or application tests were run for this documentation-only revision.


## Slice 1 focused verification (2026-10-19)

Implemented in `c723ccef0` (SDK/runtime) and `97d421471` (generated client/native panel). Results below were obtained on the corresponding implementation trees before commit; later changes were formatting, import placement, and this evidence only. Meaningful red/green checks covered missing serialization/tool/read behavior, child-stream propagation, model-visible metadata, effective deny/approval write policies, absent storage, prototype-like session identities, and late stream navigation.

- `libs/fred-runtime/.venv/bin/python -m pytest libs/fred-sdk/tests/test_context.py libs/fred-sdk/tests/test_ui_part_union_1977.py libs/fred-runtime/tests/test_deep_compiled_filesystem_tools.py -q`: 139 passed, 3 existing SDK skips before the final additional compiled cases; SDK serialization/union inputs are unchanged.
- `libs/fred-runtime/.venv/bin/python -m pytest libs/fred-runtime/tests/test_deep_compiled_filesystem_tools.py libs/fred-runtime/tests/test_deep_agent_middleware.py -q`: final compiled/middleware cases, 29 passed.
- `libs/fred-runtime/.venv/bin/python -m pytest libs/fred-runtime/tests/test_agent_app.py -q -k 'conversation_file_read or read_conversation_file or deep_parent_and_child_open_stream'`: 13 passed, followed by `-k conversation_file_read_requires_authentication`: 1 passed. Includes real standard parent/native-child execution through SSE, eventual public history read, and current file read, plus HTTP-boundary admission/ownership/traversal/content/mount cases. SQLite/filesystem tests ran outside the sandbox because sandbox worker wakeups hung; interrupted sandbox attempts are not passes.
- From `apps/frontend`, `node node_modules/vitest/vitest.mjs run src/rework/features/conversationFiles/ConversationFiles.test.tsx src/rework/core/hooks/useChatSse.test.tsx src/rework/components/pages/ManagedChatPage/ManagedChatPage.test.tsx`: initial targeted consumer regression, 121 passed. After final navigation/keyboard cases and component placement, the panel suite passed all 12 tests and the affected panel/page pair passed 60 tests. The existing 65 SSE cases are reused; no unrelated suites were run.
- From `apps/frontend`, `node node_modules/typescript/bin/tsc --noEmit --pretty false`: passed after final component placement. Prettier check of all changed frontend files and `git diff --check`: passed. Focused Ruff formatting/import checks passed for changed Python files.
- Regeneration: `libs/fred-runtime/.venv/bin/python libs/fred-runtime/scripts/generate_openapi.py`, then `apps/frontend/node_modules/.bin/rtk-query-codegen-openapi apps/frontend/src/slices/runtime/runtimeOpenApiConfig.json`. Runtime `openapi.json` is an ignored generated artifact; the regenerated frontend client is committed.
- Scoped author review against planning HEAD `ab39a41aa` covered identity, ownership/team/history reads, actual parent/child tools, stream/history consumers, generated routing, UI dispatch, source accessibility/theme/locales, navigation and reopening. Findings corrected: effective write policy rather than path-only editability; explicit model-visible metadata; always-present unavailable-storage error; stale stream navigation; prototype-like session IDs. No independent/full-branch review or manual browser session is claimed at this checkpoint. Required independent checkpoints and broad validation remain in section 8.

Slice 2 reuses `ConversationFilePart`/`ConversationFileResponse`, `ConversationFilesystemPort.is_editable`, the session's captured runtime route, the generated read query, `SourceEditor`'s controlled value/readOnly/onChange/language surface, and the exclusive `runtime:conversation-files` panel key. Extract and reuse the existing read authorization gate when adding saves; never authorize a browser write from posted metadata or `origin="system"`. The current source pane is intentionally read-only; save/flush/refresh coordination remains slice 2.


## Slice 2 focused verification (2026-10-19)

Backend implementation on the `f3dd2e993` working tree: save API red test returned 405 before implementation, then saved UTF-8 content was readable through the same conversation filesystem. Source-attribution test failed on the missing source boundary, then passed with server-bound propagation. `libs/fred-runtime/.venv/bin/python -m pytest libs/fred-runtime/tests/test_agent_app.py -q -k 'conversation_file_save or conversation_file_read or read_conversation_file'`: 25 passed (authenticated/foreign/unknown/historical team routing, forged origin/editability, traversal, `.deep`, same-path session isolation). `libs/fred-runtime/.venv/bin/python -m pytest libs/fred-runtime/tests/test_deep_conversation_filesystem.py -q`: 10 passed (full overwrite, exact-text edit, helper/system-origin attribution, user and independent system). `libs/fred-runtime/.venv/bin/python -m pytest libs/fred-runtime/tests/test_deep_compiled_filesystem_tools.py -q -k native_child_can_concatenate`: 1 passed, exercising native parent write, native child concat and parent concat with agent attribution. HTTP/compiled filesystem tests required sandbox escalation for worker wakeups; interrupted sandbox attempt is not a pass. Focused Ruff import/format checks passed. API generation used the slice 1 commands; the generated save client is included. The editor/composer block and its final focused evidence follow below. No independent checkpoint review is claimed here.

Final slice 2 implementation is `fc17bbd2f` (save/source boundary) plus `9876aa8cc` (editor/composer lifecycle and final API regressions). The final commands below ran on the corresponding source/test working tree immediately before `9876aa8cc`; only the design/tasks contract text was then reconciled before commit. The following evidence update changes documentation only.

- From `apps/frontend`, `node node_modules/vitest/vitest.mjs run src/rework/features/conversationFiles/ConversationFiles.test.tsx src/rework/components/pages/ManagedChatPage/useManagedChat.test.tsx src/rework/core/hooks/useChatSse.test.tsx src/rework/components/pages/ManagedChatPage/ManagedChatPage.test.tsx`: 218 passed. Includes rendered in-flight typing beyond the debounce window, failed-save draft reopening, switched/closed editor flush, stale refresh rejection, save reconciliation, actual tool/final refresh events, visible-only polling, slow-read completion, immediate continuation, once-only submit, and navigation away-and-back cancellation. HTTP is faked at the browser boundary; this is not a manual browser validation.
- From `apps/frontend`, `node node_modules/typescript/bin/tsc --noEmit --pretty false`: passed. Prettier check of the ten changed frontend source/test/locale files: passed.
- `libs/fred-runtime/.venv/bin/python -m pytest libs/fred-runtime/tests/test_agent_app.py -q -k 'conversation_file_save or conversation_file_read or read_conversation_file or deep_parent_and_child_open_stream or rejects_unsafe_owned_session_id' --tb=short --show-capture=no`: 29 passed. Includes real owned/historical HTTP saves, browser user attribution at the storage boundary, mounted skill and `.deep` write rejection, and save -> next native child's model receives saved content while the parent performs no read.
- `libs/fred-runtime/.venv/bin/python -m pytest libs/fred-runtime/tests/test_deep_compiled_filesystem_tools.py -q -k native_child_can_concatenate --tb=short --show-capture=no`: 1 passed with expanded native child full replacement plus native parent/child/helper concat attribution. The 10 unchanged namespace/port tests from the backend block are reused. All SQLite/provider-worker cases ran with the previously documented sandbox escalation.
- Focused Ruff checks/formatting for changed Python files, `git diff --check`, and `openspec validate open-deep-conversation-files --strict`: passed. Broad tests, root quality, raw basedpyright and independent review remain at their recorded integration/checkpoint gates.
- TDD red/green additionally established: editable source was initially read-only; composer originally sent before pending file saves; focus did not refresh; polling aborted a slow read; extracted service construction initially lost explicit unsafe-session HTTP error mapping. Each failed behavior was corrected at its approved public seam before the final passing checks.
- Scoped author review against slice 1 handoff `f3dd2e993`, final implementation `9876aa8cc`, covered save authentication/ownership/historical routing, mount/path/content policy, source propagation through all existing service constructors and provider mutations, native tool/helper consumers, generated API routing, common editor state, composer ownership, SSE refresh, localization/accessibility and close/navigation races. Findings corrected: coalesce refreshes instead of starving slow reads, restore explicit invalid-session errors, and use non-submit retry buttons. No remaining actionable finding in that scope. Root's independent slices 1/2 checkpoint and final full-branch/performance reviews remain required; no full PR review, production storage-provider integration or manual browser session is claimed.

Slice 3 handoff: consume the runtime namespace's server-bound `mutation_source` (`agent`, `user`, `independent_system`) at the existing successful mutation boundary; do not infer source from `origin` or ambient model/client metadata. Execution services bind `agent`, browser file services bind `user`, new independent services default to `independent_system`. Internal `.deep` and purge bookkeeping remain excluded from external history. No pending/history storage or user-turn boundary implementation was added in slice 2. Frontend future viewers must reuse the shared coordinator/hook and explicit flush documented in design section 4.

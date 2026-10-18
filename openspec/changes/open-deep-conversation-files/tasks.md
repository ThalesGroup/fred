# Tasks

Planning artifacts only are complete. The implementation tasks below remain unchecked intentionally.

## 1. Runtime contracts and authorized file access

- [ ] 1.1 Add the built-in typed conversation-file UI part and minimal file response models in `fred-sdk`; verify UI-part serialization, history round trips, and OpenAPI exposure without a presentation capability.
- [ ] 1.2 Add conversation-bound file read/save operations beside the runtime filesystem route, with explicit ownership, mount permissions, and normalized virtual paths; verify authorized access, unknown/foreign sessions, traversal, forged parts, and read-only saves using offline API tests.
- [ ] 1.3 Add file-backed Markdown download/Word export by reusing the existing converter; verify exports reflect the saved filesystem file and require no writable-document row.

## 2. Standard Deep open tool

- [ ] 2.1 Register `open(path)` through standard Deep assembly for parents and native children; verify both can present a file without optional capabilities, without reading it into model context, and without an execution pause.
- [ ] 2.2 Propagate child file-reference artifacts through the existing user-facing stream and history pipeline; verify a child open reaches the panel and survives conversation reload.
- [ ] 2.3 Return path/viewer/editability metadata and actionable missing/denied/unsupported errors; verify tool results contain no document body and do not claim browser acknowledgment.

## 3. External-change capture and publication

- [ ] 3.1 Add trusted mutation-source recording at the shared conversation filesystem boundary; verify parent, child, concatenation, and agent-invoked capability writes are excluded while user and independent-system writes are included, including during execution.
- [ ] 3.2 Persist per-file consolidated external groups in runtime-owned storage; verify autosave collapse, no-op/net-zero changes, failed writes, and A-to-B / agent B-to-C / C-to-D grouping without changing existing write semantics.
- [ ] 3.3 Seal pending intervals using the existing user exchange identity and publish full unified diffs; verify later-replica reads, resume/retry idempotency, boundary writes, and explicit storage/quota errors without acknowledging unpublished changes.
- [ ] 3.4 Implement flat `.diff` and numbered `.001.diff` naming with original source headers; verify nested/equal basenames, suffix collisions, Unicode, long paths, and ordering, and confirm `ls` alone discovers all artifacts with no index file.
- [ ] 3.5 Add static Deep filesystem guidance and short path-only turn-start notifications; verify zero changes produce no notification, large edits never inject content, count/length truncation retains a complete directory path, and no notifications interrupt a running turn.
- [ ] 3.6 Include pending state and published history in existing quota and erasure handling; verify earlier diffs survive normal turns and all conversation-owned files disappear on eligible erasure, without silent history eviction.

## 4. Native frontend viewers and save coordination

- [ ] 4.1 Regenerate runtime OpenAPI and frontend clients, then add built-in file-part dispatch and a session/path-keyed side-panel adapter; verify current-content reopening, deduplication, missing files, read-only state, and stale responses across navigation.
- [ ] 4.2 Reuse the Markdown editor with file-backed saving/export and keep its legacy adapter; verify the edit/save/Word-export flow and existing ReAct documents in frontend tests.
- [ ] 4.3 Adapt the existing static HTML preview to a filesystem file and add source editing; verify source preservation, preview refresh, and the existing script/network/sandbox restrictions, including downloadable/open-in-new-tab preview paths if retained.
- [ ] 4.4 Add the shared CodeMirror text editor and bundled language catalog; verify common-language highlighting, unknown-format fallback, and that a built deployment fetches all parser chunks from Fred with public-network access blocked.
- [ ] 4.5 Implement serialized autosave, explicit flush-before-send/export, dirty-buffer preservation, and bounded active-view refresh; verify immediate continuation, writes from children, typing during a save, agent writes while open, save failures, and navigation during a pending submission.
- [ ] 4.6 Apply localization, accessible labels, and existing theme tokens to file actions and states; verify keyboard opening/source switching and localized loading, denied, missing, read-only, and save-failure states.

## 5. Retire the demo bridge and preserve coexistence

- [ ] 5.1 Remove only the `open_writable_document` implementation, registration, optional selection, and obsolete copy-path references; verify saved retired selections do not cause Control Plane availability/config-health reconciliation to suspend the instance and remain usable through preparation/runtime assembly without a migration. Preserve validation/suspension for unrelated missing IDs and verify no callable importer remains.
- [ ] 5.2 Keep the main writable-document/HTML capabilities, legacy records, tables, routes, exports, and historical UI parts; verify a ReAct regression flow and a Deep agent with no presentation capability selected, without any document migration.

## 6. Integration validation and documentation

- [ ] 6.1 Exercise the full offline parent/child write -> open -> human save -> next child read -> concatenate -> live refresh scenario with a large document; verify the parent never needs the document body and model input contains only bounded change-path metadata.
- [ ] 6.2 Run `make code-quality` and `make test` in every implementation-touched project, plus raw `basedpyright` where its baseline is non-empty; record exact results here and keep default tests independent of third-party services. Mark any real storage-provider tests as integration.
- [ ] 6.3 Update the runtime execution contract, relevant viewer guidance, and required operator migration note to match the implemented APIs and coexistence behavior; verify generated clients and documentation references agree, explicitly recording that no document migration is required.
- [ ] 6.4 Before syncing or archiving this change, reconcile the completed `add-deep-agent-conversation-filesystem` delta's stale `/scratchpad/` requirements with the implemented `/` namespace, validate it, and sync/archive that foundation first. This is a blocking archive-order dependency, not a request to change mounts or migrate data.
- [ ] 6.5 Run the repository author/independent branch review and applicable runtime performance review; address findings, record verification in these tasks or the PR, and reconcile this delta with the final implementation before syncing/archiving the completed change, after task 6.4.

## Planning validation

- `openspec validate open-deep-conversation-files --strict`: passed.
- `git diff --cached --check` and artifact ASCII/local-link checks: passed.
- Independent read-only planning review against `13029601f` covered the proposed contracts and affected runtime, frontend, and capability-retirement consumers. Both findings were addressed: task 6.4 now blocks archival on reconciliation of the older filesystem delta; design, scenario, and task 5.1 now cover Control Plane suspension of saved retired selections.
- Application quality/test suites were not run because this change contains planning artifacts only. Implementation checks remain unchecked above; no runtime behavior is claimed as delivered.

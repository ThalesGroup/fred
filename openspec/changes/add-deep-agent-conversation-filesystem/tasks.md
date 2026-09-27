# Tasks

## 1. Conversation filesystem contracts and storage service

- [x] 1.1 Add the typed `ConversationScratchpadPort` contract and append it to `RuntimeServices`; verify contract tests cover text read, write/replace, expected-text edit, list, exists, and delete without exposing storage or `.deep` selection.
- [x] 1.2 Implement the conversation-bound filesystem service over `BaseFilesystem`, including safe `session_id` prefixing, virtual-path normalization, UTF-8 scratchpad validation, namespace scoping, and stable domain errors; verify focused tests reject traversal, cross-conversation access, binary scratchpad writes, and partial mutations.
- [x] 1.3 Implement create, full replacement, latest-text edit, listing, existence, deletion, and idempotent prefix purge semantics; verify tests prove stale edits preserve current content and explicit replacements use last-successful-write-wins behavior.
- [x] 1.4 Implement independent 100 MiB/1,000-file scratchpad and 1 GiB/10,000-file `.deep` quota defaults, with four independently overridable values in one grouped runtime setting, per-conversation in-process locking, initial recount, replacement deltas, and content-free metrics/logging; verify tests cover defaults, partial and complete configuration overrides, byte and count rejection, one-file use of the remaining budget, recount, and serialized same-process mutations.

## 2. Shared object-storage foundation and runtime wiring

- [x] 2.1 Add one Fred Runtime object-store/bucket configuration and a pod-lifetime `BaseFilesystem` factory using the deployment's provider credentials or workload identity; verify configuration tests cover local development plus supported MinIO/S3-compatible and GCS selections without feature-specific prefix settings.
- [x] 2.2 Make only the backward-compatible `BaseFilesystem` fixes required by the service, including safe recursive prefix deletion, consistent list/stat metadata, and non-blocking handling of synchronous cloud SDK operations; verify the shared filesystem contract suite passes for local and the available MinIO/GCS test fixtures.
- [x] 2.3 Bind a `ConversationScratchpadPort` to each turn's trusted `session_id` and inject it through `RuntimeServices`; verify two different conversation bindings cannot observe each other's files and two fresh bindings for one conversation observe the same stored data.

## 3. Deep Agents composite backend

- [x] 3.1 Implement one generic Deep `BackendProtocol` adapter over a configured conversation-filesystem namespace and a rejecting default backend; verify backend contract tests cover read/write/edit/list/glob/grep results and unsupported paths without duplicating scratchpad and `.deep` logic.
- [x] 3.2 Construct the per-conversation composite backend with `/scratchpad/`, `/.deep/`, and `artifacts_root=/.deep`, then pass the same scope to the parent and native subagents; verify a compiled deterministic Deep graph proves live child-to-parent and sibling visibility before child-state merge.
- [x] 3.3 Enable the standard safe filesystem tool names for every Deep agent while keeping `execute` blocked, and enforce model-read-only access to `/.deep/` without blocking trusted Deep middleware writes; verify compiled-runtime tests cover an agent without optional filesystem capability, rejected model writes to `.deep`, readable internal artifacts, and persistent large-tool-result storage.
- [x] 3.4 Verify a later turn built with a fresh runtime/backend instance reads the prior turn's scratchpad through shared storage and that storage failure returns an explicit tool error without creating checkpoint or local fallback data.

## 4. Conversation erasure lifecycle

- [x] 4.1 Add an authenticated internal Fred Runtime cleanup operation that idempotently purges both conversation filesystem prefixes using existing history-backed ownership checks; verify endpoint tests cover success, already-missing data, wrong ownership, and storage failure.
- [x] 4.2 Extend the Control Plane runtime client and erasure receipt with the conversation-filesystem store between checkpoint and history deletion; verify existing erasure-order tests prove that failure retains history and session metadata for retry, while a retry converges after partial deletion.
- [x] 4.3 Verify recovery-window processing reaches the same erasure path and removes scratchpad plus `.deep` objects only when the conversation becomes eligible, using the existing scheduled-erasure test seam.

## 5. Deployment, compatibility, and review

- [x] 5.1 Add deployment configuration and concise operator documentation for provisioning one private Fred Runtime bucket, its workload permissions, optional runtime-settings quota overrides, and rollback constraint; verify checked-in configuration files and charts contain neither feature-prefix settings nor quota values and that omitted overrides use code defaults.
- [x] 5.2 Reconcile the in-flight `deep-agent-runtime-baseline` filesystem wording so runtime-provided safe tools count as bound while `execute` remains unavailable; verify the two OpenSpec deltas have no contradictory filesystem requirements before either is archived.
- [x] 5.3 Document the lack of checkpoint-file migration and verify an upgrade test or release note makes the active-conversation limitation explicit without adding a legacy read-through path.
- [x] 5.4 With the developer's explicit approval, run the focused fred-core, fred-sdk, fred-runtime, and Control Plane test selections; record commands and outcomes in the change before implementation review, and delegate the repository-wide suite and required quality checks to draft-PR CI.
- [x] 5.5 Review the completed diff against #2738, #2751, #2752, this capability spec, and the out-of-scope list; verify corpus, attachment, skill, UI editor, binary-file, distributed-quota, and storage-consolidation work did not enter the implementation.

## Verification Evidence

- `libs/fred-runtime/.venv/bin/python -m pytest -q libs/fred-sdk/tests/test_conversation_scratchpad_port.py -x` — 1 passed.
- `libs/fred-runtime/.venv/bin/python -m pytest -q libs/fred-core/fred_core/tests/filesystem/test_local_filesystem.py libs/fred-core/fred_core/tests/filesystem/test_minio_filesystem.py libs/fred-core/fred_core/tests/filesystem/test_gcs_filesystem.py -x` — 19 passed.
- `libs/fred-runtime/.venv/bin/python -m pytest -q libs/fred-runtime/tests/test_conversation_filesystem.py libs/fred-runtime/tests/test_filesystem_factory.py libs/fred-runtime/tests/test_deep_conversation_filesystem.py libs/fred-runtime/tests/test_deep_internal_filesystem.py libs/fred-runtime/tests/test_deep_compiled_filesystem_tools.py libs/fred-runtime/tests/test_deep_agent_middleware.py -x` — 59 passed with one existing Pydantic serialization warning.
- Focused Runtime cleanup, Control Plane erasure, and recovery-window selections — 3, 6, and 1 tests passed respectively.
- `PYTHONPATH=apps/control-plane-backend libs/fred-runtime/.venv/bin/python -m pytest -q apps/control-plane-backend/tests/test_runtime_http_client.py apps/control-plane-backend/tests/test_erasure_service_checkpoint_receipt.py apps/control-plane-backend/tests/test_main.py apps/control-plane-backend/tests/test_lifecycle_actions.py -k 'runtime_http_client or checkpoint or erase_session_deletes_checkpoint_filesystem_then_history or erase_session_filesystem_failure_retains_history_and_retries or erase_session_skips_history_when_checkpoint_fails or recovery_window_erases_filesystem_only_when_due_and_records_result' -x` — 12 passed, 179 deselected.
- Ruff over every changed Python file, targeted `py_compile`, `git diff --check`, and strict validation of this change plus `deep-agent-runtime-baseline` passed.
- Scope review against #2738, #2751, #2752, and this change found no corpus, attachment, or skill mounts; UI editor or public scratchpad API; binary scratchpad support; distributed quota transaction; sandbox execution; or broader storage-abstraction consolidation. The PR references #2751 without closing it because its corpus and attachment work remains deferred.
- The repository-wide test suite and required quality checks are intentionally delegated to draft-PR CI per developer instruction.

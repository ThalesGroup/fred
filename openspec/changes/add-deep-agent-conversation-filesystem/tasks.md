# Tasks

## 1. Conversation filesystem contracts and storage service

- [ ] 1.1 Add the typed `ConversationScratchpadPort` contract and append it to `RuntimeServices`; verify contract tests cover text read, write/replace, expected-text edit, list, exists, and delete without exposing storage or `.deep` selection.
- [ ] 1.2 Implement the conversation-bound filesystem service over `BaseFilesystem`, including safe `session_id` prefixing, virtual-path normalization, UTF-8 scratchpad validation, namespace scoping, and stable domain errors; verify focused tests reject traversal, cross-conversation access, binary scratchpad writes, and partial mutations.
- [ ] 1.3 Implement create, full replacement, latest-text edit, listing, existence, deletion, and idempotent prefix purge semantics; verify tests prove stale edits preserve current content and explicit replacements use last-successful-write-wins behavior.
- [ ] 1.4 Implement independent 100 MiB/1,000-file scratchpad and 1 GiB/10,000-file `.deep` quota defaults, with four independently overridable values in one grouped runtime setting, per-conversation in-process locking, initial recount, replacement deltas, and content-free metrics/logging; verify tests cover defaults, partial and complete configuration overrides, byte and count rejection, one-file use of the remaining budget, recount, and serialized same-process mutations.

## 2. Shared object-storage foundation and runtime wiring

- [ ] 2.1 Add one Fred Runtime object-store/bucket configuration and a pod-lifetime `BaseFilesystem` factory using the deployment's provider credentials or workload identity; verify configuration tests cover local development plus supported MinIO/S3-compatible and GCS selections without feature-specific prefix settings.
- [ ] 2.2 Make only the backward-compatible `BaseFilesystem` fixes required by the service, including safe recursive prefix deletion, consistent list/stat metadata, and non-blocking handling of synchronous cloud SDK operations; verify the shared filesystem contract suite passes for local and the available MinIO/GCS test fixtures.
- [ ] 2.3 Bind a `ConversationScratchpadPort` to each turn's trusted `session_id` and inject it through `RuntimeServices`; verify two different conversation bindings cannot observe each other's files and two fresh bindings for one conversation observe the same stored data.

## 3. Deep Agents composite backend

- [ ] 3.1 Implement one generic Deep `BackendProtocol` adapter over a configured conversation-filesystem namespace and a rejecting default backend; verify backend contract tests cover read/write/edit/list/glob/grep results and unsupported paths without duplicating scratchpad and `.deep` logic.
- [ ] 3.2 Construct the per-conversation composite backend with `/scratchpad/`, `/.deep/`, and `artifacts_root=/.deep`, then pass the same scope to the parent and native subagents; verify a compiled deterministic Deep graph proves live child-to-parent and sibling visibility before child-state merge.
- [ ] 3.3 Enable the standard safe filesystem tool names for every Deep agent while keeping `execute` blocked, and enforce model-read-only access to `/.deep/` without blocking trusted Deep middleware writes; verify compiled-runtime tests cover an agent without optional filesystem capability, rejected model writes to `.deep`, readable internal artifacts, and persistent large-tool-result storage.
- [ ] 3.4 Verify a later turn built with a fresh runtime/backend instance reads the prior turn's scratchpad through shared storage and that storage failure returns an explicit tool error without creating checkpoint or local fallback data.

## 4. Conversation erasure lifecycle

- [ ] 4.1 Add an authenticated internal Fred Runtime cleanup operation that idempotently purges both conversation filesystem prefixes using existing history-backed ownership checks; verify endpoint tests cover success, already-missing data, wrong ownership, and storage failure.
- [ ] 4.2 Extend the Control Plane runtime client and erasure receipt with the conversation-filesystem store between checkpoint and history deletion; verify existing erasure-order tests prove that failure retains history and session metadata for retry, while a retry converges after partial deletion.
- [ ] 4.3 Verify recovery-window processing reaches the same erasure path and removes scratchpad plus `.deep` objects only when the conversation becomes eligible, using the existing scheduled-erasure test seam.

## 5. Deployment, compatibility, and review

- [ ] 5.1 Add deployment configuration and concise operator documentation for provisioning one private Fred Runtime bucket, its workload permissions, optional runtime-settings quota overrides, and rollback constraint; verify checked-in configuration files and charts contain neither feature-prefix settings nor quota values and that omitted overrides use code defaults.
- [ ] 5.2 Reconcile the in-flight `deep-agent-runtime-baseline` filesystem wording so runtime-provided safe tools count as bound while `execute` remains unavailable; verify the two OpenSpec deltas have no contradictory filesystem requirements before either is archived.
- [ ] 5.3 Document the lack of checkpoint-file migration and verify an upgrade test or release note makes the active-conversation limitation explicit without adding a legacy read-through path.
- [ ] 5.4 With the developer's explicit approval, run the focused fred-core, fred-sdk, fred-runtime, and Control Plane test selections plus the repository-required quality checks; record commands and outcomes in the change before implementation review.
- [ ] 5.5 Review the completed diff against #2738, #2751, #2752, this capability spec, and the out-of-scope list; verify corpus, attachment, skill, UI editor, binary-file, distributed-quota, and storage-consolidation work did not enter the implementation.

# Design

## Context

See [proposal.md](proposal.md) for motivation and [the delta spec](specs/managed-conversations/spec.md) for observable requirements. The design was checked against `swift` at `13029601f`.

- `libs/fred-runtime/fred_runtime/conversation_filesystem.py` already persists conversation files in the configured shared storage. Deep mounts the working namespace at `/` and internal artifacts at `/.deep/`. Parent and native children share that backend.
- `deep/conversation_backend.py` implements native reads, full writes, and exact-text edits. `deep/conversation_port.py` exposes the filesystem to capabilities; `deep/concat_files.py` supports explicit output replacement. No read-before-write enforcement is present or added here.
- `OpenWritableDocumentCapability` copies a file into legacy writable-document storage. The legacy editor and export router are useful reusable components; its copied document identity is not the identity for this feature.
- The frontend already has typed UI-part dispatch, native side panels, MDXEditor, CodeMirror consumers, and a static HTML viewer with sanitization, sandboxing, and CSP. No iframe extension host is needed for this delivery.
- The existing `add-deep-agent-conversation-filesystem` change is implementation-complete but unarchived and still describes older `/scratchpad/` naming. This follow-on uses the actual `/` mount and does not reopen its completed storage work. Before this change is synced or archived, reconcile the older delta to the implemented root namespace, validate it, and sync/archive it first (task 8.4). Do not implement a second mount or migrate paths here.

## Goals / Non-Goals

**Goals:** keep one authoritative live file; reuse native viewers and storage; make the review/edit/delegate loop work without loading large documents into parent context; preserve the existing ReAct product surface.

**Non-goals:** a general file manager, a revision/merge UI, stronger concurrent-write guarantees, a permanent audit service, legacy data migration, new resource mounts, or an extensible iframe application framework. The future ideas below do not create implementation tasks or public contracts in this change.

## Decisions

### 1. Put presentation in the standard Deep frame

Add `open(path)` through the runtime's standard Deep tool/middleware assembly, including the native child tool set. This is not a selectable capability. Reuse the tool-result artifact/UI-part pipeline so a child call reaches the same parent conversation stream and persisted history.

Introduce a built-in SDK UI part for a conversation file reference. Its identity is the trusted session plus normalized absolute virtual path; presentation metadata includes the resolved native viewer and effective editability. The session comes from execution context, not a model-supplied argument. Return a short textual result describing the presentation request, not the file body or a claim that the browser acknowledged it. `open` neither imports content nor pauses the agent.

Use a small built-in file-type mapping: Markdown, HTML, other text. Reuse the same resolved metadata in tool results and frontend dispatch. No extension registration API, external viewer URL, or capability asset manifest is introduced. Missing files and unreadable/unsupported content return actionable errors.

Reopening a reference fetches current content. Reuse the existing side-panel file-switching pattern and deduplicate references by session/path; do not add a filesystem browsing product. Parent and child opens are both allowed to select the displayed file in event order.

### 2. Add authorized file access beside the runtime session filesystem route

Extend the existing runtime `/agents/sessions/{session_id}/filesystem` route family with typed file read/save and Markdown export operations, using a virtual path parameter rather than a physical storage key. Keep content in the runtime pod; Control Plane supplies existing browser-safe session/runtime routing, not a content proxy or new document store. Register SDK UI-part changes in `ui_part_union.py` and regenerate runtime OpenAPI and frontend clients.

Every operation must authenticate and establish session ownership/access before touching storage. Do not reuse the permissive new-session ownership path for an unknown session, trust a posted UI part as authorization, or use `origin="system"` to authorize browser writes: that origin bypasses agent permission rules. Resolve allowed file access and mount editability explicitly, keep `/.deep/` runtime-managed and non-writable by editors, and reject traversal or namespace escape. Preserve existing team admission and historical-session routing rules without requiring an agent execution merely to read a file.

Start with the existing text mounts; do not add corpus, attachment, PDF, or binary adapters. A readable file on a non-editable mount can use the text viewer in read-only mode. A returned editable flag is a UI hint, never the server's authorization decision.

### 3. Reuse viewers and conversion without their legacy storage coupling

- **Markdown:** extract/reuse the existing editor surface and conversion helper with a file-backed adapter. Keep the legacy adapter intact. Export reads the latest saved Markdown directly; downloading/exporting first flushes that editor's pending save.
- **HTML:** reuse `HtmlArtifactPane` preview behavior and `composeHtmlDocument` restrictions for a single `.html` file. Add Preview/Source switching with the common source editor. Rendering sanitizes a derived preview only; the editable file remains unchanged. No script execution, external resources, sibling assets, or dashboard data loading.
- **Other text / HTML source:** use CodeMirror with filename/extension language detection and the standard supported language catalog, loaded as local build chunks. Unknown extensions use plain text. Bundle all selected parsers into Fred's distributable assets; dynamic import must not mean a CDN request. Support highlighting and basic editing, not IDE services or execution.

Use existing theme tokens, localization, accessible labels, and loading/error patterns. Do not copy an editor, export converter, or HTML sanitization implementation into a second feature directory.

### 4. Refresh views and flush saves without adding merge semantics

Keep debounced autosave, with an explicit flush operation shared by message submission and export. Serialize saves from each editor; acknowledge the buffer version that was actually sent so edits typed during an in-flight request remain dirty. Before the next user message starts execution, await pending saves in that conversation. On error, preserve drafts and do not submit. Navigation invalidates a pending send for the old session.

Use the generated file query/cache keyed by session/path. Refresh active clean views on relevant tool completion, run completion, save completion, and window focus; a bounded refresh while visible covers writes from another replica or tab without requiring a new SSE event protocol. Reuse content validators when available; otherwise compare returned content. Cancel refresh work on close/navigation and reject stale responses. Never overwrite a dirty buffer with a refresh response; reconcile after its save completes. The chosen refresh cadence is an implementation tuning value, not a real-time synchronization guarantee.

Preserve current last-successful-full-write and exact-text edit behavior. In particular, `concat_files(..., replace=True)` remains usable without the orchestrator reading the assembled output. No new write guard is introduced in tool middleware, the filesystem backend, or editor APIs.

### 5. Record mutation source at the shared filesystem boundary

A start-to-start snapshot diff cannot exclude interleaved agent writes. Extend the conversation filesystem mutation path with a small durable pending-change accumulator instead. Observe native tools, capability/helper writes, and editor saves at that shared boundary rather than adding a second recorder to each viewer.

Keep authorization origin distinct from mutation source. Server-assigned source identifies an agent execution (including its children and tool helpers), a user save, or an independent background operation. A model/client cannot label its own write as trusted system activity. Internal `/.deep/` writes never enter the recorder.

For each externally modified working file, retain the content before the first external mutation and the latest successful content of that group. Further external saves update the group's end state. A successful agent mutation of that same file closes the external group; a later external mutation begins another. Failed writes do not become completed edits, same-content saves are no-ops, and a net-zero group produces no diff. Existing create/delete operations can be represented with standard `/dev/null` diff headers; this feature adds no file-management UI.

Keep the pending state under the existing runtime-owned conversation storage, outside the public diff directory. It is historical bookkeeping, not another authoritative editable document or a new database table. Only touched files need baselines; do not snapshot/read every workspace file at every turn. Do not retain every autosave step after consolidation.

### 6. Publish flat immutable history at the next user-turn start

Use the runtime's existing user exchange identity for `<turn-id>`, not an LLM step counter, request retry identifier, or native child invocation. Before the parent model starts, capture the pending interval, publish its complete diffs, then acknowledge that interval. Reusing the same exchange must reuse its publication; a resume must not drain changes belonging to the next user turn. A write after the boundary stays pending for that next turn.

Choose artifact names only when sealing the interval, so published paths never need renaming:

```text
/.deep/changes/<turn-id>/
  report.md.diff
  summary.md.001.diff
  summary.md.002.diff
```

One non-empty external group uses `<source-name>.diff`; multiple groups use `<source-name>.<sequence>.diff`, with zero-padded chronological numbering. Each unified diff has the original absolute virtual path in its before/after headers and a group label when split. Historical segments are not a combined patch against the current file.

For nested paths, flatten with a deterministic escaped path; preserve simple names such as `report.md`. Disambiguate collisions (including names that already resemble `.001`) or overlong names with a stable source-path hash. The original path in the diff headers is authoritative, so the agent never needs to decode an artifact name. Test equal basenames, encoded separators, Unicode, suffix-like names, and sufficiently many segments for numeric ordering.

There is no `index.json` or agent-visible manifest. Standard `ls` lists the sealed turn's diffs directly; `glob`, `grep`, and partial `read_file` provide discovery. Internal publication bookkeeping must not appear as extra files in that listing.

### 7. Inject one short path-only notification

Static Deep instructions explain numbered segments, the external-change window, `ls` fallback, and reading the current file before relying on historical changes. Install those instructions through the standard frame for parents and children; do not repeat the explanation in per-turn notifications or require the parent to inspect changes before delegating.

At a new user-turn start, notify the parent of the distinct source-file count and published diff paths. Do not inject document contents, diff snippets, or an LLM summary. Provisional implementation defaults are at most 10 paths and 2,048 characters for the complete notification; these are inexpensive tunable bounds, not a content budget. Reserve room for the count, truncation indication, and directory path before adding entries. Never cut a path in the middle. When no changes remain after consolidation, inject nothing.

Example after truncation:

```text
12 files changed by users or independent systems since your previous turn began.
Changes: /.deep/changes/<turn-id>/report.md.diff, ...
List truncated. All changes: /.deep/changes/<turn-id>/
```

Encode/quote filenames as data. The tool result of `open` and this notification must remain bounded even for very large file contents. No model notification is sent when a save happens during execution.

### 8. Retain history and retire only the temporary bridge

Use existing conversation prefixes, shared storage, quotas, and erasure/recovery policy for pending state and published diffs. Do not silently prune old history. Report storage/quota failures without falling back to local state. Publication failures preserve the unacknowledged interval; retries must not claim a complete empty interval or discard it. A partially completed save must report its actual outcome rather than pretending to be transactional.

Remove `OpenWritableDocumentCapability`, its registration, optional selection, importer tests, and obsolete prompt/catalog references. Current capability assembly rejects unknown IDs, so removing registration alone is insufficient. Treat this specific retired ID as inactive when resolving saved selections, including preparation/catalog consumers and Control Plane availability/config-health reconciliation. The existing suspension sweep must not suspend an instance merely because its saved selection contains this retired ID; unrelated missing capabilities must retain their existing validation and suspension behavior. Do not preserve a callable copy tool as the compatibility mechanism or run a data migration. Leave imported documents in legacy storage.

The main `writable_document` and `html_artifact` capabilities, tables, APIs, and historical UI parts remain. Deep users can use the built-in file workflow without those selections; do not require a new "open capability" checkbox. Do not migrate existing documents or delete the main capabilities as part of this delivery.

## Implementation sequencing and ownership

Implement the seven vertical slices in [tasks.md](tasks.md) sequentially, with one active implementation owner and one integrated working tree. Quality and token economy take precedence over throughput. Each slice owns a narrow observable workflow across every affected layer and its focused tests; intermediate checkpoints do not claim the complete feature is shippable. Do not divide ownership into independent backend/frontend/test projects.

Use a fresh focused implementation context per slice by default. Reuse the previous implementer only while its context remains useful and bounded; slices 3 and 4 are the strongest candidate. Ownership belongs to the slice, not a permanent agent identity. The orchestrator retains cross-slice decisions, manages shared registrations and generated-artifact reconciliation, reviews integration, and records evidence in the existing tasks/PR. Workers regenerate clients alongside their API changes; generated files are never hand-edited. Commit completed reviewable blocks and integrate/verify each slice before dispatching the next. Separate worktrees are unnecessary for this serial arrangement.

Before each handoff, identify the affected shared contracts below and the public seams listed in that slice. Record concrete interface choices here as they are settled within the approved design; surface any product-contract change before expanding scope. Small reuse extractions belong immediately before their use in the owning slice, not in a broad speculative prefactoring project.

| Shared contract | Owner and agreement |
| --- | --- |
| File identity/presentation | Slice 1 establishes trusted session plus normalized path, typed UI reference, and the common viewer/editability mapping. Later viewers extend this path without introducing another identity. |
| Browser access | Slices 1/2 own authorized read/save models, consistent errors, routing and generated clients; slice 5 adds export using those same access rules. |
| Editor lifecycle | Slice 2 owns load/save/flush/refresh coordination, buffer-version acknowledgment and navigation cancellation; slices 5/6 reuse it. |
| Mutation attribution | Slice 2 establishes trusted source propagation, separate from authorization origin; slices 3/4 consume it at the shared filesystem boundary for all writer kinds. |
| Turn publication | Slice 3 owns exchange identity, durable boundary capture, idempotent publication/acknowledgment and notification; slice 4 extends external-group segmentation without redefining the boundary. |
| Legacy coexistence | Slice 5 preserves legacy editor/conversion adapters; slice 7 owns retirement across catalog, preparation, runtime assembly and Control Plane health. |

A handoff contains the slice objective, relevant spec/design references, owned scope and shared contracts, integrated revision, accepted public test seams, reusable verification evidence, and unresolved questions. It does not repeat the full specification. Independent reviewers receive requirements and the actual diff/evidence, not expected findings. Review the shared open/edit foundation after slice 2, history after slice 4, and the full integrated branch at close-out; reviews run sequentially too.

The dependency graph permits slices 3, 5 and 6 after slice 2, but implementation deliberately runs 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7. This avoids concurrent shared-module edits and branch reconciliation at the cost of elapsed time. Models, reasoning settings and session-specific worker instructions belong in the implementation handoff, not the durable capability requirements. The tasks retain the testing policy and delivery gates so they survive a handoff change.

## Risks / Trade-offs

- **Concurrent edits can be overwritten:** accepted for this version. Preserve existing mutation semantics and local drafts; evaluate stronger guards separately rather than claiming read tracking or automatic merge.
- **The storage layer has no cross-replica transaction/CAS:** durable pending state and idempotent publication must work for sequential operations across replicas. Simultaneous writes retain the existing race limitations; the history is contextual information, not a linearizable audit log. Do not claim an in-process lock solves distributed races.
- **Large files and many groups consume internal quota:** consolidate autosaves, diff only touched files off the model context path, honor existing quotas, and surface failures. Do not add hidden retention eviction or an unbounded notification.
- **Refresh can race navigation or user typing:** key all state by session/path, serialize local saves, preserve dirty buffers, and test stale responses explicitly.
- **Permission drift or forged UI parts:** reauthorize file operations on the server. Neither a stored editable flag nor system-origin access is sufficient authority.
- **Old filesystem planning text is stale:** task 8.4 blocks sync/archive of this change until the older delta agrees with the implemented root namespace and is synced/archived first. Strict validation of this delta alone cannot establish cross-change consistency.

## Migration Plan

This planning change performs no deployment or migration. Implementation adds compatible typed runtime APIs/UI parts and the native viewer client together, retires the demo selection with the narrowly scoped compatibility behavior above, and leaves legacy records untouched. Regenerate clients and provide the normal operator migration note when shipping implementation; it must explicitly say no document migration is required.

For rollback, retain both legacy rows and conversation files. An older frontend may not render the new file-reference UI part, but must not lose or reinterpret stored file content. Do not convert files into legacy rows during rollback. No migration script is required in this change.

## Future Ideas

Deferred exploration only: capability-packaged UI served by Fred Runtime, external iframe URLs, extension-specific viewers such as `.quiz.json`, administrator-provided defaults, CSV/PDF viewers, and generated interactive HTML dashboards using workspace data. Reuse the existing app iframe SDK's theme/locale support if that work becomes concrete. Generated HTML remains untrusted; the future access boundary is not decided here. A Skill could teach generation conventions, but would not itself grant browser privileges. Do not build a dormant extension framework or dashboard serving directory for this PR.

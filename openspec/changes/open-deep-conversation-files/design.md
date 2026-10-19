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

Slice 1 settles the shared read/presentation interfaces as follows:

- SDK `ConversationFilePart` uses `type="conversation_file"`, trusted `session_id`, validated absolute `path`, `viewer` (`markdown`, `html`, `text`), and `editable`; `ConversationFileResponse` adds current UTF-8 `content`. Paths are limited to 4,096 characters and session IDs to 256. Viewer selection uses `.md`/`.markdown`, `.html`/`.htm`, then plain text.
- `ConversationFilesystemPort.is_editable(path)` is a non-mutating policy query, conservatively false for unknown adapters. The Deep adapter uses the same ordered write rules and mounted skills restriction as mutation calls; deny and approval-required rules both mean read-only. Browser access recomputes its own policy, independent of a posted reference.
- `GET /agents/sessions/{session_id}/filesystem/file?path=...&team_id=...` rejects unknown/foreign runtime history before storage access. Authenticated calls also read the existing Control Plane team/session-details route with the browser bearer, reusing team admission, owner checks and historical-session behavior without preparing execution. Missing authorization/storage returns 503; denied access 403; unsafe paths 422; missing files 404; unsupported UTF-8/NUL content 415.
- `open` middleware returns an actionable typed error when it lacks a filesystem port. That fallback was tested with an independently supplied backend; ordinary Deep runtime setup still requires configured conversation storage and raises before execution when storage is absent. This change does not add storage-free Deep execution. A successful `open` result quotes path/viewer/editability as bounded JSON metadata. Native-child updates expose only built-in file references through runtime tool-result events and the existing final UI-part/history pipeline; child answer/thought chunks stay private.
- The frontend routes generated read queries through the session's captured `messages_url` prefix. Query identity includes session/path/team, and the reference selector deduplicates files by session/path. Each live tool-result presentation requests selection in event order; history cards reopen current content explicitly. The built-in panel shares the exclusive push-drawer slot and starts with a reusable, read-only CodeMirror source surface. Markdown/HTML-specific views and editing remain with their later slices.

Browser saves use `PUT /agents/sessions/{session_id}/filesystem/file?path=...&team_id=...` and `ConversationFileSaveRequest(content)` with extra fields forbidden. Save and read share the owned-session/historical-team authorization gate. Effective server write policy is checked before a normal `origin="agent"` full replacement. The browser cannot request privileged origin or override editability; unsupported content, policy, path, quota and storage failures are explicit.


### 3. Reuse viewers and conversion without their legacy storage coupling

- **Markdown:** extract/reuse the existing editor surface and conversion helper with a file-backed adapter. Keep the legacy adapter intact. Export reads the latest saved Markdown directly; downloading/exporting first flushes that editor's pending save.
- **HTML:** reuse `HtmlArtifactPane` preview behavior and `composeHtmlDocument` restrictions for a single `.html` file. Add Preview/Source switching with the common source editor. Rendering sanitizes a derived preview only; the editable file remains unchanged. No script execution, external resources, sibling assets, or dashboard data loading.
- **Other text / HTML source:** use CodeMirror with filename/extension language detection and the standard supported language catalog, loaded as local build chunks. Unknown extensions use plain text. Bundle all selected parsers into Fred's distributable assets; dynamic import must not mean a CDN request. Support highlighting and basic editing, not IDE services or execution.

Use existing theme tokens, localization, accessible labels, and loading/error patterns. Do not copy an editor, export converter, or HTML sanitization implementation into a second feature directory.

### 4. Refresh views and flush saves without adding merge semantics

Keep debounced autosave, with an explicit flush operation shared by message submission and export. Serialize saves from each editor; acknowledge the buffer version that was actually sent so edits typed during an in-flight request remain dirty. Before the next user message starts execution, await pending saves in that conversation. On error, preserve drafts and do not submit. Navigation invalidates a pending send for the old session.

Use the generated file query/cache keyed by session/path. Refresh active clean views on relevant tool completion, run completion, save completion, and window focus; a bounded refresh while visible covers writes from another replica or tab without requiring a new SSE event protocol. Reuse content validators when available; otherwise compare returned content. Cancel refresh work on close/navigation and reject stale responses. Never overwrite a dirty buffer with a refresh response; reconcile after its save completes. The chosen refresh cadence is an implementation tuning value, not a real-time synchronization guarantee.

Preserve current last-successful-full-write and exact-text edit behavior. In particular, `concat_files(..., replace=True)` remains usable without the orchestrator reading the assembled output. No new write guard is introduced in tool middleware, the filesystem backend, or editor APIs.

Slice 2's common lifecycle is `conversationEditorsFor(store)` plus `useConversationFileEditor(...)`. The coordinator is browser/store-local, keyed by `[sessionId, teamId, path]`; it retains drafts across file switches, drawer close, and conversation navigation for that store's lifetime (not browser reload). A 600 ms debounce serializes each file's full saves, acknowledges the content actually sent, and leaves newer typing dirty. `flushConversationEditors(sessionId)` repeatedly drains every dirty/in-flight editor for that conversation, including closed or switched files. The managed composer's existing send-attempt ownership covers this barrier: failures keep both drafts and report a localized error; duplicate submits and navigation, including away-and-back, cannot start the old attempt.

`useConversationFileEditor` owns the generated session/path/team read subscription, refresh generation and cancellation. Clean active views refresh after tool/final events, successful saves, focus/visibility return and a 5 second visible-only poll. Concurrent refresh triggers coalesce behind the current read so slow storage still completes. A response is accepted only if its mounted identity/generation and local buffer version still match and no save is in flight; dirty buffers never accept remote replacement. Close/navigation abort reads and cancel timers/listeners; save work continues against its original identity. Successful saves trigger a fresh current-file read. Markdown and HTML adapters in slices 5/6 reuse this hook/coordinator rather than adding their own draft or refresh owner.

Slice 5 Markdown/export decisions:
- `MarkdownEditor` is a shared molecule containing the existing MDX plugins, import preparation and theme styles. The legacy pane keeps its document adapter/keying; the filesystem panel feeds the common draft coordinator. External clean content uses MDX's public `setMarkdown` (which mutes change callbacks), while typing keeps the editor mounted and normalization never creates a save.
- `GET /agents/sessions/{session_id}/filesystem/export?path=...&format=md|docx&team_id=...` repeats the owned-session/team/path read authorization for every request, requires the current file's Markdown viewer, and permits export of authorized read-only Markdown. It reads current saved content and creates no legacy record. DOCX conversion runs in a worker thread; Markdown passes through byte-for-byte. Responses use a safe attachment filename and `Cache-Control: no-store`.
- The pure converter/parser live in `fred_core.documents` with legacy import shims. `fred-core[docx]` declares python-docx; runtime `app` and the legacy capability select that extra independently of capability registration. Existing resolved package versions remain unchanged. Binary browser downloads share authenticated transport, consume generated export request types, flush only the exporting file through the shared coordinator first (composer submission still flushes the full conversation), and abort on panel/navigation identity changes. Save/download failures keep drafts and report localized errors.

Slice 6 HTML/source decisions:
- `HtmlPreview` is the shared molecule extracted from `HtmlArtifactPane`: both adapters use its existing double-buffered opaque `sandbox=""` iframes and unchanged `composeHtmlDocument` sanitization/CSP. The document and buffer helpers have legacy re-exports. Inactive frames are hidden from keyboard/ARIA; the preview retains the paper canvas through `--surface-picture`, while surrounding controls and source highlighting follow theme tokens.
- The filesystem panel selects HTML from authorized `FileDraft.viewer`, defaults to Preview, and switches to the common `SourceEditor` with arrow/Home/End keyboard controls. It previews the current draft without modifying it, and uses the existing coordinator for all saves, refreshes, failures and read-only policy. No file-backed download/new-tab action was added; the retained legacy actions use the same restricted document helpers.
- `SourceEditor.filename` uses the standard `@codemirror/language-data` catalog and basename/extension detection. Its literal dynamic imports become local Vite assets; stale async loads are ignored, and unknown filenames or failed language loads remain editable plain text according to effective policy. The existing explicit language prop still overrides filename detection. The catalog was already resolved transitively; making it direct changes no resolved package version.

### 5. Record mutation source at the shared filesystem boundary

A start-to-start snapshot diff cannot exclude interleaved agent writes. Extend the conversation filesystem mutation path with a small durable pending-change accumulator instead. Observe native tools, capability/helper writes, and editor saves at that shared boundary rather than adding a second recorder to each viewer.

Keep authorization origin distinct from mutation source. Server-assigned source identifies an agent execution (including its children and tool helpers), a user save, or an independent background operation. A model/client cannot label its own write as trusted system activity. Internal `/.deep/` writes never enter the recorder.

For each externally modified working file, retain the content before the first external mutation and the latest successful content of that group. Further external saves update the group's end state. A successful agent mutation of that same file closes the external group; a later external mutation begins another. Failed writes do not become completed edits, same-content saves are no-ops, and a net-zero group produces no diff. Existing create/delete operations can be represented with standard `/dev/null` diff headers; this feature adds no file-management UI.

Keep the pending state under the existing runtime-owned conversation storage, outside the public diff directory. It is historical bookkeeping, not another authoritative editable document or a new database table. Only touched files need baselines; do not snapshot/read every workspace file at every turn. Do not retain every autosave step after consolidation.

Slice 2 binds server-assigned `mutation_source` on each runtime conversation service/namespace: execution-created services use `agent`, browser-authorized file services use `user`, and independently constructed maintenance services default to `independent_system`. All namespaces derived from that service retain the source, including native parent/child tools and helpers using privileged authorization origin. `current_mutation_source()` exposes that trusted source during provider writes/deletes; it is a scoped ContextVar, reset on failure, and is never read from model arguments, request metadata, or authorization origin. Slice 3 can consume the namespace's bound source around successful working-file mutations; internal `.deep` bookkeeping remains excluded by namespace. This attribution adds no pre-read, recorder, lock, or history yet.

Slice 3 records external mutations of the physical `scratchpad` namespace through `ConversationChanges`. Private durable state is `.deep/.changes/state.json`, outside `changes/<exchange-id>/`, and contains pending before/after groups, mutation intents, sealed intervals and path-only completed receipts. It uses the existing `.deep` quota and erasure owner. A mutation intent is persisted before the working write/delete; completion consolidates the successful result. A failed completion reports a fixed `ConversationFilesystemPartialSaveError` through the namespace, backend, port and browser save response. Recovery compares an unfinished intent with the actual file: before means no completed change, after means record it, and any other value is an explicit unresolved partial-mutation error. Recursive deletion records each removed text file. No local fallback or distributed transaction is claimed. Slice 4 extends the same journal to agent mutations: server-assigned `agent` intents close the latest open external group only after a successful content change. Failed/no-op agent mutations leave it open, and ordinary full replacements use the known external end state without reading the old output or adding a read-before-write requirement. Unfinished external or agent intents are recovered before a later mutation can overwrite their evidence. Persisted slice 3 intents without a source field remain external by default; no migration is needed. Parent, child, helper and concatenation writes retain their existing bound agent source regardless of authorization origin. No new lock or cross-replica guarantee is introduced.

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

Slice 3's `ConversationFilesystemService.publish_external_changes(exchange_id)` seals under the working namespace's existing process-local lock, then renders/publishes outside that lock. Later saves enter the new pending interval. A completed exchange returns its stored receipt; a partially published exchange reuses its sealed inputs and checks any existing artifact against the expected immutable bytes before acknowledging completion. Acknowledgment reloads state under the working lock so later pending writes survive. Separate provider instances sharing durable bytes can continue sequentially; simultaneous replicas retain the existing absence of a distributed CAS/merge guarantee.

Single-group artifact names percent-escape the complete relative source path, retaining simple names such as `report.md.diff`. Slice 4 filters net-zero groups before naming; multiple remaining groups receive chronological `.001.diff`, `.002.diff`, etc., with one padding width per source file (at least three digits, growing with that file's group count so ordinary listings remain numerically ordered beyond 999). Split diff headers carry `External change group <sequence>` as standard tab-separated header metadata alongside the exact source path. Naming examines all single/numbered candidates at seal time and hashes each source owner involved in a collision, including suffix-like source names. The sealed inputs and completed receipt keep those names stable on retry while later pending edits remain in their next interval. Names longer than 180 escaped characters use the first 100 characters, a reserved `!` separator, and the full SHA-256 source-path hash; literal `!` in ordinary source names is escaped, preventing generated-name collision chains. Headers retain the original absolute source path; nonprinting characters and literal quotes use JSON/C-style quoted headers. Diffs preserve LF line counts, CR/Unicode separator content and missing-final-newline markers. JSON parsing/serialization, diff generation and large text encoding/decoding are offloaded from the event loop. Published artifacts and private state consume `.deep` quota without evicting older history; existing scratchpad plus `.deep` erasure removes both.

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

Deep executor construction seals only the trusted `binding.runtime_context.exchange_id`, before compiling/invoking the parent; a missing user-exchange identity does not advance a boundary through a request/step fallback. Native child/model/tool steps do not construct another boundary. `ExternalChangesMiddleware` adds transient parent model context from the publication receipt, with at most 10 complete paths and 2,048 characters including the `External file changes:` label and any JSON-quoted truncation/directory metadata. No body or diff snippet enters this context. Static guidance is composed once into the shared parent/child system prompt; children receive that guidance without the parent's dynamic notification. Rebuilding a runtime for a HITL resume reuses the same exchange receipt and leaves subsequent saves pending.

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

## Context

See proposal.md for the changed scope. The branch contains uncommitted implementation work. Abandoned experiments have been removed. The developer authorized continuing the full sequence; tasks.md records the verified slices and remaining work.

Baseline code anchors used for the initial investigation:
- `libs/fred-core/fred_core/security/rebac/schema.fga`: document rights derive from folder rights; team profile visibility is not corpus access; admin/editor roles are distinct.
- `libs/fred-core/fred_core/documents/document_models.py`: corpus membership is currently a list of tag IDs.
- `libs/fred-core/fred_core/documents/tag_models.py` and knowledge-flow tag service: personal folders currently use user ownership; hierarchy uses path data.
- Knowledge-flow vector search resolves authorized folders and explicit documents separately, with a distinct conversation-attachment branch.
- Knowledge-flow task rows persist document targets and execution IDs. Ingestion cancellation is explicitly refused by the task API.
- Temporal already executes ingestion. Shared client provisioning precedes admission in the new local submission slice; an unconfirmed start can still retain a pending task indefinitely.

## Goals / Non-Goals

**Goals:** one authority per fact; team-scoped corpus authorization; explicit conflict rejection; native Temporal execution; visible errors; a migration whose unresolved cases are reviewed before mutation.

**Non-goals:** document-specific grants, shared documents, inherited grant exceptions, an authorization microservice, global FGA tuple scans as a fallback, an application-level rescue queue, ingestion cancellation for deletion, or strict vector visibility during cleanup. Retirement of the older knowledge-flow resource subsystem is explicitly approved. No extension to current control-plane prompts, agents, skills or conversation attachments.

## Decisions

### Confirmed policy and architectural direction

The delta spec is the authoritative record of approved business behavior. PostgreSQL owns corpus membership and lifecycle. OpenFGA owns team membership and permissions. Temporal owns execution of accepted long-running operations. Task records expose execution state; they are not another execution queue.

A corpus operation resolves the stored owning team, checks the existing appropriate team permission, and constrains all requested IDs to that team. It must not trust an arbitrary team ID supplied alongside a document ID. Team public-profile read permission is not sufficient for corpus access. Personal-team ownership uses the existing team model; no custom grant per document.

Use a common corpus authorization boundary within the existing backend, reusing the shared ReBAC client. Do not introduce a new service. Deduplicate within one request; cross-request permission caching is not proposed. Retain independent agent/tool/service admission checks unless code evidence proves they are redundant.

### Data and query design — implementation details to complete

Enforce one folder per corpus document and one owning team per folder. The precise relational migration and hierarchy representation remain to be designed after the writer/import inventory; do not select a new tree representation by assumption. Keep descriptive labels independent and potentially multiple.

For listing, counts and pagination, apply stored team/folder/lifecycle constraints in the database before paging. For vector search, authorize the team and narrow to selected folders/documents; retain the separate conversation-attachment path. Do not add PostgreSQL result rechecks to eliminate the accepted stale-vector window. Index scoping and index-migration details still require inspection.

### Target operation matrix

Counts below are logical corpus permission decisions per operation within one team, not measured HTTP call counts or whole-page totals. SDK, account, personal-team provisioning and service-boundary overhead must be accounted for separately in the final usage audit.

| User operation | Corpus decision | Inventory/work owner |
| --- | --- | --- |
| Browse folders/documents, counts, labels | Team read | SQL scoped query |
| Read/download a document | Resolve stored team, team read | Corpus/content service |
| Submit an ingestion batch | Team edit at admission | Existing task admission and Temporal |
| Update/move within a team | Team edit | SQL membership and lifecycle validation |
| Delete document/subtree | Team edit at admission | Conflict check, then Temporal |
| Agent corpus retrieval | Team read | Scoped vector/tabular search |
| Agent call without corpus access | No extra corpus decision | Existing agent/model/tool policies remain |

### Deletion design boundary

Reject if ingestion is active in the selected subtree; do not cancel it and do not schedule deletion to wait for it. Once deletion is accepted, reject new writes and hide the tree in navigation. Inventory comes from SQL, independent of UI pagination or FGA document listing. Temporal executes bounded cleanup; successful completion removes corpus data and temporary deletion state. A failed accepted deletion stays hidden with visible status; it resumes through Temporal rather than a second Fred executor.

The approved admission sequence is detailed below: API preflight before Temporal, then a final SQL conflict check before cleanup. Do not commit a deleting marker before Temporal submission or hold a SQL transaction during network I/O. Existing active-task coverage must include upload preparation, source sync and reprocessing; add no separate execution queue.

### Verified waiting behavior and approved deadline policy

The developer accepts longer waits when they do not stall unrelated work. Technical client deadlines are accepted; elapsed time MUST NOT be interpreted as business failure. Do not add a second application-level execution timer or fallback/retry loop. The final deadline values remain a configuration decision, not a hardcoded impatience threshold.

Read-only verification of the current local code:
- `scheduler_service.py:submit_documents` awaits the initial connection before shared admission. `ingestion_delivery.py:admit` exits its SQL transaction before `deliver` awaits Temporal. The RPC therefore does not retain that admission transaction or its row locks.
- `temporal_client_provider.py:get_client` uses an async connection call and an async lock during first connection only. Concurrent first users of that provider wait on the same connection; unrelated routes are not held by that lock. A cached client is returned before taking the lock.
- A pending HTTP request still consumes request/socket memory. Async waiting does not prove unlimited capacity or zero impact under saturation. No live saturation claim has been made.
- `temporal_scheduler.py:start_document_processing` currently caps the start RPC at ten seconds regardless of a larger configured value. Proposed change: honor the reviewed client configuration, without replacing it with a business timer.
- Multiple provider instances exist across controller/task wiring; they are not created for every upload, but process-wide uniqueness must not be claimed. Consolidation is a reuse question, not a reason to add connection supervision.
- `library_sync/service.py` creates a task before calling the scheduler; its existing error handler fails an unbound task. The statement that initial connection failure creates no tasks applies to direct shared admission, not to every upstream caller. Preserve these distinctions in tests and error contracts.

### Caller and writer inventory — evidence for the final plan

| Entry or writer | Current responsibility | Required target disposition |
| --- | --- | --- |
| TeamResourcesPage / DocumentWorkspace | Availability probe and folder/document subscriptions | Account for both UI requests; do not claim one RPC per screen |
| TagService | Folder list, rights projection, hierarchy, sharing, statistics | Team authorization for in-scope types; SQL inventory and no per-folder grants |
| MetadataService / ContentService | Lists, labels, counts, direct content, update/delete, metadata saves | Resolve stored ownership; team guard; no grant writes in progress saves |
| VectorSearchService | Team/folder/document selection and separate session attachments | Preserve selection narrowing and attachments; accept stale-vector window |
| TabularService | Candidate and per-UID access checks | Same team-scoped corpus policy; inspect all fallback branches |
| IngestionController / IngestionTaskService | Batch admission before shared input persistence; upload-only completes locally, processing submits to scheduler | Complete common folder lifecycle coverage; no payload redelivery queue |
| LibrarySyncService | Upsert/refile, input save, precreated task, submission | Participate in the same membership and active-work rules; preserve source-owned behavior until reviewed |
| Control-plane importer | Direct TagRow and DocumentMetadataRow insertion | Must migrate with storage contract; cannot bypass team/single-folder rules |
| Agent runtime / tool execution | Agent, team, model and tool admission | Retain separate policies; corpus tools converge at the corpus boundary |
| ResourceService and non-document TagType values | Older prompt/template/chat-context API | Retirement explicitly approved; remove routes, MCP mount, service/store wiring and obsolete non-document folder branches after deciding data handling |

The earlier static baseline audit counts checks (C), ListObjects (L), ListUsers (U), and tuple writes (W) at the original HEAD, not the current experimental code. Representative baseline costs: folder listing 9L when nonempty; UI probe up to 6L; document page 1L; sizes 0 authorization checks (a gap); metadata/content 1C; metadata persistence 4T accesses for T parent folders; a standard scheduled document with T=1 reaches 25 accesses across saves and worker read before batch-level overhead. Folder deletion was approximately 7+2F+4N for F visited folders and N returned single-folder documents, excluding UI refresh. Exact formulas and remaining routes must be reconciled against the final scoped plan; they are static counts, not measured end-to-end latency.

### Baseline usage audit: call counts by daily operation

Static counts at the original branch baseline, not latency measurements or validation of the in-progress replacement. C = Check, B = BatchCheck request, L = ListObjects, U = ListUsers, R = tuple Read page, W = tuple Write. A batch can contain several decisions. N = documents, F = folders, T = original folders per document; deletion formulas below assume T=1. UI refresh, account-status guards and personal-team provisioning are additional costs.

| User action / entry path | Baseline ReBAC work | Target disposition |
| --- | --- | --- |
| Team information, control-plane get_team_by_id | 1C + 1B + paginated R | Preserve independent team/role projection |
| TeamResourcesPage availability probe | Up to 6L | Stop using corpus enumeration as availability probing |
| DocumentWorkspace folder listing | 9L for a nonempty result | Bounded team read/edit decisions, SQL membership |
| Document page, browse_documents_in_tag | 1 global document L per page | Team read, SQL filtering before pagination |
| Folder sizes | No corpus authorization check | Add team authorization and validate requested folders |
| Corpus statistics | Up to 2L, insufficient stored-team scope | Team read and correctly scoped SQL aggregation |
| Metadata, original or preview artifact | 1C per request | Stored owner resolution, one team read decision |
| Labels, title, searchability mutation | 1C per document | One team edit decision per request |
| Filename rename | 1C + T L | Team edit and folder-scoped collision query |
| Label vocabulary / label search | 1 global document L | Team read and scoped SQL |
| Create root / child folder | 1C+1W / 1–2C+2W | Team edit; preserve the explicit source-root exception |
| UI remove one / N documents | 7 calls / 3+4N | Explicit deletion operation, no whole-folder item replacement |
| Direct API document delete | 1C + T U + T W | Team edit at admission, no per-document grant cleanup |
| Delete folder tree | 7+2F+4N for returned inventory | SQL inventory and Temporal execution; no FGA fan-out |
| Scheduled push ingestion, one document | 24T+1 across six metadata writes and worker read | One edit decision for the admitted HTTP batch; no worker-stage grant work |
| UI upload N files into one existing folder | 25N+3*ceil(N/8)+3 on the inspected normal path | Authorization bounded per HTTP batch; quota/admission stay explicit |
| Agent turn before corpus tools | 3C+1L | Preserve distinct control-plane/runtime admission |
| Each ToolExecution invocation | 1C in addition to backend checks | Preserve the tool admission boundary |
| Vector search in a team | 4L; +k C for k explicit document IDs | Team read and selected stored/index scope |
| Tabular team dataset/SQL scope | 5L | Team read and scoped candidates; separate conversation attachments |
| Source synchronization | Root authorization plus metadata-write fan-out | Keep its root grant at admission, remove document/stage grant maintenance |
| Document movement from UI | No action found | No new UI or API; existing source membership changes use ingestion admission |

Cold opening can issue both the availability probe and folder listing (15L), plus the document page and optional panels; different RTK Query arguments prevent deduplication. Mutation refreshes repeat relevant listing work. Do not present a fixed total per click or per agent answer without naming the cache state and tool calls. Separate account-status checks at service boundaries from corpus decisions.

### Unconfirmed scheduler start — accepted limitation

The local ingestion change propagates start errors, removes the submission payload queue and its redelivery loop, and opens the shared Temporal connection before task admission. After a start RPC error, a pending document reservation remains because execution may exist. If it does not, the existing status observer does not release it automatically. The developer explicitly accepted the concrete case of a connection breaking before the knowledge-flow backend receives Temporal’s start acknowledgement for a batch: return the client error, retain reservations, and require manual diagnosis/resolution if no workflow exists. Inability to retry through the UI until resolution is an accepted rare-case limitation. Do not add automatic redelivery/release or falsely report guaranteed non-execution.

## Risks / Trade-offs

- Documents can remain searchable while deletion is in progress: explicitly accepted. Cleanup completion must not be reported prematurely.
- Component failure reaches the UI: explicitly accepted. No alternate scheduler or cached authorization fallback.
- Admission races and workflow-start ambiguity: not silently solved; review the actual proposed sequence and limitation with the developer.
- Historical multiple/missing folders, sharing and personal ownership: inventory first; no arbitrary first-folder selection, automatic purge or inferred owner.
- Shared tag abstractions have other consumers: retain their behavior until scope is explicitly decided.
- Task/audit/Temporal history is distinct from deleted corpus data: its retention has not been settled by the requirement to remove temporary cleanup records.

## Migration Plan

This is the order of investigation, not an approved deployment procedure:
1. Inventory all readers/writers and historical data categories without mutation.
2. Present ambiguous data cases and proposed conversion to the developer.
3. Choose the relational change, writer cutover, index conversion and removal of obsolete corpus FGA tuples together; avoid routes consulting different membership authorities.
4. Specify upgrade prerequisites, mixed-version restrictions and rollback limits; obtain plan approval.
5. Implement and verify only the approved slices, including generated clients where contracts change.

For the already-local ingestion queue removal, the draft migration refuses a nonempty legacy queue and recreates an empty table on downgrade. This is not a completed production rollout and requires inclusion in the approved dependency plan.

## Disposition of local WIP — cleanup approved and implemented

| Existing work | Disposition |
| --- | --- |
| Candidate BatchCheck helper | Removed; no independent caller justified retaining the experiment |
| Global tuple Read plus candidate checks | Removed; shared engine and consumers restored to their original behavior |
| Per-document/per-folder grant maintenance | Remove for the corpus after coordinated migration |
| Cleanup journal, sweeper, late-grant compensation | Experiment removed, including migration and dedicated tests; Temporal remains the target execution owner |
| SQL admission/reference constraints | Experimental constraints removed; implement only the approved final membership/admission model |
| Ingestion fallback removal | Retain; explicit error and manual resolution accepted, complete validation |

## Planning gates

The developer approved the implementation order and starting with removal of abandoned WIP (task 2.1). This cleanup is authorized; unresolved contracts below still require explicit decisions before their implementation. The deletion preflight/final conflict rule and obsolete-resource retirement are now confirmed. Unconfirmed-start reservations and manual resolution are now explicitly accepted; no additional recovery is authorized. Resolve user-impacting questions one at a time; keep independent read-only discovery moving. Structural OpenSpec validation is not design approval.

### Prompt consumer audit: correction of the proposed scope question

The current `PromptsPage` uses control-plane team prompt APIs and categories, not knowledge-flow folder tags. Repository searches found no direct consumer of knowledge-flow resource CRUD in the current frontend, runtime, SDK or capability sources inspected, nor an `mcp-resources` catalog reference in the repository and sibling samples inspected. This does not prove absence of external clients or deployed data.

Knowledge-flow still registers `ResourceController` in `main.py:305` and mounts `mcp-resources` conditionally at `main.py:486`; checked configurations enable that mount. These remain exposed surfaces, not proven dead code. The runtime contract already records that the mount is absent from known catalogs.

Withdraw the earlier question asking whether current UI prompts should inherit document-folder rules: it conflated two models. Current control-plane prompts are outside the corpus change. The developer subsequently approved retirement of this older subsystem as part of the lot. Shared authorization types can be removed only after checking all remaining references and planning existing tuple disposition; current control-plane prompts remain outside this removal.

### Approved retirement: obsolete knowledge-flow resource subsystem

Remove together, once the consolidated implementation plan is approved:
- `features/resources/` (controller, service, structures, helpers and samples) and `core/stores/resources/` (interfaces, PostgreSQL store and ORM registration).
- `ResourceController` registration and the `mcp-resources` mount in knowledge-flow `main.py`.
- Resource store construction and configuration reporting in `application_context.py`; `storage.resource_store` and `mcp.resources_enabled` in config models, local configs, Helm values and regenerated schemas.
- Non-document `TagType` branches and `ResourceTagItemService`, now obsolete for the document-only folder service. Review stored non-document tag rows as well as `resource` rows before migration.
- `ResourcePermission` and FGA `resource` relations only after confirming no remaining consumers; remove associated dead tests/fixtures and regenerate API clients rather than editing generated code.

Known first-party runtime use of `ResourcePermission` is confined to this subsystem, tag item dispatch, the superseded cleanup experiment and the shared enum mapping. Runtime, capability and SDK source searches did not find direct old-resource callers. Public REST exposure remains an intentional breaking removal, not proof that external users never existed. Document the API removal in migration guidance.

Do not add a compatibility adapter or migrate old resource text into current control-plane prompts automatically. The developer confirmed that the migration must be explicit. Use the recommended stop-and-review path for existing legacy data; no blanket destructive deletion was authorized. No database contents have been inspected or changed for this retirement.

The empty `mcp-template` mount was verified and removed with legacy resources. The developer separately confirmed the old direct report writer is unused and approved its retirement; preserve generic content serving and existing stored reports.

Approved implementation dependency order: resolve legacy data handling; retire obsolete resource code and adjust config/contracts; simplify remaining corpus membership and team authorization; implement reviewed deletion admission/execution; run migration and end-to-end validation. Keep local experimental migrations from becoming accidental prerequisites of the final sequence.

### Legacy-resource migration procedure to include in the operator guide

1. **Before deployment:** inventory counts and identifiers for the `resource` table and non-document `tag` rows, plus their associated FGA tuples. Identify any known external client using the removed REST/MCP surface. This is read-only; do not infer that empty first-party usage means empty deployed storage.
2. **Decision gate:** if legacy data remains, stop the destructive migration. The operator must arrange a backup/export and obtain an explicit decision about those data. Do not automatically convert them into control-plane prompts or delete them to make upgrade succeed. A backup alone is not authorization to discard data.
3. **Drain and stop writers:** finish or explicitly resolve existing ingestion submissions before dropping the old submission queue. Stop the old knowledge-flow writers before schema/code cutover; no mixed-version operation against removed resource tables. Use the deployment's ordinary maintenance procedure rather than adding a compatibility runtime.
4. **Apply the reviewed migration:** retire obsolete rows only under the explicit data decision, remove the old resource storage, and clean obsolete authorization tuples for the retired object types. The exact commands and order must be tested before the final guide is approved. Do not change unrelated team, agent or control-plane prompt tuples.
5. **Deploy matching code/configuration:** remove old resource store/MCP configuration keys from local and Helm configuration, regenerate schemas and API clients, and deploy the code that no longer registers the removed routes or store.
6. **Verify:** current control-plane prompts still list/edit normally; corpus browsing and authorized access work; old resource REST/MCP surfaces are gone; no runtime imports or configuration references remain; the schema has the expected single migration head. Verify the document model migration separately rather than assuming resource retirement proves corpus integrity.
7. **Rollback:** specify the last reversible checkpoint before data/tuple removal. Recreating an empty table does not restore removed records, FGA tuples or client behavior. Any restoration must use the verified backup and matching code/schema; do not advertise automatic rollback after destructive cleanup.

The operator guide must list concrete commands, expected results and stop conditions after the final migration sequence is designed. No cleanup service, rescue queue, automatic repair or backwards-compatible adapter is part of this procedure.

## Implementation sequence — execution approved, unresolved details remain review gates

### Delivery order and scope

1. **Retire the older resource subsystem.** Remove the approved old REST/MCP/service/store/config surface and non-document folder dispatch. Preserve control-plane prompts and existing report documents; the unused direct report writer is now approved for retirement. Verify the empty `mcp-template` mount before including its removal; do not bundle unrelated MCP removals.
2. **Make corpus membership unambiguous.** Proposed target: one non-null folder identifier per corpus document and an explicit owning team on each folder, including personal teams. Keep the existing path-based folder organization unless evidence requires a separate redesign; do not introduce a second tree index or hierarchy service. Preserve UIDs, source-library/source-key identity and descriptive labels. Database constraints and all writers must agree; JSON copies and index metadata must be derived from that authority, never independently editable memberships. The final public field names and generated contract diff belong in the approval package.
3. **Converge corpus authorization.** Resolve stored team once per request, enforce the existing team capability, then run SQL-scoped listing/count/mutation or selected corpus retrieval. A single common backend policy boundary replaces per-document/folder checks and owner discovery. Preserve account restrictions, personal-team identity and agent/service admission. For a page needing both read and edit button state, use one existing batch of team decisions rather than claiming one logical decision for the entire page. No cross-request permission cache or new service.
4. **Implement the agreed simple lifecycle.** Admission rejects conflicts rather than canceling, waiting or compensating. Block new admissions into a deleting subtree through the same transactional business boundary. Temporal owns accepted cleanup; retain existing metadata until required external deletion succeeds, then remove metadata/labels and adjust quota through the existing transaction. An already-absent external object is success on replay; the workflow does not need an application-side cleanup queue. No strict read exclusion for stale vector hits.
5. **Migrate and verify before publication.** Inventory, stop old writers, apply approved data/schema/FGA/index changes and deploy matching code. No mixed membership authorities between routes. The approved data gate stops on ambiguous or still-used legacy data. Verify both correctness and authorization-call budgets, not only throughput.

### Corpus API and task contracts to review

- One-document and many-document removal must use an explicit deletion operation. The current UI's whole-folder `item_ids` replacement is not the target bulk-delete contract. Choose existing route extension where possible; do not add a parallel API family.
- Folder sharing endpoints and UI controls disappear for the retired folder authorization model. Same-team moves validate membership/lifecycle and do not write FGA relations.
- Async deletion uses existing task listing/progress/error presentation; select the event shape after checking existing erasure semantics, not by reusing an unrelated event name. Regenerate OpenAPI and frontend clients for every contract change.
- Worker ingestion progress updates content/processing state without repeating the initiating user's permission check or restoring a stale folder assignment. Accepted role changes do not stop the operation.
- Initial upload/input preparation must participate in the definition of active ingestion. Existing tasks are created later on some paths; querying only running Temporal tasks would miss that interval. Design one shared admission boundary before implementing the deletion conflict check.

### Deletion admission: approved preflight and final conflict check

The developer rejected making the first busy-folder decision only after launching Temporal. Confirmed order: knowledge-flow backend resolves the stored team, checks permission and existing active ingestion, and refuses an occupied subtree before requesting any Temporal workflow. Do not reinterpret this as authorization to commit a deleting marker before Temporal submission or hold a SQL transaction over network I/O.

The developer also approved the concurrent-arrival case after preflight and before deletion claims the subtree. Accepted handling: Temporal's first cleanup activity performs a short SQL check-and-claim against the same ingestion admission boundary. If a new ingestion won that interval, the deletion task reports a conflict and performs no deletion; no cancellation, waiting, compensation or rescue queue. Otherwise it marks the tree deleting and subsequent ingestion is refused. This second check is an approved business conflict rule. Immediate refusal for ingestion already present at the API preflight remains mandatory.

For the final UI contract, distinguish a submitted request from a successfully claimed deletion. The tree is hidden when the deleting state is committed; a conflicting task must not hide or partially delete it. Include this precise timing in the final plan approval rather than promising that an HTTP acknowledgement proves the SQL claim has completed.

### Additional verified implementation boundaries

The UI upload path saves input and metadata before creating ingestion tasks, while library synchronization can precreate its task. Therefore checking current task rows alone is not sufficient to cover every active upload: the accepted admission boundary must precede conflicting storage writes in every ingestion entry path. This is a normal business-state correction, not a separate recovery queue.

The existing `ErasureTaskEvent` is specifically conversation erasure (governance reasons and repeated erasure attempts). Do not reuse that semantics or its scheduler for corpus deletion just because the names sound similar. Reuse generic task progress infrastructure; propose the minimal corpus event contract in the final API diff.

### Call-budget acceptance targets

| Operation in one team | Target corpus FGA work | Additional work kept explicit |
| --- | --- | --- |
| Folder page with button permissions | Bounded team read/edit decisions, no per-folder checks | Existing team/identity guards; SQL paging/count |
| Document page, sizes, labels, statistics | One team read decision per request | Validate every supplied ID belongs to the scope |
| Download/update one document | One corresponding team decision per request | Resolve stored folder/team first |
| Submit N documents in one HTTP batch | One team edit decision at admission | Quota and state are SQL business checks; no per-document grant writes |
| Ingestion worker stages | Zero repeated initiator corpus permission calls | Existing machine authentication is not removed |
| Delete N documents or a tree | One team edit decision at admission | No ReBAC calls proportional to document/folder count during cleanup |
| Same-team move | One team edit decision | SQL destination/state validation; zero FGA tuple writes |
| One corpus retrieval tool call | Team read decision at corpus service boundary | Agent/tool/model admission elsewhere remains accounted separately |

These are proposed test budgets. Actual SDK requests may include explicit account/personal-team provisioning checks; record those separately rather than hiding them. Keep unrelated FGA enumeration consumers unchanged until independently scoped.

### WIP disposition before implementation resumes

Do not stack the target on top of the obsolete experiment. Replace the proposed cleanup-journal migration and remove its table/model/worker/sweeper/late-grant paths. Re-parent the queue-removal migration to the reviewed final linear sequence; it must not force deployment of the abandoned journal. Reassess candidate BatchCheck and the global Read+Check adapter: preserve only independently justified functionality and restore unrelated consumers' original behavior where the experiment changed it unnecessarily. Retain passing tests only when they cover the accepted behavior; replace tests that enforce shared-document preservation or rejected compensation protocols. Do not touch unrelated local secrets.

### Validation and publication gates

- Unit/service tests prove stored-team authorization, member/editor/personal behavior, no sharing, same-team-only moves and correct counts.
- Tests at 999/1,000/1,001/5,000 documents prove complete inventory and invariant corpus FGA call budgets.
- Real PostgreSQL tests prove single-folder constraints, admission conflict behavior, quotas and successful cleanup leaving no corpus/temporary deletion residue.
- Temporal integration tests prove accepted deletion resumes on worker restart and replay tolerates absent artifacts; test only the failure contracts agreed with the developer.
- UI/API tests cover explicit component errors, pending/active/failed deletion and rejection while ingestion is active. Keep vector stale-hit behavior permitted until cleanup completes.
- Test migration on representative valid data and refusal on multi-folder, missing-folder, ambiguous ownership, remaining old resources and nonempty submission queue; exercise documented rollback boundaries.
- Root code-quality, relevant full suites, independent correctness/performance/contract review, regenerated clients/schemas, migration-check and strict OpenSpec validation must pass before draft PR publication and archive. No load campaign is implied by static call-budget checks.

### Confirmed metadata storage boundary

The developer approved retaining the shared PostgreSQL metadata table for corpus documents and conversation attachment datasets. The final schema must explicitly distinguish these kinds, require one folder for corpus rows and no folder for attachment rows, and reject ambiguous historical rows during migration. No attachment file/vector relocation is implied. The conversation association remains in control-plane `session_attachments` (session_id, document_uid); preserve those identities and verify the full attachment flow separately.

### Concrete metadata storage contract under implementation

- `metadata.folder_id` is the single relational corpus membership, with a foreign key to `tag.tag_id`.
- `metadata.kind` distinguishes corpus (exactly one non-null folder) from attachment (no folder). A database check enforces this distinction.
- The existing public `tags.tag_ids` remains a singleton/empty serialization shape, reconstructed from SQL. It is removed from stored JSON, as is kind; worker progress does not overwrite membership.
- Source-library/source-key uniqueness, document identifiers and label rows are preserved. Snapshot export includes kind; import refuses invalid cardinality or disagreement with any embedded old folder list. Tagless old snapshot rows require explicit attachment classification rather than an inferred owner or destination.
- Migration b2845a001004 refuses multiple/missing/dangling folders and SQL/JSON disagreement before schema changes. A historical folderless CSV attachment is recognized only by matching fast-ingest source fields, uploader, tabular artifact dataset UID and absent source-sync identity. A source named fast_ingest with one valid folder is still corpus. Operators must verify conversation association separately before the coordinated cutover; source names alone do not prove that association.
- This migration does not normalize folder team ownership, remove FGA tuples or migrate index scope. Those remaining pieces must be completed before deployment. PostgreSQL is the deployment target; SQLite fixtures are classification tests, not a supported migration path for deployed data.

### Accepted stop before Temporal submission

Record ingestion admission before shared corpus writes. If the knowledge-flow process stops before calling Temporal, retained pending admission may require manual diagnosis/resolution; the developer explicitly accepts this rare-case limit. Ordinary preparation exceptions report task failure. This does not authorize recovery loops, expiry heuristics, automatic cancellation or redelivery.

### Historical membership writer: reports

`ReportsService.write_report` receives a folder ID but currently persists only display tags in PostgreSQL and writes the folder association into FGA. The developer subsequently approved removing this unused writer instead of adapting it. Historical report rows without SQL folder membership are migration stop cases requiring explicit reconciliation with their FGA parent; do not classify them as attachments or choose a folder automatically.

### Approved source authorization exception

Human corpus access is exclusively team-scoped. The developer explicitly confirmed retaining the source account’s single editor grant on its synchronization root. Resolve that root from persisted folder hierarchy and check its grant at operation admission, not at each document or worker stage. The source must not acquire team-editor access. The service_agent role alone grants no corpus read access. Machine reads require an explicit viewer or editor grant on the root; source writes require its editor grant. FGA migration must preserve these source grants while removing obsolete human folder and document relations.

### Movement scope clarified after UI inspection

No document-move action was found in the current corpus UI: DocumentWorkspace drag-and-drop opens the upload drawer for operating-system files, and useDocumentCommands exposes removal and rename, not document relocation. Do not add a move UI, endpoint or orchestration for this change. LibrarySyncService._refile already changes a source document's folder; apply the accepted active-ingestion refusal through the existing exclusive document-ingestion admission, moved before source writes. A source write must acquire that admission before changing membership or content; do not introduce a separate move reservation, queue or coordination mechanism. The generic tag item replacement endpoint also changes membership and must be narrowed during the already-planned removal of the old multi-folder contract. Folder renaming is distinct from changing a document's folder ID.

### Report writer retirement explicitly approved

The legacy /mcp/reports/write endpoint directly writes corpus artifacts and metadata outside normal ingestion. Repository and sibling fred-samples searches found its controller/service/mount/tests and generated client, but no first-party invocation. External clients remain unknown. The developer confirmed it is unused and explicitly requested deletion. Remove its route, MCP mount, service, dedicated renderer/helper/types and configuration, regenerate clients/schemas, and preserve existing stored documents. No report-specific concurrency mechanism is needed. This is distinct from current control-plane prompts and conversation attachments.

### Verified owner conversion approved

During writer shutdown, read the explicit owner tuples for each persisted folder using the existing paginated exact-object Read API. Require exactly one user or team owner and agreement with both SQL and JSON owner fields. Convert verified user ownership through the existing personal_team_id helper; keep team ownership unchanged. Missing, multiple or inconsistent owners stop the migration before any SQL conversion. Preserve all FGA tuples at this step; their coordinated removal and source-grant preservation remain a separate cutover step. Do not infer an owner from names, uploaders, accessible-document listings or a personal-team prefix alone.

### Evaluation boundary clarified

The developer confirmed removing the general service_agent read exception in knowledge-flow: every service account must have explicit corpus rights. Keep the evaluation application and its configuration outside this pass. Operators must assign each consuming account the required root viewer/editor grants before reopening corpus access. The same root policy applies to folder listing and direct reads; filter authorized roots before pagination, with one decision per root per request and no document inventory from ReBAC. Source synchronization still requires the exact account’s editor grant at admission.

Folder namespace integrity is enforced by a unique SQL index on owning team and full path, treating NULL and empty root paths identically. Migration refuses existing collisions before changes. The runtime resolves paths through that index; it does not scan for legacy aliases or recover conflicting creates. Quota and ingestion-task attribution use canonical SQL owners; unavailable services never cause a folder to be reclassified as personal.

### Unscoped read retirement

The developer requests checking usage before adapting old global reads, deleting unused paths instead of introducing a new contract. The metadata search REST endpoint has no active caller in Fred/fred-samples: its only UI reference was a fallback in useDocumentCommands, while the sole production caller always supplies its folder refresher. Remove the route and fallback. The developer also confirmed the selectable MCP Filesystem /corpus path is unused and authorized its removal. Remove its implementation and the now-unreferenced global metadata service method; retain workspace /teams operations and current corpus navigation/read tools. Regenerate clients and document the breaking removals. No replacement unscoped or explicit-scope endpoint is required.

### Label scope decision

The developer confirmed keeping active label features while narrowing their scope: UI vocabulary belongs to the displayed team, and agent label resolution follows the conversation team plus selected folders/documents. Propagate existing runtime scope at the adapter boundary, without asking the model to choose identity or team. Selections are additive: selected folder A plus a selected document in folder B includes both, always intersected with authorized folders in the conversation team. Empty selections retain the whole authorized team scope. Apply these constraints in SQL before totals and pagination. Retire unused label compatibility routes only after caller inventory; do not add a global fallback when scope is missing.

### Accepted partial index updates and deferred follow-up

The developer accepted explicit failure after a document rename or retrievability mutation commits to PostgreSQL but its vector-index update fails. Knowledge-flow returns an error identifying the saved metadata and failed index update; it performs no rollback, partial cleanup, retry, queueing or reconciliation. An index client can fail after changing some chunks, so operators must verify the actual index state. Repeating a rename to the already-saved name is a no-op, not a repair guarantee.

Keep the following as possible later work, not requirements of this change: document the operator verification/repair procedure for partial index updates; reassess native index update capabilities if observed incidents justify it. This follow-up also needs to consider the already-accepted manual resolution of ambiguous Temporal starts and crashes between ingestion reservation and submission. Any automated recovery remains subject to a separate concrete developer review; recording these limits does not authorize implementation.

### Approved batch admission conflict behavior

If any document in a requested ingestion batch is already active, reject the entire new batch before shared content or metadata writes. The existing ingestion continues unchanged. Admission remains one SQL transaction; do not accept a subset, cancel existing work or coordinate partial admission. Local upload reception and metadata extraction may precede admission, but do not write the shared corpus at that stage.

The developer confirmed retaining upload-only mode and the current frontend request splitting (at most eight files, grouped by destination and unique leaf names). Atomic conflict refusal applies to each backend request; another request from the same UI selection may proceed. Upload-only must use the common admission boundary while preserving its no-processing behavior. Do not add cross-request coordination or redesign the frontend/public API in this change. Reconsider those surfaces in a separate follow-up after this PR; the present priority is a sound shared backend foundation.


### Targeted retrieval and source admission convergence

Vector comparison authorizes the persisted folders of all requested documents together with explicitly selected folders, then performs the additive targeted searches directly. It does not inherit the general search's default personal-team scope. Missing targets are explicit errors; conversation attachments remain outside this corpus comparison. Ordered chunks and visual-artifact links use stored-folder read authorization; reranking preserves its existing editor requirement with a grouped batch check.

Result decoration is separate from authorization: one bulk folder lookup supplies names and paths after ranking/limiting. It does not recheck document existence, remove stale excerpts or issue additional ReBAC checks. Raw-file/Range streaming resolves authorized metadata once and reuses it for response headers and the stream.

Source synchronization now calls the same `admit_documents` / `deliver_documents` pair as UI uploads. Admission precedes shared content, membership writes and removal of previous vectors. Ordinary preparation failure settles its reserved task; an unconfirmed Temporal submission retains the reservation. This convergence does not complete the remaining transactional folder lifecycle or deletion workflow.


The managed runtime constructs agent settings and request context from the same validated team; no separate team-selection mechanism is needed. MCP argument injection must also overwrite a model-supplied `team_id` when that resolved scope is personal (`None` on the existing wire contract), rather than only forcing shared-team IDs. The existing document/folder selection rules are unchanged.

Deletion cancellation decision: the developer explicitly confirmed that deletion submitted to Temporal cannot be cancelled through the UI or API. It completes or reports failure; Fred does not restore already deleted artifacts.

The concrete SQL boundary uses the existing root-folder rows as short transaction locks, ordered by ID. Ingestion records its destination in `kf_task_run.folder_id` before shared writes; the destination has no foreign key because task history outlives corpus data. Source refiling also locks and checks the document's original stored folder. A changed tree or membership after waiting is explicitly refused, without automatic retry. Deletion checks active tasks (including preparations without document metadata), then records its task ID on the subtree rows in the same transaction. Temporal and content/index calls occur outside these transactions. Existing deployments must finish or manually resolve active ingestion before applying this schema; no destination is inferred for an incomplete upload.

Approved atomic rename: the frontend sends one request for the selected folder. The backend renames that folder and rewrites descendant paths in one SQL transaction, using the existing tree admission lock. No retry or compensation is added. A rename must not replace document membership from the UI snapshot. Keep intersecting folder/action changes visible for comparison with Maxime's forthcoming PR; assess actual conflicts after this change is complete rather than adding compatibility mechanisms speculatively.

Global reindexing scope decision: the developer will revisit and may remove that administrative feature separately. Do not add lifecycle coordination, a maintenance admission gate or a new operator quiet-period requirement for global reindexing in this change. This exclusion is not evidence that concurrent reindexing/deletion is safe. Keep ordinary user/source ingestion and reprocessing within the agreed admission scope.

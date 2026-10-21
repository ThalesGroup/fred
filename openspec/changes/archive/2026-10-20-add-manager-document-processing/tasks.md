## 1. Confirmed contract and persistence

- [x] 1.1 Obtain developer confirmation of this proposal/design/specification; record the confirmed scope in this task response or #3180 before implementation. Confirmed in this task on 2026-10-19: "oui je valide".
- [x] 1.2 Reuse PipelineDefinition/FileToProcess and ProcessPush unchanged; export the existing Python schema and shared profile submission policy, and verify Rust payload decoding with the current worker models and absence of credentials/content. Internal manager persistence callbacks remain separately typed.
- [x] 1.3 Extend the baseline schema with processing attempts, active/successor uniqueness, stage fences and result references; verify transaction rollback, conflicting starts and immutable document/space/original bindings with disposable PostgreSQL tests.
- [x] 1.4 Extend upload admission/idempotency with mode/profile and atomic processing intent; verify lost responses, replay with changed choices, upload-only behavior and original quota invariants.

## 2. Manager authority and durable dispatch

- [x] 2.1 Add document processing start/retry/status/history routes and generated response models; verify current admission, personal/organization/team/project roles, cross-organization denial, concurrent retries and no second original charge.
- [x] 2.2 Add strict workload authentication and operation-bound descriptor/original/stage/progress/publication routes; verify human/wrong workload rejection, actor revocation, CGU changes, corrupted original detection and safe failure persistence after revocation.
- [x] 2.3 Add bounded delivery claims, stable Temporal start identities, persisted acknowledgments and reconnect/reconciliation in the manager worker independently of lifecycle enablement; verify real Temporal outage, accepted-start response loss, restarts, completed duplicates, missing consumer and unavailable old history.
- [x] 2.4 Implement monotonic stage claims and conditional result commits; verify duplicate callbacks, obsolete/expired fences, terminal immutability, conflicting manifests and lost publication acknowledgments.

## 3. Knowledge Flow worker execution and outputs

- [x] 3.1 Keep the existing worker workflow/activity registrations and signatures; select the manager persistence adapter and freeze policy from the shared KF submission configuration; verify a real Rust-dispatched request is decoded and routed without the KF HTTP API or legacy metadata/tag/task creation.
- [x] 3.2 Adapt extraction to authenticated manager original streaming and existing subprocess supervision; verify size/digest, worker restart, local output limits and fast/medium/rich queue selection with representative supported inputs.
- [x] 3.3 Reuse the existing Office-to-PDF converter inside supervised worker extraction and include native renders in the fenced manifest; verify supported Word/PowerPoint/ODT formats, conversion timeout/failure, worker image dependencies and original preservation.
- [x] 3.4 Inject manager-specific persistence into the existing output pipeline, including separate vector/tabular stores, generation-scoped IDs and preserved scope metadata; verify actual chunks/embeddings or tabular output, profile policy and existing Python-owned ingestion regressions.
- [x] 3.5 Add durable derived artifact manifests and publication validation; verify a minimal text/PDF vertical produces inspectable output and correct counts, while incomplete files/index writes cannot publish success.
- [x] 3.6 Add bounded derived-data capacity/backpressure and cleanup of abandoned generations; verify late writes, SQL unavailability, partial vector/table output, repeated cleanup and preservation of originals/published generations.
- [x] 3.7 Prove isolation from existing KF search/listing/preview/expiry/repair and original cleanup with populated legacy and manager stores; verify shared-store misconfiguration is rejected.

## 4. Existing UI and API consumers

- [x] 4.1 Regenerate manager OpenAPI/RTK clients and restore existing upload mode/profile controls; verify generated type consistency, multipart idempotency choice propagation and ordinary upload-only regressions.
- [x] 4.2 Extend the existing import and Resources bindings to persisted processing summaries with bounded refresh; verify navigation/reload, missed updates, account/organization changes, terminal order and active processing after upload acknowledgment.
- [x] 4.3 Wire existing process/retry and preview controls to manager; verify retry needs no local file, unauthorized controls agree with backend decisions, original download survives failure and preview uses safe authorized output loading. Verify PDF range loading and both Office File/Raw modes with KF HTTP stopped, including an exhausted render failure and retry.

## 5. Configuration and full-path verification

- [x] 5.1 Add typed manager/KF configuration, workload identity provisioning, isolated derived stores and deployment values/schemas; verify factory/chart validation, disabled processing, strict token audience/client checks, invalid topology and bounded limits. Update the branch migration note with activation, reset, drain and rollback procedures.
- [x] 5.2 Run the real manager -> Temporal -> KF worker -> manager journey with KF HTTP stopped: upload/download hash, text/PDF chunks/embeddings, tabular output and fast/medium/rich routing; verify persisted preview/state after browser/API/worker restarts using disposable infrastructure.
- [x] 5.3 Exercise transient object/model/index/manager failures, non-retryable input, missing workers, queue/execution deadlines, late activity writes, concurrent starts and revocation during execution/publication; verify each original survives and no duplicate/stale result becomes published.
- [x] 5.4 Measure exact FGA requests/filters/pages/tuple operations and SQL lock durations at 1/100 documents, membership-page boundaries and concurrent admission/publication/revocation; verify design budgets and record fixture size/concurrency without inferring production scalability.
- [x] 5.5 Run manager `make test`, `make test-integration`, `make code-quality`, affected KF/frontend tests and repository-root `make code-quality`; inspect raw Python typing diagnostics where a baseline applies and fix touched regressions. Honor any requested manual validation before broad tests.

## 6. Review and local close-out

- [x] 6.1 Apply `audit-branch` to the actual PR target and obtain independent read-only implementation review, including affected contracts, async progress, authorization/performance and UI; record base/head, coverage and exclusions in the task response or PR, fix actionable findings with regression tests and obtain correction review.
- [x] 6.2 After review, update arc42 journeys, document/security/operations/quality chapters and A1/A2/A3 references for implemented behavior; mark invariant tests `// Proves: I<n>`, regenerate derived blocks and pass `make -C docs/architecture check`.
- [x] 6.3 Reconcile these artifacts with implementation and exact verification evidence, resolve any overlap with active document-storage deltas, validate/sync/archive the change and create one clean local feature commit for #3180. Do not push without explicit developer agreement.

## Verification and review evidence

The implementation preserves `ProcessPush`, `PipelineDefinition`, `FileToProcess`,
workflow definitions, activity signatures and `_build_worker` registrations. The
existing Python models decode the exported Rust submissions. Internal manager
persistence adapters provide authority, storage and publication; they do not add
a second extraction/chunking algorithm. Manager and KF configuration schemas,
OpenAPI/RTK clients, Helm values/schema and arc42 derived blocks are regenerated.

- Manager offline verification: 45 unit tests and 10 OpenAPI tests pass.
  Full disposable integration reports 103 passing tests (102 exercised cases;
  the separately opt-in journey returns early in this command). The journey also
  passes separately with `CONTROL_PLANE_IT_PROCESSING=1` and
  `INTEGRATION_POSTGRES_IMAGE=pgvector/pgvector:pg15` (395.28 seconds).
- KF: 365 scheduler/adapter/pipeline/Excel/tabular tests pass; the subsequent
  adapter boundary additions pass 36 focused tests. Faults cover original
  size/digest, lost object acknowledgment, manager HTTP recovery, partial vector
  writes, stale/late generations, unavailable cleanup authority/acknowledgment,
  resource exhaustion, converter cleanup and stable failure classification.
  Raw basedpyright reports zero errors and seven existing warnings (no baseline
  suppression used for that inspection).
- Frontend: 376 tests in 51 affected files pass, including upload choices,
  processing rehydration, account isolation, retry keys after response loss,
  generated bindings, bounded authenticated preview loading and inert diagrams.
- The real journey uses disposable PostgreSQL/pgvector, OpenFGA, SeaweedFS and
  Temporal with existing KF workers, local identity/model protocol fixtures and
  no KF HTTP server. Fast/medium/rich, text, PDF, CSV, DOCX, PPTX, DOC, ODT, PPT
  and XLSX produce durable outputs; raw/native preview and original byte equality
  are checked. Model/render exhaustion preserves the original and explicit retry
  succeeds. An actual worker OS-process restart and two populated vector
  collections with isolated delete pass. Manager dispatcher restart/lost SQL ACK
  resolve the same execution. No-consumer, unavailable Temporal and acknowledged
  missing history retain bounded safe outcomes. Unsupported input completes the
  existing workflow without publishing success; clearing its durable ACK and
  ticking the Rust dispatcher recovers the same closed run as failed. An expired
  no-ACK attempt is rejected before dispatch and real Temporal Describe returns
  NotFound, proving no execution was created. This does not simulate physical
  Temporal history deletion.
- New pool/auth/Processing replay checks terminal publication after service-state
  reconstruction, manifest conflict and late failure. Frontend rehydration tests
  and server-state reconstruction are composed restart proofs; no manual browser
  reload/visual campaign or complete manager OS-process restart was run for this
  feature. The storage-isolation fixture uses real legacy listing/preview/expiry/
  clear methods with simulated buckets; vector isolation uses real pgvector.
  These complement review of unchanged legacy catalog/repair consumers and the
  real journey's guards against any legacy metadata/content/tag factory access.
- Configuration tests reject shared vector namespaces for all four supported
  persistent adapters and the actual legacy Minio document/object/filesystem
  bucket names. Original and derived manager buckets are separately validated.
  Helm rendering/schema validation pass. Reset checks pass: 28 unit tests and
  the real disposable PGVector/OpenFGA/S3/OpenSearch reset-storage contract.
  No live k3d reset or production rollout was performed. The local companion
  deployment-factory checkout lacks its documented reset wrapper; propagation
  through that external wrapper is not claimed as tested.
- FGA request/page/tuple counts and sampled SQL lock spans, with fixture size and
  concurrency, are recorded in arc42 chapter 9. Admission compares 1/100 document
  rows and concurrency 1/8 at page size one; final publication and queued
  revocation/publication cover the guarded boundary. Sampling is approximate,
  and none of these fixtures establish production scalability.

Author review used the actual PR #3170 target `swift` (merge base
`c32c3069db80c4590af730b93ff4b9c2eb04c2d5`) and implementation baseline HEAD
`b50e5217add1abec3a25ac36ef3b8a39edf923ad`, plus this uncommitted feature diff.
Independent read-only reviewers covered manager/KF contracts, authority,
dispatch/fencing, async state, preview/UI safety, reset/deployment integration and
final arc42/product/migration documentation. Their actionable findings were fixed
with focused regressions and independently rereviewed: uncertain dispatch and
worker startup/drain, output/scratch limits, failure propagation, safe preview
loading, retry-key recovery, UI authority bindings, namespace isolation and reset
upgrade semantics. Final documentation corrections distinguish Preparation
checks from later fencing and periodic storage monitoring from an eviction
backstop. No actionable findings remain in those bounded reviews. Earlier
organization/governance internals and the entire existing 360-file branch were
not independently re-audited; this is not a claim of full PR readiness.

Only this change modifies the existing document UI requirement. The active
`one-check-per-request` and `harden-manager-edges` document-storage deltas affect
other requirements and are preserved. The current main specification keeps their
existing authoritative requirements while adding this processing behavior.

Final checks on 2026-10-20: manager `make test`, `make test-integration` and
`make code-quality`, repository-root `make code-quality`, and
`make -C docs/architecture check` all pass. The final real Temporal journey
passes as described above. OpenSpec strict validation passes for this change and
`document-storage`; all seven delta blocks match the synced main specification.
The two remaining documentation findings and the bucket-name correction were
independently rechecked and closed. This step is committed locally for #3180;
no push, merge, deployment or live data reset is included.

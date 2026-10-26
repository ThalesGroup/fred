## 1. Storage contract and configuration

- [x] 1.1 Confirm this proposal's scope/acceptance and identify the tracking issue by extending an appropriate existing issue or creating one only if needed; record the confirmed issue and scope here before source changes. Developer confirmed the full proposal on 2026-10-19; dedicated tracking is #3172 after checking existing manager/document issues.
- [x] 1.2 Add typed S3, transfer, quota and cleanup configuration through the existing control-plane deployment contract; verify schema/default validation, secret redaction, bounded temp-volume configuration and preservation of the current deployment/Home journey.
- [x] 1.3 Add the pinned S3 client and a disposable SeaweedFS 4.29 contract fixture; verify conditional immutable writes, length/checksum handling, read-back verification, bounded retries/timeouts, safe downloads and Delete/List pagination without using live buckets.

## 2. Durable upload and lifecycle coordination

- [x] 2.1 Add a new migration extending published document metadata and introducing the upload journal with indexes/constraints; verify fresh migration, incompatible metadata-only preflight, immutable placement, canonical name uniqueness and actor/request-key uniqueness without editing applied migrations.
- [x] 2.2 Implement bounded single-file parsing/spooling, authoritative quota reservation, S3 write/verification and guarded publication; verify the existing role/admission matrix, token expiry/revocation before publication, duplicate keys/names, malformed multipart, actual-size limits and concurrent shared-team quotas.
- [x] 2.3 Implement receipts, terminal outcomes, acknowledgment/retry lineage and idempotent replay; verify lost acknowledgments, receipt ownership/current authorization, stable successful IDs, concurrent retries and dismissed/superseded failures staying resolved after browser state loss.
- [x] 2.4 Implement bounded autonomous expiration/cleanup and inventory reconciliation; verify crashes, multi-replica claims, late Put after Delete, SQL outage, provider outage, cleanup backlog admission and preservation of every ready object, with no Temporal/ingestion dependency.
- [x] 2.5 Integrate pending uploads into folder subtree and space lifecycle checks; verify both race orderings against reservation/publication/abandonment and prove no target resurrection or deletion of a stored original.

## 3. Read contracts and existing UI

- [x] 3.1 Implement combined directory pages, storage summaries, ready metadata/detail and original streaming downloads; verify mixed sorting/filtering/totals, pagination bounds, shared quota isolation, denied/foreign targets, safe headers and missing/truncated content errors.
- [x] 3.2 Publish the manager OpenAPI contracts, consistent JSON error codes and generated frontend bindings; verify extractor/error cases and client/schema agreement, including multipart and binary responses, without adding a new documentation-generation pipeline.
- [x] 3.3 Bind the existing Resources workspace/drawer/panel, folder/drop destinations, preflight conflicts, statistics and individual download control to manager; verify creation-only conflicts, stored-versus-indexed wording, nested folders, navigation during transfer, partial multi-file failure, browser download limits and preserved routes/styles/controls with bulk ZIP visibly unavailable.
- [x] 3.4 Bind retry/reload/account-change behavior to actor/space-scoped receipts and browser files; verify uncertain results before resend, file re-selection, no cross-account cache disclosure and queued-file cancellation without claiming document deletion.

## 4. Acceptance, independent review and documentation

- [x] 4.1 Validate the complete UI journey against disposable PostgreSQL/OpenFGA/SeaweedFS with processing services unavailable: import, leave/return, reload, inspect metadata and download identical bytes; capture current UI behavior, failure outcomes and relevant log evidence in this task record.
- [x] 4.2 Measure the specified OpenFGA calls/pages/tuple operations, SQL lock duration, memory/temp bounds and latency with stated users, memberships, spaces, documents, replicas and upload concurrency; verify budgets and absence of body/S3 IO while holding the organization lock.
- [x] 4.3 Obtain an independent read-only manager reconstruction review of this implemented lot and affected consumers; record base/head, coverage, findings/dispositions, add regression tests for actionable findings and obtain a correction re-review. This is not full-PR readiness.
- [x] 4.4 After review, update arc42 02, 03, 03a, 05, 08, 09 and A1-A3 to verified present behavior, regenerate derived references and add relevant `// Proves: I<n>` tests; verify the dossier neither claims ingestion nor embeds this plan.
- [x] 4.5 Run manager `make test`, `make test-integration`, `make code-quality`, root `make -C docs/architecture check`, relevant frontend checks and strict OpenSpec validation; record commands/results, then reconcile/sync/archive the completed change and make one clean implementation/documentation commit on `weaver`. Do not push without explicit developer agreement.

## Planning review

Planning-only baseline: `a722a6e47eb19b710208eac2d8e664aad2eaed5f`.
The developer confirmed creation only with explicit conflicts and no overwrite.
At planning review, runtime robustness remained unverified; the implementation
evidence below is separate from proposal validation.

Independent read-only planning review on 2026-10-19 covered these uncommitted
artifacts against that unchanged HEAD, with current manager, import UI and
capability specs as evidence. Two P2 findings were corrected and independently
re-reviewed: durable receipt acknowledgment/retry lineage, and explicit server
versus browser download bounds with bulk ZIP excluded. No actionable finding
remained in the corrected planning scope. Strict OpenSpec validation and the
read-only arc42 `tools/docs.py check` passed. No service, provider, browser or
implementation tests were run; this is not branch/PR readiness evidence.


## Implementation and review evidence

Scope: this local lot and affected consumers, baseline/head before commit
`a722a6e47eb19b710208eac2d8e664aad2eaed5f` plus its working-tree diff. Deployment
integration at that baseline is retained; no live deployment or bucket was changed.
This is not a full-branch or whole-Fred readiness claim.

Independent backend and frontend reviewers examined the implemented lot and then
re-reviewed corrections. Backend findings covered bucket lifecycle inspection,
download backpressure deadlines, cleanup fairness under organization contention,
retryable FGA failure mapping and non-root temporary-volume initialization. All
were fixed with regression coverage and re-reviewed. A test-only shared-project
quota assertion was corrected to use an authorized actor and re-reviewed.
The browser acceptance test was independently reviewed and strengthened to
count all upload POSTs and prove receipt recovery before full navigation.
Its long setup also exposed a disposable SeaweedFS capacity defect: system
writes consumed the fixture's only volume before the first original. The fixture
now permits both collections; the correction was independently re-reviewed.
Frontend findings covered aggregate creation-only conflicts, processing/deletion
controls leaking legacy actions, directory invalidation after receipt recovery,
session identity surviving token renewal, and published rows incorrectly showing
pending. All were corrected, regression-tested and independently re-reviewed.
The dedicated arc42 pass corrected snapshot scope, panel navigation, displayed
metadata and cleanup backoff/logging descriptions after reviewer feedback.

Verification evidence on 2026-10-19:
- Manager `make test`: passed. `make test-integration`: 102 passed. Additional
  document-focused run after measurement/backlog assertions: 12 passed.
- Manager `make code-quality`: clippy, rustfmt and model parity passed.
- Frontend lint, production build and typecheck passed; 58 targeted files/487
  tests passed. Final stored-status correction: 30 files/205 tests passed.
- Chart generation/default values validation and seven chart tests passed.
- Arc42 generation/check passed, including SQL diagram, derived routes/config,
  invariant proofs and rendering every Mermaid diagram.
- New migration note passes the policy parser. The aggregate `make migration-check`
  is blocked by unchanged baseline `integrate-manager-fred-deployment.md` missing
  its required Prerequisites section; no unrelated note was rewritten.

The request-budget fixture uses five users, organization/team, two writer
memberships, one 128 KiB original, concurrency one: 11 Reads, three Checks,
two Writes/four guard operations. Directory budget stays three Reads/two Checks
with one versus 101 metadata rows. Two cleanup instances test claims/restart.
Spool is exactly 128 KiB at held Put and zero afterwards. Process RSS including
test proxies/concurrent fixtures is 75,628/76,240 KiB; elapsed upload 283 ms.
Sampled guarded holds are 9.7/12.3 ms with 15.3 ms maximum polling gap; another
connection obtains the organization lock during held S3 IO in 0.19/0.42 ms.
These are bounded fixture observations, not production throughput claims.

The three changed main specifications validate strictly after synchronization.
Aggregate strict validation is 33/34: unchanged `frontend-surface-scale` still
has a placeholder Purpose. That unrelated capability is not rewritten here.
The broad browser journey reaches personal opening but fails its existing Agents
page mobile-width assertion before the document segment; focused document mode
uses the same disposable real services and preserves that broad assertion.

Browser acceptance: `CONTROL_PLANE_BROWSER_DOCUMENTS_ONLY=1 make -C
apps/control-plane test-browser` passes the complete document journey with real
OIDC/PostgreSQL/OpenFGA/SeaweedFS. It uploads a 106,496-byte original, simulates a
lost response after server publication, observes the UI's stored receipt lookup
without a second upload, leaves/reloads Resources, downloads identical bytes and
SHA-256, and imports a second file while explicitly skipping the existing name.
No processing request is dispatched; unchanged shell task-feed reads remain
unavailable. Desktop and 390px captures were inspected in frontend target/. The
narrow capture exposes shared-layout overflow; it does not establish mobile
readiness, and the unchanged global layout is outside this storage lot.

Final rerun after fixture correction: one document browser journey passed, followed
by all 102 integration tests (55.17 s). Manager code-quality passed again. The
final browser-test corrections and quality-chapter paragraph were independently
re-reviewed without remaining findings. The changed main-spec requirement blocks
match all three deltas; strict validation passes for each and for this change.
All required commands were run; aggregate unrelated validation limits remain
explicitly recorded above. This closes the local storage lot, not full PR or
mobile readiness. No push is authorized or performed.

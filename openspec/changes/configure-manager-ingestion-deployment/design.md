## Context

See proposal.md for motivation. Baseline: Fred `8d3b66e7dd721beab2a46a29afc336188a458984`, branch `weaver`; the checkout also contains a large unrelated staged merge. The factory remains on `swift`. No running installation has been inspected or changed for this proposal.

The developer clarified that production uses GCS on S3NS. Its exact API surface, identity mechanism, object inventory and bucket policies have not been inspected. SeaweedFS-only success cannot establish compatibility with that environment.

Observed constraints:

- `deploy/k3d/build` builds manager, KF and frontend; the factory selects the local chart and supplies its own instance values. Its engine already supports `VALUES` applied last.
- Manager storage/processing are absent from default effective values. The two chart examples are templates, not a complete factory overlay: Helm replaces their environment/volume lists.
- `documents/mod.rs` binds original coordinates to SQL. `processing/store.rs::prefix` defines generation-scoped outputs. `deploy/k3d/reset_data.py` accepts the existing local bucket/index names only.
- Manager currently rejects a shared original/result bucket and assumes exclusive ownership of its original-key namespace during inventory cleanup. Swift's MinIO and GCS stores both use `<bucket_name>-documents/<document_uid>/input|output/...`; its generic objects use `<bucket_name>-objects`. Reference: local `origin/swift` at `19709b017f7bff35e254df3242f38f6e5b0edd02`, `application_context.py::get_content_store` and the corresponding content stores.
- `document-processing.yaml` shares one derived credential between manager and KF and mounts storage credentials on the manager worker. The Rust worker dispatches from SQL and does not use S3.
- Factory KF values mount the SeaweedFS and OpenSearch administrator credentials. A new scoped derived key alone would not remove this broader access. KF configuration still validates legacy storage; its common worker schedules legacy preview expiry.

## Goals / Non-Goals

**Goals:** an inspectable deployment of the existing processing feature using Swift's physical storage convention, with enforced workload access boundaries, a complete configuration and bounded local resource use. Explain and verify every durable result of one PDF upload before assessing concurrent operation.

**Non-Goals:** changing the authorization model or business UI; adding search/chat retrieval or a new knowledge-base registry; replacing storage providers; production HA or disaster-recovery certification; executing a legacy-data migration or a local reset; a new deployment framework. Local HTTP, one-node storage and reduced capacity remain explicit local deviations, not production guarantees.

## Decisions

### 1. Keep configuration ownership explicit

Use the production Fred chart and existing storage/processing fields. Add a complete named instance profile at the factory's `k3d-apps/fred/manager-ingestion.yaml`, selected by its existing `VALUES` option. `fred/deploy/k3d/README.md` is the entry point requested by the developer: it gives the exact command and links the profile, prerequisites and arc42 journey. It does not copy the values or define another deployment engine.

The corresponding factory changes are part of this proposed scope. Product examples remain portable references and must be corrected where their credential guidance conflicts with the access matrix below. The ordinary profile without this overlay remains usable. Existing deployment integration acceptance is not rewritten as completed.

### 2. Align physical storage with Swift

Decision confirmed by the developer on 2026-10-21: use Swift's existing bucket naming and per-document organization to reduce production migration work. Retain the instance's `<bucket_name>-documents` bucket for originals and results and `<bucket_name>-objects` for its existing generic-object consumers. Keep `<document_uid>/input/<filename>` and `<document_uid>/output/...` as the document roots. The terms `raw` and `derived` describe their roles in operator documentation; they do not rename `input`/`output` or introduce new physical buckets. This supersedes the earlier two-bucket proposal.

There is no demonstrated throughput or latency benefit from splitting originals and results into two buckets. Separate buckets simplify bucket-scoped privileges and maintenance policies, but avoiding a forced copy/reorganization of the existing corpus is the preferred trade-off. This decision does not assert that access policies are equivalent across providers; section 3 defines the enforcement evidence still needed.

Retain the manager's immutable generations, idempotency, integrity checks and SQL publication. New processing outputs belong beneath the document's `output/` root with processing/generation-qualified keys; do not overwrite a single canonical `output.md` on every attempt. The published manifest remains authoritative. Keep existing legacy object keys unchanged until an explicit import establishes their SQL identity and ownership. Preserving the roots is not a promise that every generated artifact path or document identifier is already interchangeable with Swift.

Implementation must change more than YAML: replace both Rust's separate-bucket check and KF's legacy-bucket exclusion only after validating non-overlapping input/output key construction; preserve the installation binding in SQL; validate filename/key safety; revise namespace-based inventory and orphan cleanup to use durable ownership records, including after failed-upload receipts expire and late writes arrive. Unknown Swift objects and another installation's objects must never become manager cleanup candidates merely because SQL has no corresponding row. Keep generation as the final directory segment so KF can restore the preceding generation, or explicitly revise that contract. Similarly, KF's legacy expiry, inventory, repair and deletion paths must not sweep manager generations. Support for simultaneous legacy and manager writers/maintenance is not implied by sharing the bucket convention.

Keep `document-vectors` separate from legacy indexes. PostgreSQL owns placement, receipts, the generation inventory and the published manifest; folder display names remain SQL metadata. Temporary upload/extraction files are not durable storage. On implementation, update the canonical formulas in `docs/architecture/05-documents.md` and link them from the operator journey.

The local reset guard must recognize the explicit configured resources and verify ownership before deleting anything. Do not add a whole shared documents bucket to a blanket reset allowlist. Refuse conflicting existing Rust SQL bindings without modifying data; use a fresh dedicated fixture for initial validation. Data adoption, reset and production migration remain separate operator decisions.

S3NS documents bucket names as immutable ([migration documentation](https://documentation.s3ns.fr/storage/docs/moving-buckets)). This alignment removes the proposed rename/split as a reason to copy production objects. It does not remove the need to map legacy document identities, authorization, SQL state, manifests and vectors into manager. Any remaining physical migration needs its own object inventory and cost assessment.

### 3. Enforce privileges across every credential available to a workload

| Workload | Original storage | Processing-result storage | Other access relevant here |
| --- | --- | --- | --- |
| Manager API | Put/Get/Delete for owned input keys; bounded ownership-aware inventory; required bucket-policy inspection | Get and required bucket-policy inspection | SQL, existing OpenFGA/identity services; no vector writer |
| Manager worker | None | None | SQL and Temporal; existing lifecycle FGA access where enabled |
| KF worker | None directly; authorized original streaming through manager | Put/Get; common-role cleanup also List/Delete | Authenticated manager callbacks, configured model and scoped vector index |
| Browser/frontend | None | None | Existing authenticated manager API |

This table is the target privilege boundary, not evidence that the common bucket already enforces it. Use distinct application identities with access to the required object operations. Verify all credentials available in each pod: a legacy KF identity with bucket-wide access would bypass the new restrictions. Isolate or disable incompatible legacy jobs in this manager ingestion profile rather than retain such access silently. Apply the same principle to KF's shared OpenSearch client: an isolated index name with an administrator password is not an access boundary. Application Secrets contain only their required keys; administrative credentials remain in infrastructure provisioning.

The factory owns provisioning of buckets, scoped principals, index roles and the dedicated confidential `knowledge-flow-worker` identity with the claims in the existing client example. Reuse its existing provisioning conventions; the current identity manifest supports only id/secret/grants, so bounded support for the required audience/claims must be explicit and tested. Persist generated secrets across reruns and use Secret references, including for the S3 authentication configuration itself.

Bucket-scoped permissions alone cannot enforce the input/output boundary in the selected layout. Before implementation acceptance, test the pinned local provider and actual GCS/S3NS interface for object-scoped permissions and listing semantics, particularly with the document identifier preceding `input/` or `output/`. Do not assume wildcard object-resource rules or object-list filtering are supported. If direct worker credentials cannot enforce the boundary, an alternative access mechanism needs an explicit reviewed design before implementation; neither silently restore the bucket split nor grant broad access. This provider-enforcement question remains unresolved and the storage naming decision does not constitute a security-parity result.

Before production-parity acceptance, verify the same operation matrix, conditional writes, authentication and bucket inspection semantics against the actual GCS/S3NS interface. AWS IAM and SeaweedFS examples are not evidence of GCS IAM behavior. Preserve the production protection requirements; a mismatch with manager's current bucket constraints requires an explicit design decision, not disabling protections to make the local profile pass.

GCS specifically documents that object-name IAM conditions cannot restrict `storage.objects.list` to a subset of objects ([provider documentation](https://docs.cloud.google.com/storage/docs/access-control/iam#conditions)). A direct listing worker therefore cannot obtain input-name isolation through such a condition alone. Also distinguish physical layout from API support: Swift has a native GCS/ADC adapter, whereas the current manager/KF processing adapters use S3 clients and credentials. Matching names does not establish equivalent authentication or protocol support.

The intended boundary separates workload operations on inputs and outputs; it does not claim hostile-worker isolation between every organization's outputs. Manager's protocol and SQL publication enforce document scope. Do not describe UUID key components as an IAM boundary.

### 4. Make activation reproducible

The complete instance profile preserves required SQL, OpenFGA, Keycloak, model and observability references while replacing broad storage credentials. It configures manager `storage.content` and `scheduler.processing`, all enabled KF roles' `manager_processing`, the matching Temporal namespace/base queue, and dedicated vectors. Keep the five application deployments for the first local validation; the common KF deployment explicitly serves all four roles with bounded per-role concurrency.

Use the existing `features.scheduler.export_contract` from the exact selected KF image against the effective worker configuration. Install its credential-free output as the `manager-processing-contract` ConfigMap through the normal operator manifest workflow before application startup. Record the image/configuration digest with that artifact and roll manager whenever it changes; validate queue/profile agreement and fail clearly on missing/stale inputs. Do not check in a hand-maintained JSON policy or infer it from developer defaults. The runbook covers rendering/export/install/deploy in order, including first installation and rerun, without hidden cluster writes from the build hook.

Use the existing manager identity validation and private bucket prerequisites. Manager currently rejects versioning, Object Lock and enabled expiration rules; keep the dedicated local fixture within those limits. Reusing the production bucket name does not authorize changing its protection settings. Validate that compatibility separately. Durable restore covers matching SQL, objects, vectors and authorization; disabling admission retains services needed to drain work.

### 5. Audit performance with actual resource multipliers

Set upload admission, spool capacity, extraction concurrency, temporary space, derived budgets and timeouts explicitly. Show the worst-case combined local disk/memory demand from simultaneously served roles. The current factory caps one activity per role; the chart-only default allows three. Do not multiply only the replica count while omitting roles and activity concurrency.

Account for original Put plus integrity readback, original streaming through manager to KF, generation output Put/readback, predecessor restoration and manager verification before publication. The review must identify repeated transfers and sequential artifact loops and quantify their bytes/calls on the fixture. Preserve integrity checks unless a separately reviewed change provides equivalent guarantees.

First validate one text PDF manually. Then use a bounded, explicitly sized concurrent scenario on dedicated test data if authorized: record document counts/sizes/pages, profile, activity settings, CPU/RAM/disk, queue wait, stage/end-to-end latency, S3 calls/bytes and retries. Report unavailable measurements and local topology limits. One successful upload cannot establish production capacity.

## Risks / Trade-offs

- Broad inherited secrets can defeat new restrictions: inspect rendered pod environments and test denied access with every mounted application principal, including legacy KF credentials.
- Optional examples replace required lists: test the actual factory + profile merge, not only isolated examples.
- Worker contract/image drift can misroute accepted work: regenerate from effective configuration on change, retain provenance and drain before incompatible rollout.
- Local HTTP and a single storage node do not exercise production transport or HA: record this boundary and the production TLS/secret/backup requirements in the existing operations guide.
- Shared-bucket cleanup can destroy unrelated content: prove ownership-scoped deletion and preservation of unknown Swift objects, other installations and published generations. Reject unsafe reset or conflicting SQL bindings without changing data.
- Staged unrelated work: stage only this change's paths when implementation is accepted; no merge completion, reset or broad commit is implied.

## Migration Plan

After scope confirmation, implement and render the product/instance changes, independently review them and make the exact deployment procedure available to the developer. Provision only the required additional identities/resources, preserving existing credentials and content. The developer performs the first manual PDF journey; collect redacted SQL/S3/vector/Temporal evidence using the existing arc42 procedure. Group required automated checks and correction review before the implementation commit. Keep all pushes and destructive operations under explicit developer authorization.

Disabling processing admission is the first rollback step; retain original reads, callbacks and cleanup until work drains. Do not rename, delete or adopt existing storage namespaces automatically. Archive this change only after its actual deployment and audit acceptance is recorded.

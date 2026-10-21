## Context

See [proposal.md](proposal.md) for the outcome and exclusions. Inspection baseline:
`chore/rust-rebac` at `a722a6e47eb19b710208eac2d8e664aad2eaed5f`, initially clean.
The manager deployment integration and subsequent Home fixes are already committed.
Do not replace their control-plane service/image/configuration contract.

| Responsibility | Existing Python / UI evidence | Manager boundary at inspection baseline |
| --- | --- | --- |
| Import | Knowledge-flow `ingestion_controller.py` has upload-only and upload/process routes, name/quota prechecks and NDJSON results | No content mutation route; Resources opens the existing drawer with sending unavailable |
| Ownership | Python tags and document metadata drive the old corpus | `document` has immutable space/folder placement; OpenFGA evaluates space permissions |
| Original storage | `IngestionService.save_input` stores bytes then registers metadata/rights/quota | Metadata reads only; SQL insertion helpers do not constitute an upload journey |
| Recovery | `kf_ingestion_submission`, task rows/events, retry delivery and UI import state cover processing | Space-deletion worker exists; no document upload journal or S3 client |
| Removal | Python metadata/quota removal and best-effort remote cleanup have separate failure boundaries | Folder/space deletion rejects document-bearing targets |
| Configuration | Python supports several stores, ingestion modes and quotas | Typed manager storage currently configures PostgreSQL; legacy config fields do not enable content storage |

Source anchors: `apps/control-plane/src/{api,db,domain,spaces,error,config}.rs`,
its migrations and lifecycle module; `DocumentWorkspace.tsx`,
`DocumentUploadDrawer.tsx`, `importRun.ts` and `unfinishedImports.ts` under
`apps/frontend/src/rework`; `docs/architecture/05-documents.md` and `09-quality.md`.

The active `simplify-corpus-authorization` design already assigns project storage
to the parent team's quota. Its older proposal wording about role inheritance
disagrees with the implemented model: this lot follows the current OpenFGA model
and arc42 matrix, including descending editor/analyst access. It does not alter roles.

## Goals / Non-Goals

**Goals:** one externally observable commit point for a stored original, bounded
resource use, useful retry outcomes, current space authorization and a complete
existing-UI journey. No successful upload result until bytes and metadata agree.

**Non-Goals:** a generic job engine, a new frontend, storage-provider portability,
large-file S3 multipart upload, or compatibility with Python identifiers. The
future migration and processing contracts remain separate decisions.

## Decisions

### 1. Manager owns the stored original and its upload receipt

Use the existing `document` table for published metadata, adding the opaque object
key and constraints needed for nonnegative length and a valid SHA-256. Preserve
UUID identity and immutable placement. No document or folder OpenFGA tuples.

Add one `document_upload` journal for request identity, actor, resolved space/folder,
quota owner, normalized filename, measured length/digest, generated object key,
state, lease/deadline, outcome/document ID, acknowledgment/retry lineage and cleanup
diagnostics. This is separate
from `document` because a failed or interrupted operation is not a document and
its cleanup must survive removal of the original folder/space. Historical target
IDs in terminal receipts confer no ownership or authority. Active references are
validated under the same organization lock as folder/space deletion.

A singleton `document_storage` row stores the namespace binding, inventory cursor,
orphan-byte accounting and maintenance claim. Its lifecycle spans all attempts and
receipt retention, so it is separate from both the document registry and journal.

Reusing `document` for failed operations would contaminate its ready-only reads,
unique-name rule and placement foreign keys; using space-deletion jobs would mix
unrelated lifecycles. Do not add an outbox, general task table, role mirror or
provider-neutral storage framework for this lot.

### 2. Reserve, write, publish; never hold a SQL transaction across S3 or body IO

1. Authenticate and check current admission, organization context and Write on
   the destination space before accepting file bytes. Validate target folder.
2. Consume exactly one multipart file into a private temporary file, incrementally
   computing its length and SHA-256. Validate the entire request before reserving
   anything. Bound bytes, idle/total duration and concurrent transfers.
3. In a short organization-locked transaction, recheck active placement, current
   admission/Write, request identity, name availability and quota. Reserve the
   name and bytes with a unique server-generated object key. Commit before IO.
4. Write that immutable key with a retryable file body and explicit timeouts.
   Always stream a read-back and verify length/hash before publication, including
   after a lost acknowledgment or conditional-write conflict.
5. In another short guarded transaction, verify the same live reservation and
   actor's current admission/Write, and atomically insert the document and mark
   the receipt stored. The request token must still be valid. Release reserved
   bytes into committed usage in this transaction. Only then return success.

Use the existing organization lock, active-state checks and OpenFGA guard/fence
protocol in both write phases. Receipt transitions use compare-and-set conditions.
Pending/ready references prevent folder subtree deletion and space retirement;
abandonment removes the active reservation before deletion can proceed. A late
completion cannot recreate a deleted folder/space or publish an abandoned receipt.

Authorization after the transfer is deliberate: revocation ordered before the
publication transaction prevents publication. A background reconciler never
publishes on behalf of a cached user. Reads check current rights before opening
the object; already-streamed bytes cannot be recalled after revocation.

### 3. Explicit idempotency and conflict outcomes

The request has an `Idempotency-Key` UUID, scoped to the authenticated subject,
and bound to space/folder, canonical filename, length and digest. The server
computes the digest; it does not trust a client assertion. A valid replay returns
the same document ID without another committed object. Different content or
placement with that key returns `409 idempotency_conflict`. A live concurrent
attempt returns `409 upload_in_progress` with `Retry-After` and a receipt URL.

Check ready documents and active reservations under the same organization lock;
the document constraint remains a final integrity check. This covers two different
keys importing the same name. Preflight is advisory. The developer confirmed
creation only: `409 name_conflict`, no implicit replacement or cross-folder
deduplication. A failed terminal receipt is stable; an explicit new attempt uses
a new request key. A lost success response is resolved through the existing key,
not by creating a new one. Keep stored request identity with the document; terminal
failed receipts have a documented retention window (proposed seven days).

The journal also owns panel visibility. Acknowledging an actor-owned terminal
receipt is idempotent and hides it from the active receipt list; it does not erase
the idempotency result or affect content/cleanup. Completed rows are acknowledged
when the existing panel removes them, and failed rows when the user dismisses them.
A retry carries `retry_of` and a new request key. After checking the predecessor's
actor, target and content binding, successful reservation atomically links and
supersedes that failed predecessor. Only one successor wins concurrent retries;
other callers get its receipt. The list excludes acknowledged/superseded entries,
so a successful retry or dismissal stays resolved on a new browser. Acknowledging
a running upload is refused; queued cancellation remains client-side.

Accept 1..255 Unicode characters, reject control characters, slashes, backslashes,
empty/whitespace-only names and `.`/`..`. Compare names using a documented,
case-sensitive NFC form; retain the validated display name. Apply the same rule
to preflight, reservation and final uniqueness. Names never form storage paths.

### 4. Cleanup is storage housekeeping, independent of ingestion

Run a bounded reconciliation loop in manager API processes, coordinated by SQL
leases so multiple replicas are safe. On startup and periodically, expire abandoned
reservations and delete their objects outside SQL locks. Keep retryable cleanup
outcomes durable, with backoff, bounded batch size and a health signal for backlog.
Clean only manager-owned keys. Temp files live in a dedicated bounded volume;
request cleanup and startup cleanup never sweep another replica's files.

A timed-out Put may complete remotely after a successful Delete. Therefore one
Delete is not proof that cleanup is complete. Also perform a paginated inventory
pass over the manager-owned S3 prefix, with a persisted cursor. Live reservations are the grace boundary; reservation
always precedes Put and immutable keys cannot gain a later publisher. Before deleting a candidate, recheck SQL: preserve ready objects and live
reservations; atomically abandon expired reservations. An unknown attempt key can
never later be published because reservation precedes Put and keys are never reused.
If SQL is unavailable, delete nothing. Repeat full passes so a late-arriving object
behind the cursor is eventually found. This allows bounded receipt retention
without promising that a client timeout cancels a remote write.

The journal and this loop are not connected to Temporal, ingestion, task SSE or
knowledge-flow task rows. Storage cleanup must work when those services are stopped.

### 5. One S3-compatible implementation with explicit operational limits

Use the official AWS Rust S3 SDK, pinned with a compatible toolchain/lockfile, for
signing, connection reuse and request construction. Use a private dedicated bucket
or prefix, generated keys, a configured endpoint/region/path style and secret
references. Support the deployed SeaweedFS 4.29 service as an acceptance target;
do not assume AWS behavior from the label "S3 compatible". Keep credentials out of
DTOs, logs, URLs and browser code. No public bucket, presigned bypass or proxy URL
chosen by the caller. Require TLS outside explicit local deployment configuration.
The supported bucket contract has versioning and Object Lock disabled, with no
external lifecycle policy deleting published keys; verify this explicitly. Plain
DeleteObject is not sufficient cleanup for arbitrary versioned buckets.

Use single PutObject and bounded local spooling in this lot. The supported
per-file maximum is 100 MiB; configuration can lower it, not raise it beyond the
browser download budget. Proposed defaults are that maximum, eight active
transfers per replica, 30-second idle and five-minute
total transfer limits, an explicitly sized temporary-volume budget, and finite
S3 connect/attempt/operation limits. Reject excess capacity instead of an unbounded
queue. Configuration validation must reject inconsistent or unlimited values.
The reservation expiry must cover bounded storage retries, verification and
publication plus a safety margin; reject a lease configuration shorter than that
budget. Crashed attempts still expire without an indefinitely renewed lease.

Use conditional creation (`If-None-Match: *`) where verified by the provider;
immutable unique keys and no alternate bytes for an attempt remain mandatory.
If a selected provider lacks a required property, fail the compatibility test and
resolve it explicitly; do not silently weaken the publication guarantee. Configure
checksum behavior deliberately, not by treating an ETag as SHA-256.

Relevant primary references, consulted 2026-10-19:
- [Axum multipart limits](https://docs.rs/axum/latest/axum/extract/multipart/struct.Multipart.html): configure limits explicitly rather than retaining the small default or disabling them globally.
- [AWS conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html): precondition failures and concurrent deletes have distinct outcomes.
- [AWS Rust timeouts](https://docs.aws.amazon.com/sdk-for-rust/latest/dg/timeouts.html): set operation/attempt limits and separately bound consumption of download streams.
- [S3 upload integrity](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html): distinguish content checksums from ETags.

### 6. Quotas and bounds are authoritative at reservation

Charge a project to its canonical parent team, a team to itself, a personal space
to itself, and organization-owned content to the organization. Resolve this from
OpenFGA placement, not a new SQL hierarchy. Persist the accounting owner as derived
storage metadata, never as an authorization grant. Proposed configured budgets
start at 5 GiB for personal, team and organization buckets, matching existing
personal/team deployment values. No new quota administration UI.

Account for committed bytes plus active reservations atomically under the
organization lock. Expose the applicable budget and usage, including reservations,
to authorized content users, without enumerating documents in inaccessible sibling
projects. Per-space document counts and type/size statistics describe only that
space. Failed cleanup bytes are separate operational usage, with a bounded backlog
budget that stops new uploads before leaks can grow unchecked. Test quota boundaries
across simultaneous projects of the same team and separate personal spaces.

### 7. Manager API and existing UI bindings

Route names are manager-native; all errors use the existing JSON `detail` envelope
plus a stable machine `code` for these contracts. Do not expose SQL/provider messages.

| Contract | Behavior |
| --- | --- |
| `POST /folders/{id}/documents/preflight` | Bounded list of names/sizes; authorized advisory conflicts and limits, no reservation or writes |
| `POST /folders/{id}/documents` | Exactly one multipart file and request key; 201 stored, 200 identical successful replay; never ingestion acceptance |
| `GET /spaces/{id}/document-uploads` | Paginated caller-owned receipts under current space Read, for reload/recovery; no other actor's attempts |
| `GET /document-uploads/{request_key}` | Caller-owned receipt under current space Read, resolving an uncertain result |
| `PUT /document-uploads/{request_key}/acknowledgment` | Idempotent acknowledgment of the caller's terminal receipt under current space Read; no content deletion |
| `GET /spaces/{id}/entries` | One snapshot/page/total for child folders and ready documents, existing filtering/sorting and stable ID tie-breaks; root supported for navigation |
| Existing document list/detail | Ready metadata only, consistent identifiers, length/digest/creator/time; current space Read |
| `GET /spaces/{id}/storage` | Applicable budget/reservations and this space's recursive ready-document statistics |
| `GET /documents/{id}/content` | Authorized original download, streaming attachment with length and safe filename; no redirect to an unprotected object |

Use 400 for malformed syntax, 401 for unauthenticated requests, 403 for existing
same-context targets without the required permission, 404 for absent/foreign-context
targets, 409 for state/name/key conflicts, 413 for byte limits, 422 for invalid
fields or quota exhaustion, 429 with Retry-After for local admission capacity,
and 503 for a storage/authorization dependency failure. Define extractor and
stream failures too. A missing object for a ready row is an integrity error (503
and operator signal), never an empty successful download.

Download uses `Content-Disposition: attachment`, safe UTF-8 filename encoding,
`X-Content-Type-Options: nosniff`, and `Cache-Control: private, no-store`. Ignore
Range with a full 200 response in this lot; previews and resumable downloads are
not wired. Abort a broken stream; do not retry by concatenating bytes after headers.
Explicitly bound active downloads, duration and memory as well as uploads.

The no-whole-file-buffering guarantee applies to manager. The existing browser
single-file download uses an authenticated fetch then `Response.blob()`; retain
that control/helper for this bounded lot, with a 100 MiB maximum file and one
active individual download per page. Document the possible additional Blob/copy
overhead instead of claiming constant browser memory. Bulk/selected-folder ZIP
download is outside this lot: preserve those controls as visibly unavailable.
Do not wire the current unbounded `Promise.all`/JSZip helper to manager originals.

Adapt the same `DocumentWorkspace`, drawer, import run and panel. Do not concatenate
independently paginated folder/document results or create fake tag IDs to reuse
Python hooks. A mixed directory uses one coherent query and total. Preserve nested
folder selection/drop using existing manager folder creation; an upload requires
a named folder and one immutable owning space. Multiple files are independent
requests with bounded frontend concurrency; navigation does not cancel them.

Use actual transfer/stored/error states. A stored original is downloadable but
not searchable; no synthesized ingestion stages or ingestion task IDs. Preserve
controls for later capabilities in their existing layout with truthful availability.
Retain failed/retry entries and existing stop-before-transfer behavior. Scope
browser state by issuer/subject/space and clear access-sensitive caches on account
change. On reload, resolve known request keys before offering resend; a missing
browser File requires re-selection. Both quota/statistics and uploaded rows in this
journey come from manager, not knowledge-flow's unrelated corpus.

### 8. Authorization cost and lock budget

Use chapter 09's notation: `Q(u)` is all pages of direct-role Reads filtered by
`user=user:<u>, object=space:` plus placement Reads for distinct granted spaces;
`L` is 0/1/2 target placement Reads. All Reads/Checks use HIGHER_CONSISTENCY.
One guard Read filters exact organization/version; its fence Write changes two
tuples. No folder/document tuples, ListObjects, ListUsers or BatchCheck are added.

| Successful phase | Proposed client RPC budget |
| --- | --- |
| Initial upload/preflight authorization | `Q + L` Reads, one Write-permission Check |
| Reservation, and separately publication | `Q + L + 1` Reads, one Write-permission Check, one fence Write (two tuple operations) |
| Receipt/list/detail/download/storage read | `Q + L` Reads, one Read-permission Check |
| Combined directory with can_write | `Q + L` Reads, two Checks |
| Housekeeping | No OpenFGA RPC; SQL journal state authorizes cleanup of unpublished keys only |

The two guarded transactions hold an organization lock through context resolution,
Check, fence and SQL mutation only. No body read, hashing, disk/S3 IO, retry sleep or
stream lifetime occurs under that lock. Reuse the held SQL connection to avoid
pool starvation. Quota queries grow with a team's documents/reservations; inventory
work grows with stored objects. RPC count does not imply constant OpenFGA evaluation
work or overall latency. Measure page counts, tuple operations, lock duration and
latency with stated users/memberships/spaces/documents and concurrent uploads.

## Risks / Trade-offs

- SQL and S3 cannot commit atomically: publish only verified bytes, fence late
  writers, and reconcile durable reservations plus remote inventory.
- Local spooling doubles IO and needs disk: accept the cost for bounded memory,
  reliable retry and verified digest; configure volume/admission bounds explicitly.
- Guarded writes serialize within an organization: retain the proven coordination
  protocol, measure contention, and do not hold it during transfer.
- The existing import specs assume processing/replacement: apply the accompanying
  explicit deltas; no ingestion success is simulated and no Python bug is copied.
- Stored content cannot yet be deleted through the business UI: make this first-lot
  boundary explicit at acceptance; folder/space removal must remain protective.
- SDK guarantees differ from SeaweedFS behavior: run provider contract and fault
  tests against the supported image; successful mocks are insufficient.

## Migration Plan

Add a new migration; never rewrite the existing applied schema. New published rows
require a real object. Existing metadata-only PoC rows must not be fabricated into
stored documents: fail a nonempty incompatible upgrade with an actionable preflight
message, or use an explicitly approved disposable-PoC reset. Swift data translation
is excluded. There is no API/path/identifier compatibility layer.

Deploy configuration and bounded temp storage through the existing manager-as-
control-plane integration. Keep the supported bucket/prefix private and exclusive
to this manager database. Cleanup assumes the database is authoritative: after a
database restore or when attaching an existing prefix, disable upload/cleanup
until an operator verifies the matching storage namespace and restored records.
Never adopt or sweep an unrelated occupied prefix automatically.
Disable upload admission before rollback; do not roll back
to a version unaware of active receipts, or drop rows/objects automatically. Verify
the existing deployed organization/folder/Home journeys alongside this new journey.

After independent implementation review and correction, update the arc42 journey,
security/matrix, documents, operations, quality and A1-A3 references from verified
behavior. Existing tooling generates routes from annotations, source excerpts and
proof markers; compiled OpenAPI/rustdoc/test-result generation and a new CI guard
are not part of this change.

The implemented lease is `2 * s3_seconds + transfer_seconds + 60`. Upload HTTP
receipts use the distinct `UploadReceipt` schema; lifecycle deletion keeps `Receipt`.
Directory sorting also supports document size with a folder-name fallback. Content
configuration remains optional: combined folder entries work without it, while
storage operations return 503. The spool uses a private child below the mounted
volume, preserving non-root operation with a root-owned emptyDir mount.

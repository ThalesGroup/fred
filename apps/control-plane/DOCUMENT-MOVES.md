# Document move schema: preparation and activation boundary

`migrations/0009_document_moves.sql` prepares a durable operation receipt. It does
not enable document moves. No HTTP handler, worker, search reader or scheduler
consumes this table. `document_immutable` still rejects every placement change.
The migration creates an empty table and does not rewrite existing documents,
processing records, generations, quotas, S3 objects or embeddings.

## Why a separate table

`document` remains the current catalogue fact. `document_move` is a request to
change that fact, with an immutable operation ID and destination. Keeping the
request separate avoids adding operation history and competing destinations to
every catalogue row. The existing `retrieval_*` fields describe inclusion or
exclusion from search; a boolean target cannot describe a move. They remain
unchanged. No generic projection framework or second task executor is introduced.

The scope is a drive document moving between folders or spaces of the same
organization. Conversation attachments and inter-organization transfers are
excluded. Moving a whole folder tree is not implemented by this receipt.
Temporary absence from search is accepted; access must always follow current SQL
placement. Neither content processing nor embedding computation is required.

## Stored contract

| Column | Type and requirement | Meaning |
| --- | --- | --- |
| `id` | uuid, primary key | Stable operation identity for retries and confirmations. A different move gets a different ID. |
| `document_id` | uuid, required, FK with DELETE CASCADE | Document whose definitive purge also removes its operational receipts. |
| `actor` | text, required, nonblank | Authenticated requester, supplied by the future Control Plane writer. No FK to the profile cache. |
| `source_space_id` | uuid, required | Current space captured from the document at request insertion. |
| `source_folder_id` | uuid, nullable | Current folder captured at insertion; null means drive root. |
| `destination_space_id` | uuid, required | Requested destination, verified in the same organization. |
| `destination_folder_id` | uuid, nullable | Live folder in that space, or null for its root. |
| `generation_id` | uuid, nullable | Published generation captured at insertion; null for a document without one. |
| `phase` | text, required, default `requested` | Operation progress described below. |
| `created_at` | timestamptz, required, default now | Finite creation timestamp, immutable. |
| `finished_at` | timestamptz, nullable | Database completion/cancellation timestamp, required exactly for terminal phases. |

The trigger captures source placement and generation from SQL even if the caller
supplies other values. All request fields are then immutable. Insertion checks
that the document is live, is not an attachment, has no observed pending/running
processing or unfinished inclusion command, and has a different destination.
It validates live source/destination spaces and the destination folder. These
checks establish initial facts, not authorization or a permanent reservation.

The primary key resolves operation callbacks. A partial unique index on
`document_id` permits only one `requested` or `projecting` operation per document.
An index on `(document_id, created_at DESC, id)` supports receipt lookup and the
document-delete FK. No polling queue, dispatch lease, retry counter or error
taxonomy is added before choosing the application integration.

Source/destination locations and generation are facts checked on insertion, not
permanent foreign keys. Old receipts must not prevent a source space, an abandoned
destination or an obsolete generation from being purged. A disappeared destination
must be detected again before moving; the requested operation can then be
cancelled. Receipts are bounded by document lifetime, not a separate audit archive.

## Phases and guarantees

| Transition | Meaning and SQL protection |
| --- | --- |
| Insert as `requested` | Request stored, document unchanged. Other initial phases are rejected. |
| `requested` to `projecting` | The document must already have the exact destination and captured published generation. The future writer changes placement and this phase in one SQL transaction. |
| `projecting` to `completed` | Placement and generation still match. The trusted application must first verify the external index update; SQL cannot inspect OpenSearch. |
| `requested` to `cancelled` | Abandon a request before applying placement. No rollback of a partially applied move is introduced. |

Other transitions are rejected. Terminal outcomes and their timestamps cannot be
rewritten. Retrying an unchanged phase is harmless. A confirmation must name its
operation ID and expected phase, never update by document ID alone. A stale ID
cannot identify a newer receipt; this SQL property does not fence external writes
from an old worker by itself.

In this preparation lot, the positive transition to `projecting` is deliberately
unreachable through ordinary writes: the unchanged placement trigger prevents the
required document mutation. The later activation migration must replace that
guard with a coordinated operation, not simply remove it.

## Required application integration before activation

1. Authorize both spaces, recheck lifecycle and membership, validate the destination
   folder and name collision, and check the destination local quota. The same
   organization total is unchanged. Budget initialization/maintenance from the
   storage-budget lot remains a prerequisite if that table is used.
2. Serialize admission with the existing document/organization coordination. A move
   must reject active processing, inclusion changes and another move. Processing
   and inclusion admission must reciprocally reject an active move. The current
   writers do not check this table; inserting a receipt is not a processing lock.
   Check source placement and generation again under that coordination.
3. Use a common lock order, including locking the document before its move receipt.
   In one short SQL transaction, apply destination placement and quota transfer,
   exclude the document from search while projection is pending, and advance the
   matching request to `projecting`. Preserve UUID, S3 locations, content and
   published generation. Network operations stay outside that transaction.
4. Reuse the existing durable execution facilities to update only index placement
   metadata. Keep the operation ID and captured generation throughout retries.
   Do not permit a new operation while an older worker may still write placement.
   SQL callback checks alone cannot prevent stale external writes.
5. On verified completion, confirm that exact operation and restore search
   eligibility according to the document's inclusion setting. A projection failure
   stays resumable; it must not release the active-operation constraint or silently
   reverse SQL placement. Concurrent deletion must prevent completion/resurrection.

The shared document visibility primitive must account for moves in progress.
Current search prefilters on chunk `space_id` and `folder_path`, then verifies
candidate placement and publication in SQL. This final check protects access but
cannot recover a candidate omitted by stale prefilters. Index projection must
therefore finish before the move is reported as searchable.

Persisted generation artifacts are immutable output evidence. Their captured
placement must not be treated as current authorization or routing after a move.
Review the readers that expose placement and hydrate current placement from SQL;
do not rewrite checksummed S3 artifacts to update their historical metadata.

The separate reprocessing change remains outstanding: both
`document_processing_success` and current admission prevent a new successful
processing cycle. This migration does not relax either restriction.

## Verification boundary

`tests/document_move_schema.rs` contains focused PostgreSQL checks for destination
scope, canonical source capture, immutable requests, one active request, stale
confirmations, busy documents, migration inertness and purge behavior. The SQL
tests require a disposable database and are separate from local compilation:

```sh
CONTROL_PLANE_IT_POSTGRES=postgres://postgres:it@127.0.0.1:PORT \
  cargo test --test document_move_schema -- --ignored --test-threads=4
```

They do not prove a functional move or coordination with Knowledge Flow. Those
journeys remain outside the validated architecture dossier until implemented and
validated by the lot owner.

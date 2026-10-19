# 5. Documents and knowledge

## Classification and content ownership

A space owns its folder tree, document registry and stored originals. Manager owns
their identity and storage lifecycle. Knowledge Flow owns document processing;
manager storage requests invoke neither ingestion nor Temporal. Manager folder
UUIDs and Knowledge Flow tag UUIDs are distinct identity domains.

A folder has one immutable space and at most one parent in that space. Paths
contain UUIDs, not display names. Renaming changes one label without rewriting
descendants or permissions. Sibling folder names are unique. Document placement
is immutable and its folder belongs to the same space.

## Authority

The owning space is the authorization boundary. Folders and documents have no
OpenFGA grants, parent tuples or individual permission lists. Increasing their
number adds no authorization tuples. Folder depth is limited to 15 independently
of OpenFGA evaluation depth.

Every request requires personal admission, the caller's unique organization and
current space authority. Members and effective editors/analysts read; effective
editors write. Administrator and owner titles confer no content access. Personal
spaces inherit no organization or team authority. The
[action/role matrix](03a-action-role-matrix.md) defines these distinctions.

A directory's write decision enables existing controls but reserves no right.
Mutations recheck after the organization lock and consume an OpenFGA guard revision.
Uploads do so twice: when reserving quota/name and when publishing verified content.
Token expiry and current CGU acceptance are rechecked at both boundaries. Request
body and object-storage IO take place outside that lock.

## Navigation and folder lifecycle

Resources uses one combined page of immediate folders and published documents,
plus the requested directory's ancestors, exact matching total and write decision.
Rows, ancestors and total share a read-only repeatable-read SQL snapshot; the
write decision is a separate OpenFGA Check before that transaction. Pages default to 50 rows and
contain at most 200, with folders first, name/date/size sorting and an identity
tie-breaker. Folders have no aggregate size and use name order for size sorting.
Search is a literal case-insensitive substring over the whole current directory.
Separate requests are live views; concurrent changes can shift offset boundaries.

Folder creation/rename trims labels, accepts 1..255 Unicode scalar values and
rejects separators and controls. Placement stays fixed. Deletion removes one
selected subtree atomically, but any published document or pending upload below
it refuses the whole operation. Multiple roots are independent, with partial
success reported by the UI. Space retirement likewise refuses stored documents
and pending uploads. A waiting mutation cannot resurrect a deleted target.

## Creating an original

An editor selects files in the existing drawer, including drop and nested-folder
destinations. Each upload targets a named manager folder. The advisory preflight
reports current conflicts and quota; the server makes the final decision under
the organization lock. The drawer starts nonconflicting files and retains conflicts
for explicit skipping. Replacement is visibly unavailable. Each file has an
independent outcome, so one failure does not undo another successful upload.

The server accepts one multipart file per request, up to the configured ceiling
and never above 100 MiB. It streams to a private temporary file with bounded
concurrency, idle and total deadlines, while measuring actual bytes and SHA-256.
The filename is NFC-normalized, case-sensitive and 1..255 Unicode scalar values;
path separators and controls are refused. Filename and reported MIME type are
metadata, never an object key or a trusted content type.

One SQL transaction reserves the destination name and bytes in `document_upload`.
Personal and organization spaces have their own quota; a team and its projects
share the team's quota. Published bytes plus pending reservations count toward
the limit. A name conflict returns 409 without overwriting an existing original.
Concurrent requests cannot overdraw shared quota or claim the same name.

After commit, manager writes a new opaque object with `If-None-Match: *` and checks
its complete bytes, length and SHA-256 by reading it back. Only then can the second
guarded transaction publish its `document` row and terminal `stored` receipt.
Publication failure leaves no visible document. Originals are immutable (I25).

## Receipts, retries and cleanup

`Idempotency-Key` is a request UUID scoped to the authenticated actor. The journal
binds it to destination, canonical name, size and digest. Repeating a stored upload
returns the same document ID; different bound content conflicts. Pending work
returns a conflict with a receipt location and retry delay. A terminal failed
attempt needs a new key linked by `retry_of`; only one successor can win.

The import panel observes the actor's durable receipts and distinguishes stored,
pending, failed and temporarily unknown results. Navigation retains active files
in memory. Reload restores receipts; resending after reload requires file selection
and a receipt check first. A token refresh preserves session identity. Changing
accounts clears held files and isolates cache/results. Files queued before dispatch
can be cancelled; this does not delete a document. Acknowledging or superseding a
terminal failure prevents its return after local browser state is lost.

The API's independent cleanup loop expires abandoned reservations, deletes failed
attempt objects and scans its persisted object namespace in bounded pages. SQL
claims coordinate replicas; retries retain progress and back off. Every inventory
candidate is checked against published and pending SQL state before deletion.
Repeated scans recover a late Put after an earlier Delete. SQL unavailability
prevents deletion; an excessive failed-object backlog refuses new uploads.
Acknowledged stored receipts remain available for idempotency. Cleaned failed
receipts expire after the configured retention period.

## Finding and downloading

After storage, the existing table displays filename, size, file-type icon and real
creation date. Reload finds the same identity. Statistics and quota use manager's
registry and reservations. The status says stored, without implying indexing or
search availability. The existing preview, processing, replacement, document
deletion and bulk ZIP controls remain visible and unavailable in this journey.
The separate knowledge-base consumer retains its existing service bindings.

Individual download checks current read permission and streams the original with
bounded server buffers and deadlines. It forces attachment, octet-stream,
`nosniff` and private/no-store headers. A missing object or inconsistent declared
length fails before the response; corruption discovered while streaming aborts
the body. The browser checks the final length and keeps at most one original Blob,
bounded by the 100 MiB ceiling. No presigned public URL or content conversion is
involved.

See the [Resources journey](02-user-journeys.md#priya-opens-resources),
[request costs](09-quality.md#original-storage-costs-and-failure-evidence),
[runtime](A1-manager-runtime.md#original-storage) and
[operations](A3-manager-operations.md#original-storage).

## Context

The resource journey reads manager folders/documents. `create_folder` already
uses `authorized_write`, organization locking, current OpenFGA context and a fence,
but lives in AppState/Temporal routes and accepts unchecked names. The legacy
CreateFolderModal defaults to knowledge-flow tags. Its optional submit callback
has no pending guard. See proposal.md for scope and approval.

## Goals / Non-Goals

Complete root/nested folder creation without changing the explorer's presentation.
Do not change role inheritance, add SQL grants, or enable admin self-assignment,
uploads, renames, deletion or document lifecycle controls.

## Decisions

- Move the existing POST registration to GovernanceState, preserving URL and DTOs.
  This removes the handler/router dependency on ingestion; full `serve` still
  connects to Temporal before HTTP startup.
- Retain OpenFGA `can_write`: local/inherited editors write, members/analysts/admins/
  organization owners/platform roles alone do not. Personal owner has direct editor
  from personal creation, without inherited authority. No inferred UI role matrix.
- Query the generated authorize-space mutation on each keyed resource entry; fail
  closed until allowed. The POST repeats authorization under the existing lock.
- Reuse the existing dialog's presentation with a required asynchronous submit
  callback; keep the legacy tag adapter for its existing consumers. Prevent Enter/
  click duplicates synchronously, disable dismissal while submitting, and ignore
  completions after unmount. Manager callbacks use generated mutations only,
  without automatic 401 replay of a potentially committed write.
- Keep the legacy 15-level ceiling, whitespace trimming and slash/backslash refusal.
  Reject control characters and names over 255 Unicode scalar values to keep names
  displayable and safely within the PostgreSQL sibling uniqueness index. No migration
  or rewrite of existing rows. Return 422 for these invalid requests, 404 for missing
  parent, 400 for parent in another space, 409 for duplicate sibling name.
- On success return to page zero of the same folder and refetch; do not insert a row
  optimistically or affect another space/folder after navigation.

## Authorization cost and ordering

UI adds one authorize-space request per resource entry, plus the create POST when
submitted and refreshed resource reads after success. No list-users/list-objects or
content tuples. Each authorization uses placement reads (0 organization, 1 team or
personal, 2 project), paged direct-role reads filtered by user and space object prefix,
and placement reads for distinct memberships, followed by one can_write Check.
For POST, placement precedes SQL BEGIN/organization advisory lock; guard reads,
context resolution, permission Check and fence precede parent lookup/INSERT/COMMIT
on the same connection. Successful fencing writes guard revision tuples only.
Memberships/pages drive RPC cost; folders/documents do not. Project parent resolution
is dependent, independent memberships overlap at the existing cap of 32. Verify
exact Read/Check/Write counts and tuple payloads in the proxy fixture, and report
wall time/fixture concurrency without interpreting it as production scalability.

## Risks / Trade-offs

- Stale visible permission -> server checks current rights; a 403 removes the action and disables further submission in the open dialog; an explicit resource refresh checks permission again.
- Lost response may follow commit -> no automatic retry; manual retry can receive
  409, with refresh available through the existing page reload action.
- Existing Python depth ceiling has a different technical motivation -> retain the
  same user boundary rather than silently allowing a deeper tree in this step.
- No rename migration -> existing names remain readable; validation covers creation.

## Migration Plan

Deploy the API and generated client together; no schema or infrastructure change.
Rolling back removes the UI action and leaves created folders readable.

## User-requested architecture review reference

Add an exhaustive matrix of implemented manager actions versus roles, with precise
scope, inheritance and additional gates. Distinguish queryable model capabilities
from implemented operations and operator CLI from authenticated HTTP. Record verified
Python/Rust semantic differences without changing those permissions in this lot.

# 5. Documents and knowledge

## Classification and content ownership

A space owns its folder tree and document registry. Manager is the authority for
folder identity, containment and lifecycle. The Resources screen uses that
classification directly; knowledge-flow tags are a separate identity domain.
Folder navigation and mutation need neither knowledge-flow nor Temporal.

A folder has one immutable space and at most one parent in that space. Its stable
UUID identifies it; its path contains UUIDs, not display names. Renaming changes
one label without rewriting descendants, references or permissions. Sibling names
are unique, including at the space root. Folders in different parents can share a
name. Containment is enforced independently of authorization, including document
references to folders in the same space.

## Authority

The space is the authorization boundary for its whole tree. Folders and documents
carry no OpenFGA grants, parent tuples or individual permission lists. Increasing
the number or depth of folders adds no authorization tuples. Folder depth is
limited to 15 as a classification rule, independently of OpenFGA evaluation depth.

Every request requires personal admission, the caller's unique organization and
current authority on the owning space. Members and effective editors/analysts read;
only effective editors write. Administrator and owner titles confer no content
access. Personal spaces inherit no organization or team authority. The
[action/role matrix](03a-action-role-matrix.md) defines these distinctions.

The directory response carries a current write decision for the existing controls.
It is not a grant: mutations recheck authority after acquiring the organization
lock. A guard fence orders those decisions against revocation; the lock remains
held through commit. Failures publish no partial folder mutation.

## Navigation and lifecycle

Navigation returns only immediate children and the ancestor chain of the requested
directory. A page contains at most 200 folders (50 by default), ordered by name or
stored creation date with a stable identity tie-breaker. Search is a literal,
case-insensitive substring within the entire directory. The page, its exact matching
total and its ancestors share one database snapshot. Separate page requests are
live views: concurrent changes can shift offset boundaries.

Creation and rename trim names, accept 1..255 Unicode scalar values, and reject
slashes, backslashes and control characters. Conflicting sibling names are refused,
including concurrent creation of the same name. Placement cannot be changed.
A missing or foreign directory filter returns not-found after space authorization.

Deletion removes a selected folder and all its descendants in one transaction.
A document reference anywhere in that subtree refuses the whole operation;
no document, stored file or index is removed. Multiple selected roots are independent
operations, so the UI reports partial success when only some can be deleted.
A mutation waiting behind a committed deletion sees not-found.

## Presentation and content-service boundary

The existing Resources toolbar, rows, breadcrumbs, search, pagination and dialogs
serve manager folders. Account/space navigation isolates pending actions; writes
are not automatically replayed after an unauthorized response. Creation dates are
real, while document-derived sizes use the existing unknown-value placeholder.
Size sorting retains the existing folder fallback to name.

The original document panel opens with sending explicitly unavailable. Upload,
drop, import retry/resume and selected-folder document actions issue no content or
tag mutations in this view. Manager UUIDs never become knowledge-flow tag UUIDs.
The separate knowledge-base consumer retains its existing service bindings.

The document registry has authorized metadata reads and paired name/UUID cursor
pagination, with a default of 50 and maximum of 200. Those metadata pages are not
combined with folder pages or counted in their totals. Statistics and quota retain
their existing service bindings and do not gate folder management.

See the [Resources journey](02-user-journeys.md#priya-opens-resources),
[measured costs](09-quality.md#folder-navigation-and-write-costs) and
[runtime boundary](A1-manager-runtime.md#frontend-resource-browsing).

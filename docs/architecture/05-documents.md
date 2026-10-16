# 5. Documents and knowledge

## Knowledge bases, libraries and content ownership

Manager folders and documents belong to one immutable space. A folder's parent
and a document's folder belong to that same space, enforced by composite SQL foreign
keys. Names are unique within a parent folder; the same name in another folder does
not identify the same content. Listing a space does not include its ancestors' or
descendants' documents. Personal content inherits no organization/team authority.

An admitted caller's unique organization must match the space before OpenFGA
checks `can_read`. A local member or effective editor/analyst reads content; an
admin or organization owner alone does not. Every list request checks current
authority, including direct resource URLs. See [security](03-security.md).

`GET /spaces/{id}/folders` lists direct children of `parent_id`, or root folders
when omitted, ordered by name and id. `GET /spaces/{id}/documents` selects the
same space and `folder_id`, or root documents when omitted. A supplied folder
must exist in the requested space; a missing or foreign filter returns 404 after
space authorization. Empty successful lists represent empty contents.

Documents use the paired `(after_name, after_id)` cursor in name/id order. The
API defaults to 50 and clamps limits to 1..200. The UI requests 51, renders 50 and
uses the extra row only to enable Next. It carries the last rendered document's
cursor, retains cursors for Previous/First, and resets them on folder/space changes.
Folder lists are unpaginated. Cursor pages are live reads, not a snapshot: concurrent
renames can move documents across page boundaries.

## Folder creation

`POST /folders` creates one root folder or one child in its owning space. It checks
current organization and `can_write` under the organization lock and fences the
OpenFGA guard before the SQL insert. A local or inherited editor writes; member,
analyst, administrator and organization owner alone do not. Personal spaces inherit
no authority. The [action/role matrix](03a-action-role-matrix.md) details the scope.

Creation trims the name, accepts 1..255 Unicode scalar values, and rejects slashes,
backslashes and control characters. A root has depth 1; depth 15 is accepted and
16 is refused. Invalid name/depth returns 422, missing parent 404, foreign-space
parent 400 and duplicate sibling name 409. SQL uniqueness also applies at the root;
the same name in another parent is permitted. Concurrent identical creations yield
one folder and one conflict. These validation rules describe creation, not renaming
or rewriting pre-existing rows.

The existing dialog keeps its name and reports localized errors on failure. During
submission it prevents duplicate Enter/click requests and dismissal. A successful
creation refreshes page one of the same location; navigation discards the old
dialog's completion. A 403 disables further submission until the user closes and
refreshes permissions. Creation is not automatically replayed after a 401; after
an uncertain response the user can refresh Resources to inspect the persisted state.

The folder handler makes no Temporal call and belongs to the governance router,
which is constructible without an ingestion client. The full `serve` binary still
connects to Temporal during startup.

## Uploads, connectors and storage

## Ingestion, extraction and indexing

## Retrieval, search scope and citations

## Versioning, deletion and reconciliation

## Implementation references

[Manager content checks, scope and workflow submission](A1-manager-runtime.md#content-access).
The [Resources journey](02-user-journeys.md#priya-browses-her-resources) displays
persisted metadata using the generated manager client and existing explorer.

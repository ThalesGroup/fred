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

## Uploads, connectors and storage

## Ingestion, extraction and indexing

## Retrieval, search scope and citations

## Versioning, deletion and reconciliation

## Implementation references

[Manager content checks, scope and workflow submission](A1-manager-runtime.md#content-access).
The [Resources journey](02-user-journeys.md#priya-browses-her-resources) displays
persisted metadata using the generated manager client and existing explorer.

# 1. Introduction and goals

## Responsibilities

`fred-manager` owns Fred's spaces, folders and documents, and decides who may read,
write or manage them.

| Responsibility | Chapter |
| --- | --- |
| Spaces: organizations, teams, projects, personal spaces | 4, 5 |
| Folders and documents: placement, names, pages | 5 |
| Platform roles and roles on spaces, with the parent rule | 4, 5 |
| One-check content access, and the search scope of a space | 4, 5 |
| Bearer authentication against the Keycloak realm | 6 |
| The one-time root platform admin | 4 |
| Authenticated CLI provisioning of identities, organizations, teams and roles | 4, 7 |
| Submission of ingestion and deletion work to Temporal | 4 |
| Structured stdout logging, request correlation | 6 |

## Quality goals

| Goal | Means |
| --- | --- |
| An access decision costs one OpenFGA check | Rights live on spaces only; the tree is in SQL (D1, D3) |
| Rights stay consistent under concurrency | Check and write under one lock per organization (I4, I5) |
| Governance never implies reading | Admin roles carry no content permission (I8) |
| The design and the code never diverge | Generated blocks, invariants proved by tests (chapter 9) |

## Constraints

- Runs on Fred's shared infrastructure: Postgres database `fred`, Keycloak realm `app`,
  OpenFGA, Temporal.
- Configuration, secrets and log output follow the conventions of Fred's other
  services (chapter 6).

## Vocabulary

| Term | Meaning |
| --- | --- |
| Space | An organization, a team or a project. Holds folders and documents. |
| Personal space | A team with `personal_owner` set: one member, no project. |
| Path | A space's ancestors then itself, as ids. Also its search scope. |
| Role | `member`, `editor`, `analyst` or `admin`, held directly on one space in OpenFGA. |
| Content role | `member`, `editor` or `analyst`: the roles that read content. |
| Platform admin | `admin` on `platform:root`. Governs, reads no content. |
| Folder path | `/<id>/<id>/`: a folder's ancestors then itself. |
| Storage prefix | `<space_id>/<document_id>/`: where a document's artefacts are stored. |

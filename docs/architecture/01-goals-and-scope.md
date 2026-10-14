# 1. Goals and scope

## Goal

Replace the control-plane and knowledge-flow backends by one Rust service,
`fred-manager`, built beside them topic by topic, with no migration in scope. The agents
(`fred-agents`) and the knowledge-flow ingestion workers stay in Python. `fred-manager`
is the UI's interface.

## Ported so far

| Topic | Status | Where |
| --- | --- | --- |
| Spaces: organization, team, project, personal space | built | chapters 4, 5 |
| Folders and documents, placement and pagination | built | chapter 5 |
| Space roles and their parent invariant | built | chapters 4, 5 |
| Content access check and agent search scope | built | chapters 4, 5 |
| Bearer authentication (fred-core `security/oidc.py`) | built | chapter 6 |
| Root platform-admin bootstrap (control-plane) | built | chapter 4 |
| Structured logging (fred-core `logs/`) | built | chapter 6 |
| Ingestion submission to Temporal | client only, no worker | chapter 4 |
| Provisioning bundle import | next | chapter 10 |

Not yet ported: source upload to object storage, search, conversations, agents and
capabilities, teams' product settings, quotas, KPIs, post-authentication admission
gates (chapter 6).

## Vocabulary

| Term | Meaning |
| --- | --- |
| Space | An organization, a team or a project. Holds folders and documents. |
| Personal space | A team with `personal_owner` set: one member, no project. |
| Path | A space's ancestors then itself, as ids. Also the search scope. |
| Role | `member`, `editor` or `admin`, held directly on one space in OpenFGA. |
| Content role | `member` or `editor`: the roles that read content. |
| Platform admin | `admin` on `platform:root`. Governs, reads no content. |
| Folder path | `/<id>/<id>/`: a folder's ancestors then itself, copied into every chunk. |
| Derived artefact | Anything built from a document: markdown, chunks, tables, previews. |

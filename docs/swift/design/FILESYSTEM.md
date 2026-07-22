# Fred Filesystem

## Purpose

Fred exposes one team-scoped virtual filesystem for human file exchange, agent
outputs, Knowledge Flow corpus browsing, and chat download links.

This document describes the **as-built behaviour** of the current implementation.
Future hardening and completion work belongs in the filesystem RFCs, not here.

The product model is deliberately small:

1. **Resources** are read-only corpus content produced by ingestion.
2. **Mon espace** is the current user's private file area inside the current team.
3. **Espace d'equipe** is the team-shared writable area.
4. **Agents** contains files produced or used by each agent instance for the
   current user.

The older `/workspace`, `/agent/<agent-id>`, and `/team/<team-id>` layout is no
longer the current product contract for the Files UI or v2 runtime filesystem.

## User-Facing Roots

For a user working in team `acme`, the Files UI shows:

```text
acme
├── Resources
├── Mon espace
├── Espace d'equipe
└── Agents
```

The UI labels are product names. The backend paths are implementation details.

| UI root | Backend area | Writer |
| --- | --- | --- |
| Resources | `/corpus/...` | ingestion only |
| Mon espace | `/teams/{team}/users/{uid}/...` | the owning user |
| Espace d'equipe | `/teams/{team}/shared/...` | humans with team update permission |
| Agents | `/teams/{team}/agents/{agent_instance_id}/users/{uid}/...` | the running agent for that user, via runtime adapter |
| Agent config assets | `/teams/{team}/agents/{agent_instance_id}/config/...` | read: any team member (chat-time asset fetch); write: team update permission — capability upload slots store their binaries here at agent save (#1903, AGENT-CAPABILITY-RFC §3.4) |

Earlier target notes described a `/teams/{team}/resources/...` path; the current
shipped implementation exposes corpus content through the separate `/corpus/...`
virtual area.

## Virtual Path Layout

The active virtual filesystem has these top-level areas:

```text
/
├── teams/
│   └── {team}/
│       ├── users/{uid}/...
│       ├── shared/...
│       └── agents/{agent_instance_id}/
│           ├── users/{uid}/...
│           └── config/...
└── corpus/
    ├── documents/{document_uid}/preview.md
    └── {library_or_tag}/...
```

Unknown top-level areas are rejected. The filesystem service does not implicitly
map bare paths to `/workspace`.

### `/teams/{team}/users/{uid}`

This is **Mon espace** for one user inside one team.

| Property | Behaviour |
| --- | --- |
| Read | allowed only for the authenticated user whose uid appears in the path |
| Write/delete/mkdir | allowed only for that same user |
| Team gate | caller must have team `CAN_READ` before entering the team box |
| Provenance | files derive as `origin=uploaded`, `producer=human`, `created_by={uid}` |

This area is private per user and per team. Another team member cannot list,
read, or write files under a different uid.

### `/teams/{team}/shared`

This is **Espace d'equipe**.

| Property | Behaviour |
| --- | --- |
| Read | team `CAN_READ` |
| Write/delete/mkdir | team `CAN_UPDATE_RESOURCES` |
| Provenance | direct files derive as `origin=uploaded`, `producer=human`, `created_by=None` |

Agents should not write here through the SDK/runtime filesystem. The current
Knowledge Flow `/fs` boundary itself only sees the authenticated user and team
permissions, so stronger agent-principal enforcement is tracked as hardening
work.

### `/teams/{team}/agents/{agent_instance_id}/users/{uid}`

This is the **Agents** root shown in the UI, grouped by control-plane agent
display name.

| Property | Behaviour |
| --- | --- |
| Read | owning user only |
| Write/delete/mkdir | owning user at Knowledge Flow boundary; running agent is constrained by runtime adapter |
| Agent identity | folder key is `agent_instance_id`, not template agent id |
| UI label | display name, disambiguated when names collide |
| Provenance | files derive as `origin=agent_generated`, `producer=agent:{agent_instance_id}`, `created_by={uid}` |

The v2 runtime adapter maps a bare author path such as `outputs/q3.pptx` to:

```text
teams/{team}/agents/{agent_instance_id}/users/{uid}/outputs/q3.pptx
```

The adapter rejects writes and deletes that resolve outside the current agent's
own subtree, including `shared/...`, another team, another user, or a sibling
agent instance.

### `/corpus`

This is **Resources**.

| Property | Behaviour |
| --- | --- |
| Read | governed by corpus/library permissions |
| Write/delete/mkdir | rejected through filesystem contract |
| Backend | virtual view over document metadata and extracted content |
| Provenance | files derive as `origin=ingested`, `producer=ingestion` |

Stable document reads use:

```text
/corpus/documents/{document_uid}/preview.md
```

Corpus binaries are not served by `/fs/download`; they continue to use the
content/document APIs.

## Access Surfaces

### Files UI

The rework Resources page is the main human surface. It renders:

- Resources through the document/corpus workspace.
- Mon espace through `/fs` under `teams/{team}/users/{uid}`.
- Espace d'equipe through `/fs` under `teams/{team}/shared`.
- Agents through control-plane agent-instance metadata plus `/fs` folders under
  `teams/{team}/agents/{agent_instance_id}/users/{uid}`.

Human users can copy a private file to the team with **Copy to Espace d'equipe**.
The server copies the source into:

```text
teams/{team}/shared/files/{basename}
```

Name collisions receive a deterministic suffix such as `report (2).pptx`.
The original remains in place.

### Knowledge Flow `/fs` HTTP API

Knowledge Flow owns file bytes and virtual filesystem routing. Important routes:

| Route | Purpose |
| --- | --- |
| `GET /fs/list?path=...` | list direct children |
| `GET /fs/stat/{path}` | stat one file or directory |
| `GET /fs/cat/{path}` | read bounded numbered text |
| `GET /fs/page/{path}` | read bounded text with continuation metadata |
| `POST /fs/write/{path}` | write text |
| `POST /fs/upload/{path}` | upload binary multipart content |
| `GET /fs/download/{path}` | download binary content |
| `GET /fs/share/{path}` | create a short-TTL signed download link |
| `POST /fs/copy-to-shared/{path}` | human share-by-copy |
| `POST /fs/edit/{path}` | exact string replacement |
| `POST /fs/mkdir/{path}` | create a directory |
| `DELETE /fs/delete/{path}` | delete a file or directory |
| `GET /fs/glob` / `GET /fs/grep` | discovery/search over visible paths |

The `/fs/cat` and `/fs/page` routes enforce bounded text reads so agents do not
accidentally inline unbounded files into model context.

Errors are mapped consistently:

| Exception | HTTP status |
| --- | --- |
| `ValueError` | `400` |
| `PermissionError` | `403` |
| `FileNotFoundError` | `404` |

### v2 Runtime and SDK

Agent authors normally use `ToolContext` or graph context helpers, not full
virtual paths.

| Helper | Current behaviour |
| --- | --- |
| `ctx.read(path)` / `ctx.read_bytes(path)` | read from the agent author-relative path; `shared/...` reads team shared |
| `ctx.write(path, content)` | write to the running agent's own Agents subtree |
| `ctx.link_for(path)` | create a short-TTL download link for an existing file |
| `ctx.ls(path)` | list through the runtime workspace adapter |
| `ctx.read_user(path)` | read from Mon espace |
| `ctx.read_team(path)` | read from Espace d'equipe |
| `ctx.read_resource(path)` | currently deferred; use search/RAG tools for corpus content |
| `ctx.resolve_template(name)` | authored ToolContext checks Mon espace `templates/{name}` then Espace d'equipe `templates/{name}` |

The runtime forwards requests to Knowledge Flow with the user's access token.
Path construction is done from runtime context: team id, user id, and
`agent_instance_id`.

## Provenance

Provenance is currently path-derived, not stored as separate metadata.

| Path | Derived origin |
| --- | --- |
| `/teams/{team}/users/{uid}/...` | `uploaded` |
| `/teams/{team}/shared/files/...` | `shared_copy` |
| `/teams/{team}/shared/...` | `uploaded` |
| `/teams/{team}/agents/{agent_instance_id}/users/{uid}/...` | `agent_generated` |
| `/corpus/...` | `ingested` |

Knowledge Flow stamps provenance on file-level list/stat responses. Directories
are not stamped. The current SDK `FsEntry` type exposes only `path`, `size`, and
`is_dir`, so provenance is visible to the Files UI but not yet a first-class SDK
listing contract.

## Current Limitations

These are known as-built limits, not hidden design intent:

1. **Signed agent filesystem principal is deferred.** The runtime adapter
   constrains agent paths, but the raw Knowledge Flow `/fs` service does not yet
   validate a signed runtime principal that proves the caller is
   `agent_instance_id`.
2. **Share-copy metadata is path-derived.** `shared_by`, `shared_at`, and source
   provenance preservation are not stored today.
3. **Share-copy suffixing is not atomic.** The service lists existing names and
   then writes the chosen destination.
4. **Large file transfer buffers in memory.** Upload reads the whole multipart
   file and download reads bytes before returning the response.
5. **`read_resource` is deferred.** Corpus raw reads are not exposed through the
   SDK helper yet.
6. **Some SDK/runtime docstrings still describe the old bare-path behaviour.**
   The shipped adapter maps bare writes to Agents, not Mon espace.
7. **Graph runtime template resolution is not fully aligned with ToolContext.**
   The authored `ToolContext` checks Mon espace then Espace d'equipe; graph
   runtime still probes bare `templates/{name}` through `read_bytes`, which now
   means agent space.

## Source Map

| Concern | Source |
| --- | --- |
| Virtual path parsing | `knowledge_flow_backend/features/filesystem/virtual_fs_contract.py` |
| Team/user/shared/agent authorization | `knowledge_flow_backend/features/filesystem/scoped_area_filesystem.py` |
| `/fs` service behaviour | `knowledge_flow_backend/features/filesystem/mcp_fs_service.py` |
| `/fs` HTTP routes | `knowledge_flow_backend/features/filesystem/mcp_fs_controller.py` |
| Runtime path adapter | `fred_runtime/integrations/v2_runtime/adapters.py` |
| Authoring helpers | `fred_sdk/authoring/api.py` |
| SDK port contracts | `fred_sdk/contracts/runtime.py`, `fred_sdk/contracts/context.py` |
| Files UI | `apps/frontend/src/rework/components/pages/TeamResourcesPage/` |

# Fred Filesystem

## Purpose

Fred exposes a **single virtual filesystem** visible to agents, MCP tools, and the platform UI.
The design goal is twofold:

1. **Standard API** — agents (including deep agents built on LangChain/LangGraph) interact with
   Fred FS using the same mental model as a regular POSIX filesystem: `ls`, `read`, `write`,
   `glob`, `grep`, `mkdir`, `delete`. No Fred-specific API knowledge is required.

2. **Permission-shaped visibility** — each user sees only the subtrees they are authorised to
   access. The visible tree is shaped at query time by the ReBAC engine, so an agent can never
   accidentally access another user's files, another team's files, or a corpus it cannot read.

---

## Virtual Path Layout

Every path starts with one of four top-level **areas**:

```
/
├── workspace/          ← user's personal writable space
├── agent/
│   ├── <agent-id>/     ← config files uploaded by admins for one agent
│   └── ...
├── team/
│   ├── <team-id>/      ← shared writable space for a team
│   └── ...
└── corpus/
    ├── <library-tag>/  ← read-only document corpus (ingested documents)
    └── ...
```

Paths without a leading area segment are treated as `/workspace/...` (backward-compatible
default). The legacy prefix `/user/` is also accepted as an alias for `/workspace/`.

---

## Areas in Detail

### `/workspace` — Personal user space

| Property | Value |
|---|---|
| **Who reads** | The authenticated user, agents acting on behalf of that user |
| **Who writes** | The authenticated user, agents acting on behalf of that user |
| **Storage key** | `users/{user_id}/{key}` |
| **Typical use** | Uploaded documents, agent-generated reports, scratch files |

This is the shared exchange zone between user and agent: the user drops a document here,
the agent reads and processes it, and writes a result back that the user can download.

### `/agent/<agent-id>` — Agent configuration space

| Property | Value |
|---|---|
| **Who reads** | Any agent running under `<agent-id>`, admin users |
| **Who writes** | Admin users only (via the UI upload form or REST API) |
| **Storage key** | `agents/{agent_id}/config/{key}` |
| **Typical use** | PowerPoint templates, JSON configuration, reference data files |

This is where admins upload static resources that an agent needs to do its job.
The agent reads them via `ctx.read_resource(key)` (v2 SDK) or
`fetch_config_blob_to_tempfile(key)` (v1 `AgentFlow`).

> **Permission rule**: agents can only read their own config space. An agent running
> under `agent-A` cannot read files from `/agent/agent-B`.

### `/team/<team-id>` — Team shared space

| Property | Value |
|---|---|
| **Who reads** | Team members with `CAN_READ` permission |
| **Who writes** | Team members with `CAN_UPDATE_RESOURCES` permission |
| **Storage key** | `teams/{team_id}/{key}` |
| **Typical use** | Shared reference documents, templates accessible to all team agents |

### `/corpus` — Read-only document corpus

| Property | Value |
|---|---|
| **Who reads** | Users whose teams can access the corresponding document library |
| **Who writes** | Nobody — corpus is **read-only** from the filesystem |
| **Backend** | Virtual — rendered from the document metadata and content store |
| **Typical use** | Browsing ingested documents, reading extracted text for RAG workflows |

The corpus area is not backed by a file store. It is synthesised at query time from the
document metadata service. Each ingested document appears as a virtual folder, with a
`preview.md` child containing the extracted text.

```
/corpus/
└── <library-tag>/
    └── <document-uid>/
        └── preview.md     ← extracted text of the document
```

Writing or deleting under `/corpus` is rejected with a permission error.

---

## Access Surfaces

### 1 — MCP Tools (for agents)

Agents interact with the filesystem via standard MCP tools exposed by the
Knowledge Flow backend. The tools are available to any agent that has
`mcp-knowledge-flow-mcp-text` in its MCP server list.

| Tool | Description |
|---|---|
| `ls(path)` | List direct children of one directory |
| `read_file(path, offset, limit)` | Read one text file with paginated numbered lines |
| `write(path, data)` | Write a text file (creates parent dirs automatically) |
| `edit_file(path, old_string, new_string, replace_all)` | In-place string replacement |
| `delete(path)` | Delete one file or directory |
| `glob(pattern, path)` | Find files matching a glob pattern (e.g. `**/*.md`) |
| `grep(pattern, path)` | Search file contents by regex and return matching paths |
| `stat(path)` | Return metadata (size, type, modified) for one path |
| `mkdir(path)` | Create a directory |

All tools resolve the path through the virtual routing layer and apply ReBAC
permission checks before any storage access. Corpus paths are automatically
routed to the read-only virtual backend; workspace/agent/team paths go to
the writable store.

**Example — deep agent reading a template:**
```python
# Agent lists all .pptx files it can access in its config space
files = await ls(user, f"/agent/{agent_id}")
# reads a specific template
content = await read_file(user, f"/agent/{agent_id}/template_fiche_ref_projet.pptx")
```

**Glob patterns work exactly like a standard filesystem:**
```python
# find all markdown files in the workspace
await glob(user, "**/*.md", path="/workspace")
# find all documents in corpus under a tag
await glob(user, "**/*", path="/corpus/CIR")
```

### 2 — HTTP REST API (for admin UI and direct integration)

The Knowledge Flow backend exposes three scoped storage REST endpoints.
All endpoints require authentication and apply RBAC/ReBAC checks.

**User scope** — `GET/POST/DELETE /knowledge-flow/v1/storage/user/...`

| Method | Path | Description |
|---|---|---|
| `POST` | `/storage/user/upload` | Upload a file to the user's personal space |
| `GET` | `/storage/user` | List files in the user's space |
| `GET` | `/storage/user/{key}` | Download one file |
| `DELETE` | `/storage/user/{key}` | Delete one file |

**Agent config scope** — `GET/POST/DELETE /knowledge-flow/v1/storage/agent-config/{agentId}/...`

| Method | Path | Description |
|---|---|---|
| `POST` | `/storage/agent-config/{agentId}/upload` | Upload a template or config file for one agent |
| `GET` | `/storage/agent-config/{agentId}` | List config files for one agent |
| `GET` | `/storage/agent-config/{agentId}/{key}` | Download one config file |
| `DELETE` | `/storage/agent-config/{agentId}/{key}` | Delete one config file |

**Agent-user scope** — per-user agent memory

| Method | Path | Description |
|---|---|---|
| `POST` | `/storage/agent-user/{agentId}/{userId}/upload` | Upload to the agent's per-user memory |
| `GET` | `/storage/agent-user/{agentId}/{userId}` | List files in per-user agent memory |
| `GET` | `/storage/agent-user/{agentId}/{userId}/{key}` | Download one file |
| `DELETE` | `/storage/agent-user/{agentId}/{userId}/{key}` | Delete one file |

**Uploading a template from the UI:**
The agent edit drawer (visible to admins when editing an existing agent) contains a
drag-and-drop upload form backed by the agent-config endpoints. The uploaded filename
becomes the `key`. For example, uploading `template_fiche_ref_projet.pptx` stores it
under key `template_fiche_ref_projet.pptx` and the agent reads it with
`ctx.read_resource("template_fiche_ref_projet.pptx")`.

### 3 — v2 Authoring SDK (for tool authors)

Inside a `@tool(...)` function, `ToolContext` exposes three high-level helpers that
map directly onto the agent-config and artifact storage areas:

```python
# Read one file from the agent's config space (agents/<agent_id>/config/<key>)
resource: FetchedResource = await ctx.read_resource("template.pptx")
bytes_data = resource.content_bytes

# Publish a file for the user to download (artifact / user-scoped)
artifact: PublishedArtifact = await ctx.publish_bytes(
    file_name="report.pptx",
    content=bytes_data,
    content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
)
# or for text content
artifact = await ctx.publish_text(file_name="summary.md", content="# Summary\n...")

# Return a UI download link part
return ToolOutput(text="Ready.", ui_parts=(artifact.to_link_part(),))
```

These helpers shield tool authors from the underlying path layout.
`read_resource` always reads from the agent's own config space.
`publish_*` writes to the user-scoped artifact store.

---

## Implementation Layers

```
McpFilesystemService          ← single entry point for all MCP tool calls
    │
    ├── resolve_virtual_path  ← maps "/agent/a1/report.md" → (area=AGENT, segments=("a1","report.md"))
    │
    ├── ScopedAreaFilesystem  ← routes workspace / agent / team areas
    │       │                    applies ReBAC permission checks per area
    │       └── WorkspaceFilesystem  ← injects owner namespace, builds full storage key
    │               └── BaseFilesystem   ← MinIO / local disk implementation
    │
    └── CorpusVirtualFilesystem  ← synthesises /corpus from metadata + content store
                                    (read-only, no BaseFilesystem backing)
```

**Key files:**

| File | Responsibility |
|---|---|
| `virtual_fs_contract.py` | Path grammar, area enum, `resolve_virtual_path`, helper builders |
| `mcp_fs_service.py` | Public MCP API: `ls`, `read_file`, `write`, `glob`, `grep`, `edit_file`, `mkdir`, `delete`, `stat` |
| `scoped_area_filesystem.py` | Per-area routing, ReBAC permission enforcement |
| `workspace_filesystem.py` | Namespace injection, sub-prefix listing, `WorkspaceFilesystem` |
| `corpus_virtual_filesystem.py` | Synthetic read-only corpus tree |
| `workspace_storage_controller.py` | HTTP REST endpoints (upload/list/download/delete) |
| `workspace_storage_service.py` | Service layer between controller and `WorkspaceFilesystem` |

---

## Permission Model

| Actor | `/workspace` | `/agent/<id>` | `/team/<id>` | `/corpus` |
|---|---|---|---|---|
| Authenticated user | Full (own files only) | Read if `AgentPermission.READ` | Read if `CAN_READ`, Write if `CAN_UPDATE_RESOURCES` | Read if team has library access |
| Agent (via MCP) | Full on behalf of the calling user | Read own config space | Read/write if user has team permission | Read if user has library access |
| Admin (UI) | — | Upload/list/delete via HTTP API | — | — |

ReBAC gates every read and write call. When ReBAC is disabled (e.g. local dev),
all files are visible to the authenticated user.

The virtual root listing (`ls /`) is **permission-shaped**: `/agent` only appears if
the user can read at least one agent; `/team` only appears if the user belongs to at
least one team; `/corpus` only appears if at least one library is accessible.

---

## Storage Configuration

The physical path patterns are driven by `workspace_layout` in the Knowledge Flow
backend configuration:

```yaml
workspace_layout:
  user_pattern:         "users/{user_id}/{key}"
  agent_config_pattern: "agents/{agent_id}/config/{key}"
  agent_user_pattern:   "agents/{agent_id}/users/{user_id}/{key}"
```

The defaults work for both MinIO (object store) and local filesystem backends.
Override only if your deployment uses a non-standard bucket layout.

---

## Common Patterns

**Agent reads its own config template:**
```python
# v2 tool author
resource = await ctx.read_resource("ppt_template.pptx")
pptx_bytes = resource.content_bytes
```

**Agent writes a result to the user's workspace:**
```python
# via MCP tool in a deep agent
await fs.write(user, "/workspace/output/report.md", markdown_text)
```

**Deep agent discovers all documents in a corpus library:**
```python
files = await fs.glob(user, "**/*", path="/corpus/CIR")
for path in files:
    text = await fs.cat(user, path)
```

**Admin uploads a PowerPoint template for an agent:**
1. Open the Agent Hub → find the agent → click Edit (pencil icon)
2. Scroll to **Resources** section in the edit drawer (admin only)
3. Drag-and-drop the `.pptx` file → Upload
4. The file is now available to the agent under its file name as the key

---

## Developer Notes

- **`/user` is a legacy alias** for `/workspace`. New code should always use `/workspace`.
- **`corpus` is read-only at all times.** Any write or delete call to `/corpus/...` raises a
  permission error regardless of user role.
- **Sub-prefix listing** (`ls /agent/<id>/subdir`) correctly returns direct children of the
  requested directory, not the directory itself. This was a known issue in earlier versions
  where listing a sub-prefix would collapse all files into the sub-folder name.
- **`mkdir` is implicit on write.** `WorkspaceFilesystem.put(...)` creates missing parent
  directories automatically. Explicit `mkdir` calls are only needed when you want to create
  an empty directory.
- **Agent-user memory** (`/storage/agent-user/...`) is not yet exposed through the MCP
  virtual path layout. Agents access it only through the `AgentFlow` v1 API at this stage.

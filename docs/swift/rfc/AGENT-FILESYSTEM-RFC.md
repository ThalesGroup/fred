# RFC: Agent Filesystem — Unified File Model (AGENT-FILESYSTEM)

**Status:** confirmed — implementation started 2026-05-30  
**Author:** Dimitri Tombroff  
**Date:** 2026-05-30  
**ID:** AGENT-FILESYSTEM  
**Backlog:** `docs/swift/backlog/CHAT-UI-BACKLOG.md §4` (CHAT-04 — attachment/upload frontend)  
**Contract impact:** deprecates typed ports in `RUNTIME-EXECUTION-CONTRACT.md §5`;
resolves deferred decision in `CONTROL-PLANE-PRODUCT-CONTRACT.md §3.9`

---

## 1. Problem

File handling in Fred currently has two parallel, diverging stories:

| Story | Mechanism | State |
|---|---|---|
| Agent reads a template | `ResourceFetchRequest` → `FredResourceReader` → workspace API | wired, SDK-typed |
| Agent publishes output | `ArtifactPublishRequest` → `FredArtifactPublisher` → workspace API | wired, SDK-typed |
| Agent explores/lists files | MCP FS tools (`ls`, `glob`, `cat`, …) → `McpFilesystemService` | wired, MCP-exposed |
| User downloads a file | `LinkPart.href` = presigned URL from `PublishedArtifact` | SDK-typed; no UI renderer |
| User uploads a file | ❌ not built | deferred |

The two SDK-typed stories (`ArtifactPublishRequest`, `ResourceFetchRequest`) and the MCP
filesystem story route to **the same storage backend** through different abstraction layers.
The result is two mental models, two callsites, and a growing gap for binary files and
user-facing uploads.

The `McpFilesystemService` — already wired into `knowledge-flow-backend` with rebac,
four virtual areas, and a full set of FS operations — is the right unified model. The
typed ports are a higher-level wrapper around it that adds no value once the FS is
the canonical interface.

Fred MUST NOT take a hard dependency on a specific object-store implementation such as
MinIO, OpenSearch, or any other vendor-specific backend at the contract layer. The
contract is the filesystem path model plus read/write/download primitives; the storage
provider is an implementation detail behind that contract.

This is not just a file-upload cleanup. It is a foundation for Fred's broader
runtime model: if skills are the unit of capability, then every skill should be able
to operate on the same filesystem-shaped substrate without learning a separate file
story for chat, runtime, or control-plane code.

### 1.1 Follow-up clarification — bounded document reads stay on `read_file`

Knowledge Flow already exposes unrestricted full-preview HTTP reads through
`GET /knowledge-flow/v1/markdown/{document_uid}`. That endpoint must remain an
internal backend/UI surface, not an agent-facing tool contract.

Agents read document previews through the filesystem using the existing
`read_file` contract for plain-text compatibility and the new
`read_file_page` contract when they need structured pagination metadata. Both
operate on the existing corpus paths, including the stable UID-oriented path:

```text
/corpus/documents/{document_uid}/preview.md
```

This keeps full-document retrieval internal while exposing a bounded,
paginated document-reading capability to agents.

---

## 2. Existing foundation

`knowledge-flow-backend/knowledge_flow_backend/features/filesystem/mcp_fs_service.py`
already provides:

```
/workspace/          — caller's private files (read/write, no extra permission check)
/agent/{agent_id}/   — agent-scoped files (rebac: AgentPermission.READ / .UPDATE)
/team/{team_id}/     — team-scoped files (rebac: TeamPermission.CAN_READ / .CAN_UPDATE_RESOURCES)
/corpus/             — read-only RAG knowledge base (always read-only)
```

Operations: `ls`, `read_file`, `glob`, `cat`, `write`, `edit_file`, `mkdir`, `delete`,
`grep`, `stat`. All are permission-checked via OpenFGA before touching storage.

`read_file` is the canonical bounded-read surface for text and corpus preview
content. It returns numbered excerpts with server-enforced limits.
`read_file_page` uses the same bounds but returns typed continuation metadata:

- default `limit`: 100 lines
- maximum `limit`: 500 lines
- default `max_chars`: 20,000 characters
- absolute `max_chars`: 50,000 characters

Hardening rules:

- invalid bounds are rejected as client errors instead of surfacing as HTTP 500s
- truncation never drops a partial page boundary; pages contain complete numbered
  lines unless a single line alone exceeds `max_chars`
- in that single-line overflow case, the backend returns one controlled
  truncated line, `returned_lines=1`, `truncated=true`, and `next_offset`
  advanced by one line

This is the filesystem the user described: Unix-style, area-scoped, rebac-enforced.
The only gaps are four concrete missing pieces (§4).

For a skill-based architecture, this matters because a skill should be able to say
"read this template from `/agent/{id}/config`", "write the result to `/workspace`",
and "return a download link" using the same path model that the rest of Fred uses.
That keeps skills composable: they depend on filesystem primitives, not on ad hoc
publish/read wrappers or knowledge of which service owns a particular file flow.

---

## 3. Canonical area layout

```
/workspace/
├── uploads/          ← user-uploaded input files (file picker → POST upload endpoint)
└── <user-chosen>/    ← agent-generated outputs the agent writes here

/agent/{agent_id}/
└── config/           ← admin-uploaded templates and agent configuration
                        (agents: read-only via ResourceFetchRequest today → cat after this RFC)

/team/{team_id}/      ← files shared across the team

/corpus/              ← read-only RAG knowledge (unchanged)
```

**Folder conventions replace the `ArtifactScope` enum.** The path is the contract:

### 3.1 Who exchanges data with whom

| Actor | What they do | Path / transport |
|---|---|---|
| User | Uploads an input file for the current session | `POST /knowledge-flow/v1/storage/user/upload` → `/workspace/uploads/...` |
| Team admin | Seeds shared files or agent templates before execution | write to `/team/{team_id}/...` or `/agent/{agent_id}/config/...` |
| Agent | Reads inputs, writes outputs, and returns a downloadable result | `read_bytes` / `write_bytes` / `get_download_url` on filesystem paths |
| UI | Shows the result to the user | `LinkPart` with a download URL |

Rule of thumb: users and admins place files into the filesystem; agents consume and produce files inside the same filesystem; the chat UI only displays the final download link.

If a user wants to give an agent a file, the file lands in `/workspace/uploads/...` and the agent reads that path.
If a team admin wants to prepare a template or shared asset, it lands in `/agent/{id}/config/...` or `/team/{team_id}/...`.
The agent never needs a separate upload protocol beyond the path it is given.
---

## 4. Four gaps to close

### 4.1 Binary read/write on the MCP FS service

`McpFilesystemService.write(path, data: str)` and `cat(path) → str` are text-only.
Binary files (PPTX, PDF, images) must be handled.

Add to `McpFilesystemService`:
- `write_bytes(user, path, data: bytes, *, content_type: str)` — store a binary object
- `read_bytes(user, path) → bytes` — retrieve raw bytes

These route to the same `WorkspaceFilesystem` / storage backend that text operations use.

### 4.2 `get_download_url(path) → str` on the MCP FS service

An agent that writes a file for the user to download must be able to produce a
short-lived presigned URL for that path.

Add to `McpFilesystemService`:
- `get_download_url(user, path, *, expires_minutes: int = 60) → str`

The URL is signed by the storage backend's signed-URL implementation (for example,
MinIO, GCS, or another S3-compatible/object-store backend). This is a storage-layer
capability, not a MinIO-specific contract. The agent embeds this URL in a `LinkPart`
and returns it in `ui_parts`.

### 4.3 User upload HTTP endpoint

This endpoint **already exists** in `knowledge-flow-backend`:

```
POST /knowledge-flow/v1/storage/user/upload
  Content-Type: multipart/form-data
  Body: UploadFile (file field)
  → places file in the caller's workspace storage
  → returns { download_url, key, file_name, size, … }
```

All configs set `base_url: "/knowledge-flow/v1"` — this is the canonical prefix for all
KF HTTP routes. No new endpoint is needed. Gap 4.3 is therefore a **frontend integration
task only**: wire the chat file picker to call
`POST /knowledge-flow/v1/storage/user/upload` and pass the returned key to the agent
as part of the message context.

**Delegated writes (agent writes on behalf of a specific user):** the existing
`POST /knowledge-flow/v1/storage/agent-user/{agent_id}/{target_user_id}/upload`
endpoint already handles this case. When an agent needs to place a file in a
specific user's workspace (e.g., a report for `user-X`), it uses this route.
This preserves the `target_user_id` intent that the `ArtifactScope.AGENT_USER`
typed path carried — the path convention replaces the enum, but the HTTP route
that enforces identity isolation is unchanged.

This resolves the deferred decision in `CONTROL-PLANE-PRODUCT-CONTRACT §3.9`:
the upload routes directly to knowledge-flow-backend (the owner of the filesystem),
not through the control-plane.

That ownership boundary is deliberate: keeping file storage local to the filesystem
service makes the eventual skill layer much simpler, because skills can depend on one
path-based file contract instead of a separate control-plane file API.

### 4.4 `LinkPart` download renderer in the chat UI

`useChatSse.ts` already injects `ui_parts` into `ChatMessage.parts`. Nothing renders them.

Add to the rework chat UI:
- A `DownloadLinkBadge` atom (small chip with file icon, filename, size if known)
- `AssistantTurn` renders `LinkPart` entries from message parts below the message bubble

`LinkPart` stays as the UI-facing transport — it is already correct. Only the renderer
is missing.

### 4.5 Bounded corpus document reading

When the runtime context already contains `selected_document_uids`, the agent
should not be forced to rediscover the document through search before reading.
The preferred direct-read flow is:

1. Resolve the selected document UID to `/corpus/documents/{document_uid}/preview.md`
2. Read it through `read_file(path, offset, limit, max_chars)`
3. Continue with additional paginated reads only as needed

This preserves the "extend, do not duplicate" rule:

- no new `read_document` operation
- no direct agent exposure of `/markdown/{document_uid}`
- no duplicate content-loading logic outside `ContentService` and the corpus VFS

---

## 5. Agent workflow end-to-end (PPTX example)

```
1. Admin uploads template to /agent/{id}/config/template.pptx
   (via a future admin UI or direct MinIO write — existing storage, no code change)

2. Agent: bytes = await fs.read_bytes("/agent/{id}/config/template.pptx")
   (gap 4.1 — new method)

3. Agent: filled = fill_template(bytes, data)

4. Agent: await fs.write_bytes("/workspace/report.pptx", filled, content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
   (gap 4.1 — new method)

5. Agent: url = await fs.get_download_url("/workspace/report.pptx", expires_minutes=60)
   (gap 4.2 — new method)

6. Agent: return AgentResult(ui_parts=(LinkPart(href=url, title="Download report.pptx", kind=LinkKind.download),))

7. UI: renders DownloadLinkBadge  →  user clicks  →  browser downloads file
   (gap 4.4 — new component)
```

Steps 2–5 are direct FS calls. No `ArtifactPublishRequest`, no workspace API detour.

---

## 6. What gets deprecated / removed

Once all four gaps are closed and agents migrate to direct FS calls:

| What | Location | Replacement |
|---|---|---|
| `ArtifactPublishRequest` | `fred-sdk/contracts/context.py` | `fs.write_bytes` + `fs.get_download_url` |
| `PublishedArtifact` | `fred-sdk/contracts/context.py` | `LinkPart` built inline |
| `ResourceFetchRequest` | `fred-sdk/contracts/context.py` | `fs.read_bytes` / `fs.cat` |
| `FetchedResource` | `fred-sdk/contracts/context.py` | raw bytes / str |
| `ArtifactScope` | `fred-sdk/contracts/context.py` | folder path convention |
| `ResourceScope` | `fred-sdk/contracts/context.py` | folder path convention |
| `ArtifactPublisherPort` | `fred-sdk/contracts/runtime.py` | removed from `RuntimeServices` |
| `ResourceReaderPort` | `fred-sdk/contracts/runtime.py` | removed from `RuntimeServices` |
| `FredArtifactPublisher` | `fred-runtime/integrations/v2_runtime/adapters.py` | deleted |
| `FredResourceReader` | `fred-runtime/integrations/v2_runtime/adapters.py` | deleted |

**Nothing that the frontend or the SSE protocol uses is removed.** `LinkPart`, `GeoPart`,
`UiPart`, and the `ui_parts` field on `final`/`tool_result` events are unchanged.

---

## 7. Impact on existing contracts

### 7.1 `RUNTIME-EXECUTION-CONTRACT.md §5`

The `ArtifactPublisherPort` and `ResourceReaderPort` entries in `RuntimeServices` are
deprecated. A dated note is added there (see amendment). The `UiPart` / `LinkPart`
section is unchanged.

### 7.2 `CONTROL-PLANE-PRODUCT-CONTRACT.md §3.9`

The deferred binary upload routing decision is resolved: uploads go directly to
`knowledge-flow-backend` via the existing `POST /knowledge-flow/v1/storage/user/upload`
endpoint. The control-plane does not proxy binary content. The section is updated to
reflect this decision.

### 7.3 `fred-sdk` simplification

Removal of 8 types and 2 port interfaces from `fred-sdk/contracts/context.py` and
`fred-sdk/contracts/runtime.py`. This is the largest simplification impact:
agents that currently use `ArtifactPublishRequest` in `react_tool_resolution.py`
switch to direct FS calls instead of going through the port abstraction.

---

## 8. Alternatives considered

### 8.1 Keep both stories, add binary to the typed ports

Extend `ArtifactPublishRequest` with a binary path and keep the existing abstraction.
**Rejected:** adds complexity without removing the duplicate story. The typed port
was built before `McpFilesystemService` reached its current maturity; there is no
longer a reason to maintain both.

### 8.2 Use the typed ports as a thin wrapper over the FS

Keep `ArtifactPublishRequest` but have `FredArtifactPublisher.publish()` call
`fs.write_bytes` + `fs.get_download_url` internally.
**Rejected:** the wrapper adds zero value — agents can call the FS directly and the
extra layer makes tracing and testing harder. Keeping a wrapper to protect agent
authors from two function calls is not a valid trade-off.

---

## 9. Files touched

| File | Change |
|---|---|
| `knowledge-flow-backend/.../mcp_fs_service.py` | Add `write_bytes`, `read_bytes`, `get_download_url` |
| `knowledge-flow-backend/.../workspace_storage_controller.py` | No change — `POST /knowledge-flow/v1/storage/user/upload` already exists |
| `apps/frontend/src/rework/.../DownloadLinkBadge/` | New atom — download chip |
| `apps/frontend/src/rework/.../AssistantTurn/AssistantTurn.tsx` | Render `LinkPart` entries from parts |
| `libs/fred-sdk/fred_sdk/contracts/context.py` | Deprecate 8 types (remove after migration) |
| `libs/fred-sdk/fred_sdk/contracts/runtime.py` | Deprecate 2 ports (remove after migration) |
| `libs/fred-runtime/fred_runtime/integrations/v2_runtime/adapters.py` | Remove `FredArtifactPublisher`, `FredResourceReader` after migration |
| `libs/fred-runtime/fred_runtime/react/react_tool_resolution.py` | Migrate artifact calls to direct FS calls |
| `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` | Dated deprecation note §5 |
| `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` | Resolve §3.9 deferred decision |

---

## 10. Deprecation migration phases

Three phases ensure no agent breaks during the transition.

| Phase | Gate | What changes | Typed ports |
|---|---|---|---|
| **P1 — coexist** | gaps 4.1 and 4.2 closed in KF backend | `write_bytes`, `read_bytes`, `get_download_url` added to `McpFilesystemService`. SDK deprecation warnings added (not removed). Both call paths work. | Still present and functional |
| **P2 — migrate** | P1 merged + all active agents switched to FS calls | `react_tool_resolution.py` migrated. `FredArtifactPublisher` and `FredResourceReader` no longer called. Integration tests run both paths to confirm parity. | Deprecated, no callers |
| **P3 — remove** | P2 merged + 2-week soak on main, no regressions | 8 SDK types and 2 port interfaces deleted. `FredArtifactPublisher` and `FredResourceReader` deleted. `RUNTIME-EXECUTION-CONTRACT.md §5` updated to reflect removal. | Deleted |

**No cross-phase wrappers.** P1 deprecates; P2 migrates all callers; P3 deletes. There is no intermediate re-export or shim layer.

**Removal gate for P3:** `git grep -r "ArtifactPublishRequest\|ResourceFetchRequest\|ArtifactPublisherPort\|ResourceReaderPort"` returns zero hits in `apps/` and `libs/`.

---

## 11. Acceptance criteria

- [ ] Agent can read a binary file from `/agent/{id}/config/` and write output to `/workspace/`
- [ ] Agent can produce a presigned download URL for a file it just wrote
- [ ] The URL is returned as `LinkPart` in `ui_parts` and reaches the frontend via SSE
- [ ] Chat UI renders a `DownloadLinkBadge` below the assistant message for each `LinkPart` with `kind=download`
- [ ] User can upload a file through the chat UI file picker; it lands at `/workspace/uploads/{filename}`
- [ ] Agent can read the uploaded binary file via `fs.read_bytes("/workspace/uploads/{filename}")`
- [ ] `ArtifactPublishRequest` and `ResourceFetchRequest` are gone from active agent code
- [ ] No SSE protocol change — `ui_parts`, `LinkPart`, `GeoPart` are untouched
- [ ] `tsc --noEmit` passes; `make code-quality` passes for all touched packages

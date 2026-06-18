# RFC: Agent Filesystem — MCP Filesystem First

**Status:** confirmed — MCP-first target refreshed 2026-06-18
**Author:** Dimitri Tombroff
**Date:** 2026-05-30
**Last updated:** 2026-06-18
**ID:** AGENT-FILESYSTEM
**Tracked item:** `FILES-01`
**Backlog:** `docs/swift/backlog/CHAT-UI-BACKLOG.md §4.5`
**Contract impact:** breaking SDK/runtime simplification allowed; no legacy generated-content migration

---

## 1. Decision

Fred's agent file exchange contract is the Knowledge Flow MCP filesystem.

For a fresh Swift install, there is no backward-compatibility requirement for old
conversation history, generated artifacts, or previous runtime file abstractions. The
migration imports only durable product configuration: agents, prompts, users, teams,
and the metadata required to make those entities usable in Swift.

Generated content produced before this cutover is not migrated into the new file model.
That lets the platform remove the duplicate artifact/resource story instead of carrying
it indefinitely.

The target model is:

- users, admins, agents, and graph nodes exchange files through the same virtual
  filesystem paths
- the runtime exposes the Knowledge Flow filesystem to agents through MCP
- `fred-sdk` provides ergonomic helpers over that MCP filesystem, not a second storage
  abstraction
- generated files are stored by Knowledge Flow and returned to chat as typed `LinkPart`
  download references
- the frontend renders and replays those `LinkPart` values from typed message parts

---

## 2. Problem

Fred currently has two overlapping file stories.

| Story | Current mechanism | State |
| --- | --- | --- |
| User uploads an input file | `POST /knowledge-flow/v1/storage/user/upload` | shipped through CHAT-04 |
| Agent explores files | Knowledge Flow MCP FS (`ls`, `read_file`, `glob`, etc.) | wired for text workflows |
| Agent reads a configured template | `ResourceFetchRequest` -> `FredResourceReader` -> Knowledge Flow storage | wired but separate |
| Agent publishes output | `ArtifactPublishRequest` -> `FredArtifactPublisher` -> Knowledge Flow storage | wired but separate |
| UI receives download links | `LinkPart` in `ui_parts` | live SSE path exists, history/rendering incomplete |

The duplicate SDK/runtime ports were useful while the filesystem service was still
immature. They are now the confusing part: an agent author has to know when a file is a
resource, when it is an artifact, when it is an MCP path, and which scope enum maps to
which backing location.

The product experience we want is simpler:

1. a user uploads inputs into a workspace path;
2. a team admin places shared templates into a team or agent path;
3. an agent reads those paths, writes an output path, and asks for a safe download link;
4. chat renders the returned `LinkPart`;
5. all bytes stay behind Fred/Knowledge Flow auth and storage policy.

---

## 3. Target Contract

### 3.1 Canonical filesystem layout

```
/workspace/
├── uploads/          # user-uploaded input files
└── outputs/          # default user-visible generated outputs

/agent/{agent_id}/
└── config/           # admin-managed agent templates and configuration files

/team/{team_id}/      # team-shared templates and files

/corpus/              # read-only RAG corpus views
```

The path is the product contract. Storage routes, object-store keys, buckets, and signed
URL mechanics are implementation details.

### 3.2 Required filesystem capabilities

The Knowledge Flow MCP filesystem must be the authoritative surface for:

- `list`, `stat`, `mkdir`, `delete`, `move`
- `glob`, `grep`, bounded text reads, and paginated reads
- text writes and edits
- binary reads and writes for files such as PPTX, PDF, images, spreadsheets, and archives
- metadata-preserving writes: file name, MIME type, byte size, path, updated timestamp
- safe download links returned as `LinkPart`-compatible metadata

Binary operations may be implemented as MCP tools that carry base64 payloads or as MCP
resources with binary `blob` content. The implementation choice belongs to Knowledge
Flow, but the SDK-facing API must expose ordinary `bytes`.

### 3.3 Access and safety

All operations are authorized before storage access:

- `/workspace/...` is scoped to the current user/workspace
- `/agent/{agent_id}/...` is scoped through agent permissions
- `/team/{team_id}/...` is scoped through team permissions
- `/corpus/...` is read-only

Download links are Fred/Knowledge Flow API links, not raw bucket credentials. They must
remain protected by the normal bearer-token and authorization path unless a future RFC
explicitly introduces anonymous or externally shared links.

---

## 4. SDK Target

`fred-sdk` exposes one agent authoring model:

```python
template = await ctx.fs.read_bytes("/agent/{agent_id}/config/templates/report.pptx")
output = build_deck(template, data)

link = await ctx.fs.write_download(
    "/workspace/outputs/generated-report.pptx",
    output,
    content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    label="Download generated-report.pptx",
)

return ToolOutput(text="Slides ready.", ui_parts=(link,))
```

Graph nodes use the same concept:

```python
template = await context.fs.read_bytes("/team/{team_id}/templates/report.pptx")
await context.fs.write_bytes(
    "/workspace/outputs/generated-report.pptx",
    output_bytes,
    content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
)
link = await context.fs.link("/workspace/outputs/generated-report.pptx")
return GraphExecutionOutput(content="Slides ready.", ui_parts=(link,))
```

Target SDK API:

- `ctx.fs.read_text(path, *, offset=None, limit=None, max_chars=None)`
- `ctx.fs.read_bytes(path)`
- `ctx.fs.write_text(path, content, *, content_type="text/plain")`
- `ctx.fs.write_bytes(path, content, *, content_type, metadata=None)`
- `ctx.fs.link(path, *, label=None, expires_in=None) -> LinkPart`
- `ctx.fs.write_download(path, content, *, content_type, label=None) -> LinkPart`
- graph equivalents on `context.fs`

`LinkPart`, `UiPart`, and SSE `ui_parts` remain the UI transport. The SDK removes or
stops exposing the old file abstraction layer:

- `ArtifactPublishRequest`
- `PublishedArtifact`
- `ResourceFetchRequest`
- `FetchedResource`
- `ArtifactScope`
- `ResourceScope`
- `ArtifactPublisherPort`
- `ResourceReaderPort`

This is intentionally breaking. Fresh Swift installs do not need compatibility shims for
old generated content or historical conversations.

---

## 5. Runtime Target

`fred-runtime` connects file-capable agents to the Knowledge Flow filesystem MCP server.

Runtime responsibilities:

- include the Knowledge Flow filesystem MCP server for agents that require file exchange
- provide the authenticated user/team/agent execution identity to that MCP server
- expose the MCP filesystem tools to ReAct agents
- expose the same capability to graph nodes through SDK `context.fs`
- persist `ui_parts` from final/tool-result events into session history
- replay typed `LinkPart` values through `messages_url_template`

Runtime removes the duplicate file services once SDK callers have moved:

- `FredArtifactPublisher`
- `FredResourceReader`
- `RuntimeServices.artifact_publisher`
- `RuntimeServices.resource_reader`

The runtime should not proxy raw file bytes through control-plane. Control-plane remains
the owner of sessions, teams, agent instances, and product metadata; Knowledge Flow owns
files, vectors, previews, and storage cleanup.

---

## 6. Knowledge Flow Backing Implementation

Knowledge Flow remains the backing implementation.

Current foundation:

- `WorkspaceFilesystem` over `fred_core.filesystem.BaseFilesystem`
- local filesystem or S3-compatible object storage depending on deployment config
- existing user upload endpoint used by CHAT-04
- existing MCP virtual filesystem with workspace, agent, team, and corpus roots
- ReBAC checks before protected areas are read or mutated

Required additions/hardening:

- binary read/write support through MCP
- download-link generation through MCP
- consistent metadata for text and binary files
- path normalization and traversal protection across all roots
- offline tests for local filesystem behavior
- adapter tests with mocked object storage or mocked filesystem boundary

Fred must not expose MinIO/S3/GCS implementation details in the SDK, runtime, frontend,
or agent authoring contract.

---

## 7. End-To-End Slide Flow

Recommended target flow for generated slides:

```
1. Admin uploads template:
   /team/{team_id}/templates/company-report.pptx
   or
   /agent/{agent_id}/config/templates/company-report.pptx

2. Agent reads template:
   template = await ctx.fs.read_bytes("/team/{team_id}/templates/company-report.pptx")

3. Agent generates PPTX bytes:
   output_bytes = build_deck(template, data)

4. Agent writes output:
   await ctx.fs.write_bytes(
       "/workspace/outputs/generated-report.pptx",
       output_bytes,
       content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
   )

5. Agent gets a download link:
   link = await ctx.fs.link(
       "/workspace/outputs/generated-report.pptx",
       label="Download generated-report.pptx",
   )

6. Agent returns typed UI:
   return ToolOutput(text="Slides ready.", ui_parts=(link,))

7. UI renders:
   DownloadLinkBadge(link)
```

No slide-specific storage API is needed. Slides are binary files in the filesystem.

---

## 8. Migration Rule

The Swift migration/import path keeps:

- users
- teams
- agent definitions
- agent prompts and configuration needed to recreate current agents
- team/agent metadata needed for permissions and routing

The Swift migration/import path does not keep:

- old chat conversations
- generated artifacts from old conversations
- historical download links
- old artifact/resource keys
- compatibility aliases for previous generated-content paths

If a business template is still needed, it should be imported as a new Swift filesystem
file under `/team/{team_id}/...` or `/agent/{agent_id}/config/...`.

---

## 9. Development Plan

### 9.1 FILES-01.A — Knowledge Flow MCP FS hardening

- [ ] Add binary read/write support to the Knowledge Flow MCP filesystem.
- [ ] Add `link(path)` / download-reference generation to the MCP filesystem.
- [ ] Return stable metadata: path, name, MIME type, size, updated timestamp, and href
      when applicable.
- [ ] Add path traversal, authorization, and read-only corpus tests.
- [ ] Add local-backend and mocked-object-storage tests.

### 9.2 FILES-01.B — SDK filesystem helpers

- [ ] Add `ctx.fs` and graph `context.fs` helper APIs over MCP.
- [ ] Make helper calls return Python `str`, `bytes`, metadata objects, and `LinkPart`
      without exposing MCP transport details.
- [ ] Remove or stop exporting the old artifact/resource request and port contracts.
- [ ] Update SDK authoring docs and examples to use filesystem paths.

### 9.3 FILES-01.C — Runtime MCP integration

- [ ] Ensure file-capable agents declare or receive the Knowledge Flow filesystem MCP server.
- [ ] Route ReAct filesystem tool calls through the MCP tool catalog.
- [ ] Route graph `context.fs` helper calls through the same authenticated MCP capability.
- [ ] Remove `FredArtifactPublisher` and `FredResourceReader` after callers migrate.
- [ ] Add runtime tests proving execution identity is propagated to filesystem calls.

### 9.4 FILES-01.D — LinkPart rendering and replay

- [ ] Render `LinkPart(kind="download")` entries in `AssistantTurn` with
      `DownloadLinkBadge`.
- [ ] Preserve `ui_parts` in runtime history so live SSE and history reload show the
      same links.
- [ ] Add frontend tests for live and history-loaded download links.
- [ ] Add runtime history tests for persisted `ui_parts`.

### 9.5 FILES-01.E — Minimal slide-template validation

- [ ] Add a fixture-backed validation agent or graph step that reads a PPTX template,
      writes a trivial generated PPTX, and returns a download `LinkPart`.
- [ ] Keep the happy path deterministic and no-LLM.
- [ ] Use the official PPTX MIME type:
      `application/vnd.openxmlformats-officedocument.presentationml.presentation`.

---

## 10. Acceptance Criteria

- [ ] Agent authors can use `ctx.fs` for text, binary, and download-link workflows.
- [ ] Graph nodes can use `context.fs` for the same workflows.
- [ ] ReAct agents can call Knowledge Flow filesystem MCP tools directly when needed.
- [ ] A PPTX template can be read from `/team/{team_id}/...` or
      `/agent/{agent_id}/config/...`.
- [ ] A generated PPTX can be written to `/workspace/outputs/...`.
- [ ] The generated PPTX returns a safe Fred/Knowledge Flow download link as `LinkPart`.
- [ ] Managed chat renders the link during live SSE and after history reload.
- [ ] Runtime and Knowledge Flow tests cover auth, binary bytes, metadata, and link replay.
- [ ] Old artifact/resource SDK/runtime ports are removed or no longer exported.
- [ ] No raw object-store URL, bucket name, or credential becomes the product contract.

---

## 11. Alternatives Considered

### 11.1 Keep the typed artifact/resource ports as compatibility shims

Rejected. The target deployment is a fresh Swift install. Keeping shims would preserve
the confusing dual model and slow down the implementation without preserving anything
the migration needs.

### 11.2 Add a slide-specific storage API

Rejected. Slides are binary files. A slide-specific API would duplicate the generic
filesystem contract and make PDFs, spreadsheets, images, and archives second-class.

### 11.3 Return raw S3 presigned URLs directly to agents and browsers

Rejected as the platform contract. Storage providers are an implementation detail.
Agents and browsers should see Fred/Knowledge Flow paths and safe `LinkPart` links.

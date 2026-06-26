# RFC: Agent Filesystem Hardening and Completion

**Status:** proposed follow-up; no implementation approved by this RFC alone
**Author:** Dimitri Tombroff
**Date:** 2026-06-26
**ID:** AGENT-FILESYSTEM-HARDENING
**Tracked items:** `FILES-04`, `FILES-05`; linked security dependency `RUNTIME-07`
**Related docs:** `docs/swift/design/FILESYSTEM.md`, `docs/swift/rfc/EXECUTION-GRANT-SECURITY-HARDENING-RFC.md`

---

## 1. Problem

The agent filesystem is now largely implemented. The previous broad target RFC was
removed so the current knowledge lives in two places only:

1. `docs/swift/design/FILESYSTEM.md` for as-built behaviour;
2. this RFC for fixes and completion work.

This split avoids keeping old `/workspace`, `/agent/<agent-id>`, and broad target
material around as competing implementation guidance.

The main architectural gap is that agent isolation is currently enforced by the v2 runtime
adapter, while the raw Knowledge Flow `/fs` boundary still sees a normal user token and
team ReBAC. That is acceptable for a trusted first-party runtime path, but it is not the
final security model for classified or multi-tenant deployments.

## 2. Current as-built baseline

The shipped product model is:

```text
/corpus/...                                                  # Resources, read-only
/teams/{team}/users/{uid}/...                                # Mon espace
/teams/{team}/shared/...                                     # Espace d'equipe
/teams/{team}/agents/{agent_instance_id}/users/{uid}/...     # Agents
```

The v2 runtime adapter maps bare agent writes to the current agent instance's own
`agents/{agent_instance_id}/users/{uid}` subtree and rejects writes outside that subtree.
Knowledge Flow enforces team `CAN_READ`, team `CAN_UPDATE_RESOURCES` for `shared/` writes,
and uid ownership for `users/{uid}` and `agents/{agent}/users/{uid}`.

Provenance is path-derived. Share-by-copy exists and writes into
`teams/{team}/shared/files/{basename}` with a deterministic suffix on name collisions.

## 3. Findings

### F1 - Raw `/fs` does not validate a signed agent filesystem principal

Runtime SDK isolation is implemented, but Knowledge Flow receives only a
`KeycloakUser`. It cannot know whether a write to:

```text
/teams/{team}/agents/{agent_instance_id}/users/{uid}/...
```

was made by the matching runtime agent instance or by another first-party caller using
the user's bearer token. It also cannot distinguish a human caller from an agent caller
for `shared/` writes. This is the deferred G1b gap from FILES-04.

### F2 - The filesystem principal depends on ExecutionGrant hardening

The filesystem should not invent a parallel identity system. The correct source of agent
identity is the managed execution grant and runtime context. This RFC therefore depends
on `RUNTIME-07` for a signed grant and runtime-verifiable execution scope.

### F3 - SDK and runtime docs still describe stale bare-path semantics

Several docstrings and contracts still say a bare path is the acting user's private
space or that `shared/` can be used to write to the team. Current runtime behaviour is
different:

- bare write -> current agent's Agents subtree;
- `shared/...` -> readable team shared path;
- write/delete to `shared/...` -> rejected by runtime adapter.

This is documentation drift that can mislead agent authors.

### F4 - Graph runtime template resolution is not aligned with ToolContext

`ToolContext.resolve_template(name)` checks:

1. Mon espace `templates/{name}`;
2. Espace d'equipe `templates/{name}`.

Graph runtime still checks `templates/{name}` through `read_bytes`, which now resolves to
the agent's own Agents subtree, then `shared/templates/{name}`. This is probably an
incomplete migration.

### F5 - `read_resource` is a surface placeholder

`ctx.read_resource(path)` exists for the desired Resources/corpus helper, but currently
raises `NotImplementedError`. Agents must use search/RAG tools for corpus content.

### F6 - Share-copy provenance is incomplete

The current implementation derives `shared_copy` from the destination path
`shared/files/...`. It does not persist:

- original source path;
- original origin/producer;
- `shared_by`;
- `shared_at`.

Earlier target notes claimed those fields would be added; the implementation does not
yet do that.

### F7 - Share-copy no-clobber is not atomic

The service lists existing names, chooses a suffix, then writes. Concurrent copies of the
same filename can race and select the same destination.

### F8 - Large file transfer buffers in memory

`/fs/upload` reads the whole multipart file before writing. `/fs/download` reads all bytes
and returns `Response(content=data)`. This is acceptable for current templates/decks but
not for large files.

### F9 - Browser path encoding is weaker than runtime path encoding

The runtime client percent-encodes reserved path characters while preserving `/`.
The Files UI uses `encodeURI(...)` in some `/fs/download` and copy-to-shared paths.
Filenames containing `#` or `?` may be interpreted as fragments or query delimiters.

### F10 - SDK `FsEntry` does not expose provenance

Knowledge Flow stamps provenance on file list/stat responses. The SDK `FsEntry` model
currently exposes only `path`, `size`, and `is_dir`, so SDK authors cannot see the same
origin signal the UI shows.

## 4. Proposed work packages

### P1 - Signed workspace principal at the `/fs` boundary

Introduce a narrow runtime-to-Knowledge-Flow workspace principal derived from the signed
execution grant:

```text
actor_type = "agent" | "human"
team_id
user_id
agent_instance_id   # required when actor_type = agent
grant_id / jti
expires_at
signature
```

Knowledge Flow uses it only for filesystem authorization. It must not replace normal
Keycloak authentication; it adds the missing actor scope.

Rules:

- agent writes are allowed only under
  `/teams/{team}/agents/{agent_instance_id}/users/{user_id}/...`;
- agent delete follows the same rule;
- agent reads may include its own agent space and allowed team/user helper reads;
- agent writes to `/teams/{team}/shared/...` are rejected even if the user has
  `CAN_UPDATE_RESOURCES`;
- human calls keep the existing ReBAC behaviour.

This should be implemented after or alongside `RUNTIME-07`, not as an independent signing
scheme.

### P2 - Align SDK, graph runtime, and docs with shipped path semantics

Update the SDK/runtime documentation and helper implementations so they say and do the
same thing:

- bare `write` means agent output;
- explicit `read_user` means Mon espace;
- explicit `read_team` means Espace d'equipe;
- graph `resolve_template` should match `ToolContext.resolve_template` unless a separate
  agent-space template override is deliberately desired and documented.

### P3 - Complete share-copy metadata or document it as intentionally lightweight

Choose one of two paths:

1. Keep path-derived share-copy provenance only and amend the broad RFC accordingly.
2. Add stored metadata for `source_path`, `source_origin`, `shared_by`, and `shared_at`.

If metadata is added, list/stat should merge stored metadata with path-derived defaults.

### P4 - Atomic no-clobber copy

Replace list-then-write suffix selection with backend-supported conditional creation when
available, or a small retry loop that detects destination conflicts and re-suffixes.

### P5 - Large-file transfer decision

Resolve FILES-05 with one of:

- true streaming proxy through Knowledge Flow;
- hybrid presigned URLs for S3/GCS-style backends plus streaming fallback;
- explicit size caps until streaming lands.

### P6 - Browser path encoding hardening

Adopt a shared frontend helper equivalent to the runtime client's path encoding:

```text
encode each segment with encodeURIComponent, then join with "/"
```

Use it for download, upload, delete, mkdir, share, and copy-to-shared route paths.

### P7 - SDK provenance exposure

If provenance is an author-facing feature, extend `FsEntry` and runtime parsing to expose:

```text
origin
producer
created_by
modified
```

If provenance remains UI-only, keep `docs/swift/design/FILESYSTEM.md` explicit that this
is a UI/KF response signal, not an SDK listing contract.

## 5. Recommended sequencing

1. **P2 + P6 first.** Low risk, fixes misleading contracts and path buglets.
2. **P1 with RUNTIME-07.** This is the security-critical boundary.
3. **P5.** Decide streaming/presigned before large deployments rely on `/fs`.
4. **P3 + P4.** Share-copy metadata and atomicity are correctness polish.
5. **P7.** Decide whether SDK provenance is product surface or UI-only.

## 6. Contract impact

- `docs/swift/design/FILESYSTEM.md`: already rewritten as the as-built source.
- `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`: update if workspace principal fields
  become part of runtime execution context or grant validation.
- `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`: update if prepare-execution mints
  a workspace-scoped principal or token.
- `fred-sdk` contracts: update `WorkspaceFsPort` docstrings and optionally `FsEntry`.
- `knowledge-flow-backend` OpenAPI: update if `/fs` accepts a new runtime principal header
  or if upload/download streaming changes response types.

## 7. Test plan

- Runtime adapter tests: keep existing path isolation tests; add graph
  `resolve_template` parity tests.
- SDK tests: stale doc fixes do not need tests, but any helper behaviour change does.
- Knowledge Flow tests: reject agent principal writes to `shared`; reject mismatched
  `agent_instance_id`; preserve human `/fs` behaviour.
- Frontend tests: reserved-character filenames in download/share/copy paths.
- Large file tests: streaming or size-cap tests depending on FILES-05 decision.
- Share-copy tests: concurrent collision test if atomicity is implemented.

## 8. Decision needed

Before implementation, decide:

1. Does P1 live inside `RUNTIME-07` or as a child FILES task that consumes signed grants?
2. Is share-copy provenance intentionally path-only, or do we need stored metadata?
3. Should SDK `FsEntry` expose provenance, or is provenance only a Files UI signal?
4. Does graph runtime template resolution intentionally include agent-space templates, or
   should it match `ToolContext`?

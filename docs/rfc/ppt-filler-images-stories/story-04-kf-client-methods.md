# Story 04 — Knowledge Flow client: tag-by-path resolution + raw original bytes

**Area:** agentic-backend (KF client wiring)
**Depends on:** nothing (can run first)
**Branch:** `image-support-in-ppt-filler` — commit when green.

## Goal

Add two capabilities the agentic side is missing:

1. **Resolve a folder string → DOCUMENT tag id** within a space (team or personal), by listing
   tags and matching full path. Backs the `FolderResolver` seam (Story 03).
2. **Fetch a document's ORIGINAL raw bytes by id.** The existing `KfDocumentClient` only has
   preview/markdown-media fetchers; add a raw-original fetcher. Backs the fill tool (Story 06).

## Knowledge Flow endpoints (already exist — do NOT modify KF)

- `GET /tags?type=document&owner_filter=<personal|team>&team_id=<id>&path_prefix=<optional>`
  → `list[TagWithPermissions]`, each carrying `id`, `name`, `path` (parent), and computed
  `full_path = path + "/" + name` (or just `name` at root). Type filter value is the `TagType`
  enum's `document` value — confirm the exact serialized string (likely `"document"`).
  Controller: `knowledge-flow-backend/.../features/tag/tag_controller.py` `list_all_tags`.
- `GET /raw_content/{document_uid}` → `StreamingResponse` of the original file bytes, with
  `Content-Type` and `Content-Disposition: attachment; filename="..."`.
  Controller: `knowledge-flow-backend/.../features/content/content_controller.py` `download_document`.

## Where to add the client code

Two reasonable homes — pick to match existing conventions:

- **Tag resolution**: a small new client `agentic_backend/common/kf_tag_client.py`
  (`KfTagClient(KfBaseClient)`) OR add a method to `KfDocumentClient`. A dedicated `KfTagClient`
  is cleaner (tags are a distinct KF surface). Mirror `KfDocumentClient`'s constructor
  (`agent`-based) and `_request_with_token_refresh` usage.
- **Raw bytes**: add `fetch_raw_content(...)` to `KfDocumentClient`
  (`agentic_backend/common/kf_document_client.py`) next to `fetch_preview_artifact`.

### Tag resolution method

```python
@dataclass(frozen=True)
class ResolvedTag:
    tag_id: str
    full_path: str

class KfTagClient(KfBaseClient):
    def __init__(self, agent): super().__init__(agent=agent, allowed_methods=frozenset({"GET"}))

    async def list_document_tags(
        self, *, owner_filter: OwnerFilter, team_id: Optional[str] = None,
        path_prefix: Optional[str] = None,
    ) -> list[ResolvedTag]:
        params = {"type": "document"}
        params["owner_filter"] = owner_filter.value
        if team_id: params["team_id"] = team_id
        if path_prefix: params["path_prefix"] = path_prefix
        r = await self._request_with_token_refresh("GET", "/tags",
              phase_name="kf_list_tags", params=params)
        r.raise_for_status()
        out = []
        for raw in r.json():
            name = raw.get("name"); path = raw.get("path")
            full_path = f"{path}/{name}" if path else name
            out.append(ResolvedTag(tag_id=raw["id"], full_path=full_path))
        return out

    async def resolve_folder(
        self, folder: str, *, owner_filter: OwnerFilter, team_id: Optional[str] = None,
    ) -> Optional[str]:
        """Return the tag id whose full_path == normalized(folder), else None."""
        target = folder.strip().strip("/").replace("\\", "/")
        for tag in await self.list_document_tags(owner_filter=owner_filter, team_id=team_id):
            if tag.full_path == target:
                return tag.tag_id
        return None
```

> The KF `full_path` may compute slightly differently; normalize both sides (strip surrounding
> slashes/whitespace) before comparing. Compare case-sensitively unless you confirm KF folds case.

### Raw bytes method (on `KfDocumentClient`)

Reuse the existing `PreviewArtifactBlob` dataclass shape (bytes/content_type/filename/size) or add
a parallel `RawContentBlob`. Stream like `fetch_preview_artifact`:

```python
async def fetch_raw_content(self, *, document_uid: str) -> RawContentBlob:
    r = await self._request_with_token_refresh(
        method="GET", path=f"/raw_content/{document_uid}", phase_name="kf_raw_content_fetch")
    r.raise_for_status()
    content = r.content
    ctype = r.headers.get("Content-Type", "application/octet-stream")
    # filename from Content-Disposition if present, else the uid
    ...
    return RawContentBlob(bytes=content, content_type=ctype, filename=filename, size=len(content))
```

## Tests

Fake the HTTP layer (these tests are unit, offline). Mirror existing client tests — look for how
`KfDocumentClient` is tested (if there is a test, follow its mocking style; otherwise mock
`_request_with_token_refresh` to return a fake response object with `.json()`, `.content`,
`.headers`, `.raise_for_status()`).

- `resolve_folder("images/flags")` returns the matching tag id given a fake `/tags` payload with
  `{id, name:"flags", path:"images"}`; returns None when absent.
- normalization: `"images/flags/"`, `" images/flags "` resolve the same as `"images/flags"`.
- owner_filter/team_id are forwarded as query params (assert the params dict passed to the request).
- `fetch_raw_content` returns the bytes + content_type from the faked streaming response.

If standing up these unit tests is disproportionate (no existing client-test harness), at minimum
add a focused test for `resolve_folder`'s path-matching/normalization using a fake
`list_document_tags` (monkeypatch), and keep `fetch_raw_content` covered indirectly by Story 06's
faked fill test. Document whatever you choose.

## Done when

- `make code-quality` and `make test` pass in `agentic-backend/`.
- Committed with `feat(ppt-filler): add KF tag-path resolution and raw-bytes client`.
</content>

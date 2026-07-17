# RAG Agent Quality RFC — Rico citation, tool result hygiene, and source navigation

**Status:** Draft — awaiting confirmation before implementation  
**IDs:** `RUNTIME-06` (backend), `CHAT-08` (frontend)  
**Author:** Dimitri  
**Date:** 2026-05-25

---

## 1. Problem statement

The Rico template (`fred.github.rag_expert`) has three compounding quality issues that together
make it unreliable in production.

### 1.1 Under-specified system prompt

`basic_react_rag_expert_system_prompt.md` is 8 lines.  It says _"cite the retrieved source
identifiers"_ but never specifies:

- the citation format (`[N]` superscripts, not titles, not filenames)
- that citations must be embedded inline at the point of use, not listed at the end
- which field in the tool result JSON is the citable text (`content`) vs noise
- that URL fields in the tool result **must not** be reproduced in the reply

Without these rules the LLM:
- cites by title ("see the Architecture Guide") — badges never render
- lists references as a footnote section — no inline `[N]` superscripts
- copies `citation_url` values as markdown links — always broken (see §1.2)

### 1.2 LLM reproduces broken URLs from tool result JSON

`knowledge.search` serialises every field of `VectorSearchHit` as JSON
(`react_tool_rendering.py:49` — plain `json.dumps`).  Each hit includes:

```json
{
  "citation_url": "/documents/abc123#chunk=def456",
  "preview_url":  "/documents/abc123",
  "preview_at_url": "/documents/abc123#page=2",
  ...17 more fields the LLM does not need
}
```

The frontend router has **no `/documents/:uid` route**.  Any link the LLM generates from
these fields produces a 404.  The MCP variant of the agent has an explicit "NEVER generate
URLs" guardrail that the built-in prompt lacks.

Two separate fixes are needed:
1. Explicit "never reproduce URLs" rule in the system prompt (defensive)
2. Strip URL and operational fields from the LLM-visible slice of the tool result (structural)

### 1.3 No source-to-document navigation from chat

Clicking `[N]` in the chat opens `SourceDetailModal`, which shows the chunk extract, title,
and metadata.  There is no way to open the full source document from chat.

The `/documents/{uid}` path exists in `VectorSearchHit.citation_url` and was designed to
point at a viewer page, but that page was never registered in the frontend router.

Signed/presigned URLs are **not relevant here**: the markdown viewer pipeline uses Keycloak
session tokens for authentication and handles presigned MinIO media URLs internally.
The `citation_url` path is a plain navigation URL, not a signed URL.

---

## 2. Proposed solution

### 2.1 Richer default system prompt (RUNTIME-06)

Replace `basic_react_rag_expert_system_prompt.md` with a production-quality prompt that:

- Specifies `[N]` as the citation format, where N is the 1-based position of the hit in
  the tool response, in order of appearance
- Requires inline embedding: place `[N]` immediately after the sentence that uses the
  evidence, not in a reference list at the end
- Identifies `content` as the evidence field and `title` as the source name field
- Forbids reproducing any URL, link, or path from the tool result
- Instructs the agent to call `knowledge.search` before answering any factual question,
  and to use multiple calls when the question has sub-parts

The `prompts.system` override field (already present as a `FieldSpec`) remains the operator
escape hatch — no schema change needed.

### 2.2 Show default prompt in the creation modal (RUNTIME-06)

When creating a Rico instance the "System prompt" textarea is empty — the `FieldSpec` has
no `default` and `UIHints.placeholder` is null.  The user cannot see or learn from the
built-in prompt.

Fix: set `placeholder=system_prompt_template` in the `UIHints` for `prompts.system`, and
wire `field.ui.placeholder` through `TuningFieldRenderer` → `TextArea`.

**Why `placeholder` and not `default`:**  Setting `default` pre-fills the value, which
means the instance stores the full prompt text and will not benefit from future prompt
improvements.  Setting it as a `placeholder` (greyed-out hint) shows the default without
committing to it; leaving the field blank always inherits the latest built-in prompt.

### 2.3 Prune LLM-visible tool result fields (RUNTIME-06)

In `_invoke_knowledge_search` (adapters.py), replace the full `hit.model_dump(mode="json")`
serialisation with an explicit allowlist of fields the LLM actually needs:

```python
KNOWLEDGE_SEARCH_LLM_FIELDS = {
    "uid", "title", "content", "file_name", "page", "section", "score",
}
```

All URL fields (`citation_url`, `preview_url`, `preview_at_url`, `repo_url`), operational
fields (`embedding_model`, `vector_index`, `retrieved_at`, `retrieval_session_id`,
`tag_ids`, `tag_names`, `tag_full_paths`, `token_count`), and access fields
(`confidential`, `license`) are excluded from the LLM-visible JSON.

The full `VectorSearchHit` continues to be sent to the frontend via the SSE `sources` array —
this change only affects the string that LangChain receives as the tool return value.

### 2.3 `/documents/:uid` route and viewer page (CHAT-08)

Register a new frontend route `/documents/:uid` that renders a full-screen document viewer
using the existing `MarkdownDocumentViewer` component (already available at
`src/common/MarkdownDocumentViewer.tsx`).

This closes the loop for `VectorSearchHit.citation_url`:
- The backend already constructs `citation_url = "/documents/{uid}#chunk={chunk_id}"`
- The new route receives this path and opens the correct document
- `#chunk=...` fragment can be used in a future phase to highlight the cited chunk
  (out of scope here — the viewer opens the document at the top for now)

`SourceDetailModal` gains an "Open document" link that navigates to
`/documents/{source.uid}` in a new tab.  This link is conditionally rendered only when
`source.uid` is known and not `"Unknown"`.

**Why a route rather than a drawer callback chain?**  
A dedicated route produces a shareable, bookmarkable URL.  Threading an `onOpenDocument`
callback from `ManagedChatPage` through `AssistantTurn` → `SourceDetailModal` would tie
the modal to a specific page context and prevent deep-linking.  The route approach also
makes `citation_url` useful immediately without further changes.

**No signed URLs needed for this flow.**  
`MarkdownDocumentViewer` calls `GET /knowledge-flow/v1/markdown/{uid}` with the Keycloak
session token already present in the RTK Query client.  Embedded images in the markdown
are served via presigned MinIO URLs that the backend injects transparently.

---

## 3. Alternatives considered

### 3.1 Strip URL fields from the vector search response DTO entirely

Removing `citation_url` from `VectorSearchHit` would require a breaking change to the
`fred-core` schema, regenerating OpenAPI specs, and updating every consumer.  Keeping the
field but excluding it from the LLM-visible slice is the minimal change.

### 3.2 Use only the existing `SourceDetailModal` (no navigation)

The modal already shows the chunk content, which is the most important piece.  But users
cannot reach the surrounding context or verify the passage in its original document.
For a production RAG assistant this is a critical UX gap.

### 3.3 Drawer callback threading

See §2.3 rationale.  The route approach is strictly better for shareability and decoupling.

---

## 4. Impact on existing contracts

| Contract file | Change |
|---|---|
| `RUNTIME-EXECUTION-CONTRACT.md` | Document `KNOWLEDGE_SEARCH_LLM_FIELDS` as the stable LLM-visible subset of `VectorSearchHit`; note that the full hit is still forwarded to the frontend |
| `CONTROL-PLANE-PRODUCT-CONTRACT.md` | No change — `VectorSearchHit` schema is unchanged |
| `router.tsx` | Add `/documents/:uid` route |
| `basic_react_rag_expert_system_prompt.md` | Replaced (content only, file path unchanged) |
| SSE contract | No change — `sources` array in final event is unaffected |

---

## 5. Out of scope

- Chunk highlighting in the document viewer (fragment `#chunk=...` handling) — follow-up
- Source de-duplication across multiple `knowledge.search` calls — follow-up
- Accurate citation-to-source mapping when the LLM skips indices — follow-up
- `SourceDetailModal` link for `repo_url` (external git links) — follow-up
- Native PDF rendering and an assistant side panel on `/documents/:uid` — superseded by
  `docs/swift/rfc/DOCUMENT-VIEWER-AI-PANEL-RFC.md` (`FRONT-13`); this RFC's route serves
  markdown only, by design, for every format until that phase lands.

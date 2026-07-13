# Document Viewer RFC — native PDF rendering + AI assistant side panel

**Status:** Draft — awaiting confirmation before implementation
**ID:** `FRONT-13`
**Author:** Dimitri
**Date:** 2026-07-12

---

## 1. Problem statement

FRED has two separate entry points that show the content of one ingested document, and
both currently render the same thing: extracted markdown text, regardless of the source
file's real format.

### 1.1 Two disconnected viewer flows, one shared renderer

- **Chat citation flow** (`CHAT-08`): clicking "Open document ↗" in `SourceDetailModal`
  navigates to `/documents/:uid` (`DocumentViewerPage.tsx`), which calls
  `GET /knowledge-flow/v1/markdown/{uid}` and renders the result with `MarkdownRenderer`.
- **Corpus workspace flow** (`FRONT-09`): clicking the preview action on a row in
  `TeamResourcesPage`/`DocumentWorkspace` opens a drawer (`useDocumentCommands.preview`)
  that renders the same markdown extract via `MarkdownDocumentViewer`.

Both flows were built independently during the kea→swift migration and never
consolidated, even though they show the same data through the same backend endpoint.

### 1.2 Native PDF rendering exists in the code but is wired nowhere

A real PDF renderer already exists — `PdfStreamingDocumentViewer.tsx` (`react-pdf`),
exposed through `usePdfDocumentViewer.tsx` and `commands.previewPdf` in
`useDocumentCommands.tsx`. On `main` (kea), this path was used: `DocumentLibraryRow`
picked `onPdfPreview` over `onPreview` for `.pdf` files, and `SourceDetailsDialog`
did the same file-extension check before opening a modal. On the current branch,
neither `DocRow`/`DocumentWorkspace` nor `DocumentViewerPage`/`SourceDetailModal` call
`previewPdf` — the callback has no caller. Users who click a PDF today get a plain-text
extract instead of the PDF they uploaded, which is a UX regression from kea, already
tracked as an open item on GitHub issue
[#1956](https://github.com/ThalesGroup/fred/issues/1956).

### 1.3 No path from "viewing a document" to "asking about it"

FRED already has document-grounded chat: `runtimeContextBuilder.ts` sends
`selected_document_uids` to scope a managed-chat turn to specific documents
(`ManagedChatPage`, control-plane `RuntimeContext.selected_document_uids`). But this
scoping is only reachable from the chat composer's document picker — there is no way,
while looking at one open document, to ask "summarize this" or "what does this say
about X" without leaving the viewer and manually re-selecting the same document in a
chat session.

### 1.4 Backlog/RFC duplication around this gap

The same "PDF viewer deferred, markdown only for now" note is currently written in three
places with no single source of truth: `RAG-AGENT-QUALITY-RFC.md` §5,
`CHAT-UI-BACKLOG.md` §9.4, and the `CHAT-08` entry in `id-legend.yaml`. This RFC becomes
that source of truth; the other three are trimmed to point here (see §6).

---

## 2. Proposed solution

### 2.1 One shared `DocumentViewer` component, two render strategies

Introduce a single `DocumentViewer` component used by both entry points
(`DocumentViewerPage` for the chat-citation route, and the corpus workspace preview
drawer), replacing the two independent call sites that each currently render
`MarkdownDocumentViewer` directly.

`DocumentViewer` picks a render strategy from the document's file type (already known —
`file_name` is available on both `VectorSearchHit` and the corpus document metadata):

- **`.pdf` → native rendering** via the existing `PdfStreamingDocumentViewer` (`react-pdf`).
  This wires up code that already exists (§1.2) instead of writing a new renderer.
- **Every other format (`.docx`, `.pptx`, `.xlsx`, `.txt`, …) → markdown rendering**, using
  the existing `GET /knowledge-flow/v1/markdown/{uid}` extraction the backend already
  produces for RAG. No new per-format renderer is proposed — see §3.1 for why.

This mirrors the choice kea already made (`isPdf` branch in `DocumentLibraryRow` /
`SourceDetailsDialog`) rather than inventing a new decision.

### 2.2 An "Ask the assistant" side panel next to the viewer

Add a collapsible side panel next to `DocumentViewer` (open document + Google-Drive-style
assistant panel, side by side — the feature that prompted this RFC). The panel offers:

- One or two quick-action buttons ("Summarize this document", "List key points") that
  send a canned prompt.
- A free-text input for follow-up questions.

Implementation reuses existing plumbing rather than adding a new one: the panel opens a
managed-chat turn with `selected_document_uids: [this document's uid]` — the same
mechanism `ManagedChatPage`/`runtimeContextBuilder.ts` already uses for the composer's
document picker. No new backend endpoint, no new agent, no new context-passing
mechanism.

### 2.3 Consolidation, not duplication, of tracking docs

- This RFC is the canonical design reference for "how FRED shows and lets users query one
  document." `RAG-AGENT-QUALITY-RFC.md` and `KNOWLEDGE-WORKSPACE-REWORK-RFC.md` keep a
  one-line pointer instead of re-describing the deferred PDF/AI-panel scope (§6).
- One backlog phase (`FRONTEND-BACKLOG.md` — new phase, ID `FRONT-13`) tracks the work
  for both entry points together, instead of splitting it across `CHAT-UI-BACKLOG.md`
  §9 and `FRONTEND-BACKLOG.md` §15/FRONT-09.E, which would recreate the original
  duplication this RFC is meant to remove.

---

## 3. Alternatives considered

### 3.1 Build native in-browser renderers for `.docx`/`.pptx`/`.xlsx` too

Rejected for this phase. The knowledge-flow ingestion pipeline already normalizes every
supported format into markdown for RAG; reusing that output for display is close to
free. Native renderers for every office format would be a much larger, separate effort
with its own licensing and fidelity questions (already partially in scope of
`INGEST-01`/`EXTENSIBLE-DOCUMENT-PROCESSOR-RFC.md` for ingestion, not display). PDF is
the one format singled out because kea already had a dedicated native viewer for it and
users lose that fidelity today; every other format was markdown-only in kea as well, so
there is no regression to fix there.

### 3.2 Bespoke AI panel with its own backend call

Rejected. FRED already has an agent-invocation contract
(`RUNTIME-EXECUTION-CONTRACT.md`) and a document-scoping mechanism
(`selected_document_uids`) built for exactly this purpose (constraining an agent turn to
one or more documents). A dedicated summarization endpoint would duplicate that
mechanism for no functional gain.

### 3.3 Keep two independent viewer call sites

Rejected. This is the status quo and the direct cause of the current inconsistency
(one call site wired to `previewPdf`, historically, and neither current one wired to
it now). A single `DocumentViewer` component removes the class of bug where one call
site gets a fix (e.g. PDF rendering, or later the AI panel) and the other silently
doesn't.

---

## 4. Impact on existing contracts

| Contract file | Change |
|---|---|
| `CONTROL-PLANE-PRODUCT-CONTRACT.md` | No schema change — reuses existing `RuntimeContext.selected_document_uids` |
| `RUNTIME-EXECUTION-CONTRACT.md` | No change — reuses the existing agent-invocation path |
| `COMPONENT-UX.md` | New entry once implemented: `DocumentViewer` (shared component, PDF + markdown strategies) and its assistant side panel |
| `router.tsx` | No new route — `/documents/:uid` already exists (CHAT-08) |

No backend endpoint, schema, or SSE contract changes are anticipated by this RFC. This
will be re-checked at implementation time if the assistant panel needs anything beyond
what `selected_document_uids` already carries (e.g. a canned-prompt template).

---

## 5. Out of scope

- Chunk-highlight fragment (`#chunk=...`) in the viewer — already deferred by CHAT-08,
  still deferred here.
- OCR / rendering for scanned PDFs with no extractable text layer.
- Per-format native renderers beyond PDF (§3.1).
- Public/unauthenticated document sharing.
- Editing or annotating documents from the viewer (this is a read + ask surface, not the
  `WritableDocument` collaborative-editing feature tracked separately on GitHub issue
  [#1905](https://github.com/ThalesGroup/fred/issues/1905)).

---

## 6. Cross-references to trim (companion edits in this change)

- `docs/swift/rfc/RAG-AGENT-QUALITY-RFC.md` §5 — replace the "PDF viewer route deferred"
  bullet with a pointer to this RFC.
- `docs/swift/backlog/CHAT-UI-BACKLOG.md` §9.4 — same trim, plus shorten §9.2 background
  (duplicated rationale now lives only in `RAG-AGENT-QUALITY-RFC.md` §2.3 and here).
- `docs/swift/backlog/FRONTEND-BACKLOG.md` FRONT-09.E — cross-reference this RFC instead
  of leaving "open actions" undefined.
- `docs/swift/data/id-legend.yaml` — new `FRONT-13` entry; trim duplicated rationale out
  of the `CHAT-08` entry's notes.
- GitHub issue [#1956](https://github.com/ThalesGroup/fred/issues/1956) already carries a
  "PDF viewer parity" checklist item; once this RFC's backlog phase exists, that item can
  point to `FRONT-13` instead of standing alone.

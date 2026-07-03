# PPT Filler Toolkit — PDF Preview Pane — PRD / RFC

Status: Draft
Provider key: `ppt_filler` (extends the existing toolkit)
Area: Agentic Backend (fill tool) + `fred-core` (shared pptx→pdf) + Knowledge Flow (user-storage presigned URL) + Frontend (resizable preview pane)
Extends: [`PPT-FILLER-TOOLKIT-RFC.md`](./PPT-FILLER-TOOLKIT-RFC.md)

---

## Problem Statement

Today a PPT Filler agent fills the template and returns a **download link**. To see whether the deck
is right, the user must download the `.pptx`, open it in PowerPoint, notice something to change, come
back to the chat, ask for the change, and download again. Every iteration is a full round-trip through
an external app. For a "fill my deck" feature whose whole value is getting a *good* deck, that
feedback loop is the main friction — the user cannot glance at the result and say "change the title"
without leaving Fred.

There is no way to **see the filled deck in the UI**, so there is no tight loop between "agent fills"
and "user asks for a correction."

## Solution

After a fill, show the filled deck as a **PDF preview in a resizable side pane** to the right of the
chat — the same pane pattern as the writable-documents editor
([`WritableDocumentPane`](../../frontend/src/components/chatbot/WritableDocumentPane.tsx)). The pane
**auto-opens the first time** an agent produces a deck, and the **chat stays fully usable** beside it,
so the user can read the preview and immediately type "make the title bigger" without downloading
anything. When the agent re-fills, the pane **updates in place** to the new version — a real
edit → preview → correct loop.

The deck is rendered by converting the filled `.pptx` to **PDF** (LibreOffice, already used in Knowledge
Flow) and displaying it with the existing `react-pdf` viewer. PDF is the only reliable way to show a
faithful deck in the browser; the conversion reuses proven code rather than inventing a renderer.

The preview is **best-effort and never blocks the deliverable**: if conversion fails or times out, the
user still gets the `.pptx` and is told in chat that the preview could not be generated.

## User Stories

### Using the agent (chat time)

1. As an end user, when an agent fills a deck, I want a **preview to open automatically** beside the
   chat, so that I can see the result immediately without downloading and opening PowerPoint.
2. As an end user, I want the **chat to stay usable while I view the preview**, so that I can ask for
   changes without closing the deck.
3. As an end user, I want the pane to be **resizable**, so that I can balance reading the deck and
   reading the chat.
4. As an end user, when I ask for a change and the agent **re-fills**, I want the open preview to
   **update to the new version**, so that I always see the latest deck without reopening anything.
5. As an end user, I want a **single card in the chat** for the produced deck — click it to (re)open
   the preview, and a button to **download the `.pptx`** — so that the deck is one clear object.
6. As an end user, if the preview can't be generated, I want to **still get the `.pptx`** and a clear
   note that the preview failed, so that a rendering problem never costs me the deck.

### Maintainability (shared logic)

7. As a maintainer, I want the `.pptx`→PDF conversion to live in **one shared place** used by both
   backends, so that the two do not each carry their own LibreOffice call.
8. As a maintainer, I want the **resizable pane shell** and the **in-chat artifact card** to be shared
   components, so that the writable-documents pane and the PPT preview do not duplicate layout, resize,
   and chip code.

## Implementation Decisions

This feature extends the existing `ppt_filler` toolkit (no new provider) and adds a read-only preview
surface. It does **not** touch the analyze/save flow, the template schema, or agent params.

### Conversion (shared, in `fred-core`)

- The LibreOffice `.pptx`→PDF conversion (today
  [`convert_pptx_to_pdf`](../../knowledge-flow-backend/knowledge_flow_backend/core/processors/input/pptx_markdown_processor/utils/pptx_slide_renderer.py)
  in Knowledge Flow) is **moved into `fred-core`**, the package both backends already depend on, so
  there is one implementation and one place to harden. `soffice` is already installed in both backend
  images.
- The shared helper must be **non-blocking and bounded**: run `soffice` off the event loop
  (`asyncio.to_thread`) with a **timeout**, in a `TemporaryDirectory`. Today's call is a bare, un-timed,
  blocking `subprocess.run` — acceptable inside a KF processor, not inside the async fill tool.

### Fill tool (eager conversion, graceful degradation)

- After the existing `.pptx` upload, the fill tool **converts the filled bytes to PDF eagerly** (every
  fill) and uploads the PDF **beside the `.pptx`** in the same session-scoped user storage
  (`{session_id}/…`), so the preview is ready the instant the deck is produced and the PDF is
  **auto-cleaned on session delete** exactly like the `.pptx`.
- On conversion failure/timeout the tool **still returns the `.pptx`**, omits the preview, and the
  success message **states the preview could not be generated**. The deck is never lost to a preview
  problem.
- The tool emits **one** new `ppt_preview` UI part (below) **instead of** the current standalone
  download `LinkPart` — the card carries both open-preview and download, so a separate download chip is
  redundant.

### PDF delivery (session-scoped, presigned URL)

- The PDF is stored in the **same `/storage/user` store** as the `.pptx`, and the browser fetches it
  **directly from object storage via a short-lived MinIO presigned GET URL** — not proxied through a
  Knowledge Flow streaming endpoint. Presigned GETs are **range-capable natively**, which is what
  `react-pdf` needs, and serving the bytes straight from MinIO keeps large-file transfer **off the app
  server** (consistent with the presigned-URL usage already elsewhere in the platform, e.g. tabular and
  content stores).
- Knowledge Flow exposes a small **bearer-protected `GET /storage/user/presigned/{key}`** endpoint that
  returns the presigned URL for a session-scoped key (it does not stream bytes). The fill tool calls it
  after uploading the PDF and puts the resulting URL on the preview part.
- Presigning is added to the **user-storage `MinioFilesystem`** (the backend `/storage/user` already
  uses), signing against the configured **public/ingress endpoint** so the URL is browser-reachable,
  mirroring `MinioStorageBackend`'s public-client pattern (`public_endpoint`/`public_secure`).
- The store choice is deliberate: `/storage/user` keys are `{session_id}`-prefixed and cleaned up on
  session delete, unlike the user-scoped asset store (no session cleanup) or KF ingestion (which would
  mint a library document and pollute the corpus).
- **Local/standalone caveat:** the local filesystem backend cannot presign; there the preview URL is
  simply omitted and the deck degrades to the `.pptx` download chip (below). MinIO deployments get the
  full preview. This is an accepted, known gap — local mode is not the priority.

### Preview part (new, specific)

- A new **`ppt_preview`** message part, mirroring the `writable_document` part plumbing (Pydantic model
  in the `MessagePart`/`UiPart` union; one branch in `hydrate_fred_parts`; regenerated OpenAPI types).
  It is **not** the `writable_document` part (different data, read-only, no autosave) and **not**
  `LinkPart(kind=view)` (a download-chip model that opens a blocking drawer).
- The part carries: the **presigned PDF URL**, a **version token** stamped per fill, a **title**, and the
  **`.pptx` download href** — enough for the card to be self-contained.
- **Freshness (the loop):** the version token is used as the `react-pdf` remount key, mirroring the
  writable-doc `updated_at` pattern. A re-fill yields a new version (derived from the PDF content hash),
  and — because presigning runs per fill — a brand-new presigned URL (fresh signature/date). New remount
  key + new URL → fresh fetch → the open pane updates live rather than showing a browser-cached stale
  deck. Note: the version must **not** be appended as an extra query param on the presigned URL — the
  presigned signature covers the whole query string, so an added `?v=` yields a `403 SignatureDoesNotMatch`.

### Frontend (shared shell + shared card)

- Extract a shared **`ResizablePaneShell`** from the existing ChatBotView pane markup + `useResizablePane`
  (divider, drag, open/close animation). **One pane is active at a time**: opening the PDF preview swaps
  the writable-doc pane and vice versa; each remains reachable from its chat card. This keeps the current
  single-surface layout.
- Extract a shared **artifact card** (icon + title + click-to-open-pane + download button) used by
  **both** the writable-doc chip and the ppt preview. For the ppt card, open → PDF pane, download →
  `.pptx`. The generic piece is the **card**, not the part: parts stay specific (rule of three — factor a
  shared part only when a third side-pane tool appears).
- A small `usePptPreview` controller mirrors `useWritableDocuments`: it reads `ppt_preview` parts,
  auto-opens the pane on first appearance, and points the viewer at the presigned PDF URL. The pane
  reuses the existing `react-pdf` rendering (same worker/`<Document>`/`<Page>` setup as
  [`PdfStreamingDocumentViewer`](../../frontend/src/common/PdfStreamingDocumentViewer.tsx)) inside the
  shared resizable pane shell rather than the blocking drawer.

## Testing Decisions

Tests assert **external behavior** and stay offline/fixture-driven.

1. **Shared conversion helper (`fred-core`, new)** — given a fixture `.pptx`, returns PDF bytes;
   respects the timeout (a stubbed slow/hung `soffice` returns the failure signal, not a hang); missing
   `soffice` degrades to the failure signal rather than raising through the caller.
2. **Fill tool (extended)** — a successful fill emits a `ppt_preview` part (PDF key + version + `.pptx`
   href) and no standalone download `LinkPart`; a **failed conversion** still returns the `.pptx` and a
   message noting the preview was skipped; the version token **changes on re-fill**.
3. **User-storage presign (KF, new)** — `WorkspaceFilesystem.presigned_url` signs the correct
   session-scoped `root/owner/key` path and delegates to the backend; a backend without presigning (local
   disk) raises `NotImplementedError` (the endpoint maps it to `501` and the fill tool degrades). MinIO
   signing against the public endpoint is covered by the existing content-store presign tests.

## Out of Scope

- **Editing** the deck in the pane — the preview is read-only; corrections go through the chat/agent.
- **Live/streaming** slide-by-slide rendering, thumbnails, or per-slide navigation beyond what
  `react-pdf` gives for free.
- **Two panes at once** (writable-doc + preview side by side / tabs) — one active pane; revisit only if
  a real need appears.
- Any change to the **analyze/save** flow, template **schema**, **params**, or agent **tool args**.
- Reusing the existing **PDF drawer** (`usePdfDocumentViewer`) — it blocks the chat, which defeats the
  loop.

## Further Notes

- **Why reuse, not rebuild:** conversion (LibreOffice), the PDF viewer (`react-pdf`), the resizable pane,
  and the auto-open pattern all already exist — this feature mostly **wires proven pieces** together and
  extracts two of them (conversion into `fred-core`, pane shell + card into shared components).
- **Highest-risk watch-points:**
  1. **Stale preview on re-fill** — if the version token is missing from the URL/remount key, a
     same-named re-fill shows the cached old deck and silently breaks the loop. Pinned by the
     version-changes-on-re-fill test.
  2. **Blocking/hanging conversion** — a bare synchronous `soffice` call inside the async fill tool
     stalls the agent turn; the helper must offload and time out. Pinned by the timeout test.
  3. **Preview failure taking the deck down** — conversion is best-effort; a failure must still return
     the `.pptx`. Pinned by the failed-conversion test.
- **Backward compatibility:** agents and templates are unchanged; the only chat-surface change is the
  produced-deck card (open-preview + `.pptx` download) replacing the bare download chip.

# Document Viewer RFC — "Ask the assistant" side panel

**Status:** Draft — blocked on a product decision, not a technical unknown
**ID:** `FRONT-13` (remainder)
**Author:** Dimitri
**Date:** 2026-07-12 — reduced 2026-08-03 to this remaining scope

> **§2.1 of this RFC (native PDF rendering via a shared `DocumentViewer`
> component) shipped 2026-07-19** — see `docs/swift/ux/COMPONENT-UX.md`
> (`DocumentViewer`) and `docs/swift/backlog/FRONTEND-BACKLOG.md` §19. This
> file now covers only the still-open remainder: the "ask the assistant"
> side panel.

---

## 1. Problem statement

FRED already has document-grounded chat: `runtimeContextBuilder.ts` sends
`selected_document_uids` to scope a managed-chat turn to specific documents
(`ManagedChatPage`, control-plane `RuntimeContext.selected_document_uids`).
But this scoping is only reachable from the chat composer's document
picker — there is no way, while looking at one open document, to ask
"summarize this" or "what does this say about X" without leaving the viewer
and manually re-selecting the same document in a chat session.

---

## 2. Proposed solution

Add a collapsible side panel next to `DocumentViewer` (open document +
Google-Drive-style assistant panel, side by side). The panel offers:

- One or two quick-action buttons ("Summarize this document", "List key
  points") that send a canned prompt.
- A free-text input for follow-up questions.

Implementation reuses existing plumbing rather than adding a new one: the
panel opens a managed-chat turn with `selected_document_uids: [this
document's uid]` — the same mechanism `ManagedChatPage`/
`runtimeContextBuilder.ts` already uses for the composer's document picker.
No new backend endpoint, no new agent, no new context-passing mechanism.

### 2.1 The blocking product decision

`ManagedChatPage` requires an `agentInstanceId` in its route, and
`selected_document_uids` only exists inside an already-open chat's composer
state — there is no "default/last-used agent" concept anywhere in the code
today. The panel needs an agent picker (the team's agent instances, same
source as `TeamAgentsPage`) before it can open a scoped turn at all. This is
the one thing blocking implementation; the plumbing itself (document
scoping, the managed-chat turn mechanism) already exists and needs no
change.

---

## 3. Alternative considered — a bespoke AI panel with its own backend call

Rejected. FRED already has an agent-invocation contract
(`RUNTIME-EXECUTION-CONTRACT.md`) and a document-scoping mechanism
(`selected_document_uids`) built for exactly this purpose (constraining an
agent turn to one or more documents). A dedicated summarization endpoint
would duplicate that mechanism for no functional gain.

---

## 4. Impact on existing contracts

| Contract file | Change |
|---|---|
| `CONTROL-PLANE-PRODUCT-CONTRACT.md` | No schema change — reuses existing `RuntimeContext.selected_document_uids` |
| `RUNTIME-EXECUTION-CONTRACT.md` | No change — reuses the existing agent-invocation path |
| `COMPONENT-UX.md` | New entry once implemented: the assistant side panel and its states |

No backend endpoint, schema, or SSE contract changes are anticipated. This
will be re-checked at implementation time if the assistant panel needs
anything beyond what `selected_document_uids` already carries (e.g. a
canned-prompt template).

---

## 5. Out of scope

- Chunk-highlight fragment (`#chunk=...`) in the viewer — already deferred
  elsewhere (CHAT-08).
- Editing or annotating documents from the viewer (this is a read + ask
  surface, not the `WritableDocument` collaborative-editing feature, GitHub
  issue [#1905](https://github.com/ThalesGroup/fred/issues/1905)).

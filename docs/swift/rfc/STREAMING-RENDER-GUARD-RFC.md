# RFC: Streaming Render Guard (CHAT-09)

**Status:** Implemented (2026-05-28) — live pod validation still pending  
**Author:** Dimitri Tombroff  
**Date:** 2026-05-26  
**ID:** CHAT-09  
**Backlog:** `docs/swift/backlog/CHAT-UI-BACKLOG.md §10`  
**Parent RFC:** `docs/swift/rfc/CHAT-RENDERING-SPEC.md`  
**Contract impact:** none — frontend only

---

## 1. Problem

During streaming, `assistant_delta` events deliver markdown in arbitrary chunks.
Block renderers — Mermaid, `react-syntax-highlighter`, and KaTeX — each require a
**complete syntax unit** to produce valid output. When a chunk boundary falls inside
a fenced block, the renderer receives:

- an unclosed ` ```mermaid ` fence → Mermaid throws, UI shows `Diagram error`
- an unclosed ` ```python ` fence → SyntaxHighlighter renders partial tokens with broken highlighting
- an unclosed `$$` block → KaTeX throws a parse error inline

All errors are transient — the final assembled message is correct — but each
intermediate render produces a visible error state that flickers until the closing
fence arrives. This degrades perceived quality and breaks the "streaming feels
like typing" illusion.

### 1.1 Root cause

`MarkdownRenderer` receives the live-accumulated text on every delta and passes
it directly to `react-markdown`. There is no fence-completeness check before the
content reaches block-level renderers.

### 1.2 Scope

Affected fence types:

| Syntax | Renderer | Failure mode |
|---|---|---|
| ` ```mermaid ` … ` ``` ` | MermaidBlock | `mermaid.render()` throws → `Diagram error` |
| ` ```<lang> ` … ` ``` ` | CodeBlock / react-syntax-highlighter | Partial token highlighting |
| `$$` … `$$` | KaTeX (rehype-katex) | Inline parse error |
| `:::details` … `:::` | remarkDetailsDirective | Raw directive text leaks |

Out of scope: GeoJSON. In the current stack, GeoJSON arrives as a `GeoPart` in
`ui_parts` on the `final` event — it is rendered outside `MarkdownRenderer`
and never reaches this pipeline during streaming. A ` ```json ` code block is
rendered by `CodeBlock` (syntax highlighting only) which does not throw on
incomplete input.

Plain inline markdown (bold, italic, links, headings, inline code) is unaffected —
these are safe to render incrementally.

---

## 2. Proposed solution

### 2.1 Principle

Introduce a single, generic streaming fence scanner that runs **before**
`react-markdown` receives content when the renderer is in streaming mode. It:

1. Scans the accumulated text for any open (unclosed) fence.
2. Splits the content into:
   - `stableMarkdown`: safe to hand to `react-markdown` immediately
   - `pendingFence`: metadata for the last still-open fence, if any
3. Keeps already-closed blocks in the normal markdown flow.
4. Lets the UI decide how to present the still-open fence.

Current UI policy:

- any open fence (` ```lang `, ` ```mermaid `, `$$`, `:::`) → render a
  `CodeBlock` shell immediately with the live source text
- once the closing delimiter arrives, hand the complete block back to the
  normal markdown pipeline
- for Mermaid specifically, the final markdown pass mounts `MermaidBlock` and
  renders the SVG only after the fence is complete

### 2.2 Fence detection rules

| Type | Open signal | Close signal | Notes |
|---|---|---|---|
| Backtick fence | `` ``` `` at line start (any info string) | `` ``` `` alone on a line | Covers code, mermaid, json, and any future lang |
| Dollar math block | `$$` at line start | `$$` alone on a line | Inline `$…$` is safe — single-line, never split |
| Directive block | `:::word` at line start | `:::` alone on a line | remark-directive syntax |

Detection is a line-by-line state machine — O(n), no AST required. The algorithm
must follow CommonMark §4.5 fence rules to avoid false positives:

1. A fence opener is only recognised **at the start of a line** (column 0, optional
   leading spaces ≤ 3). Mid-line backtick sequences (inline code, quoted examples)
   are never treated as openers.
2. Once inside an open fence, the scanner **stops looking for new openers** and only
   scans for the matching closer. This prevents content inside a code block (e.g. a
   mermaid example shown as documentation) from being misidentified as a nested open.
3. The closing fence must consist of the same fence character (`` ` `` or `$` or `:`)
   with at least as many repetitions as the opener, with no trailing content.

These three rules mean the guard is strictly a fence-state tracker, not a parser,
and produces no false positives on well-formed markdown.

### 2.3 MarkdownRenderer integration

`MarkdownRenderer` gains an optional `streaming` prop (default `false`).
When `true`, content is passed through `getStreamingMarkdownState(text)` before
rendering.

```
streaming=false (default, final messages)
  → content passed as-is

streaming=true  (active delta messages)
  → render `stableMarkdown` via `react-markdown`
  → if `pendingFence` exists, append `CodeBlock(streaming=true)`
```

`isStreaming` is already threaded from `AssistantTurn` into `AssistantMessage`
(see `AssistantTurn.tsx:71`, `AssistantMessage.tsx:25`). The only wiring change
required is `AssistantMessage.tsx:30` — add `streaming={isStreaming}` to the
existing `<MarkdownRenderer>` call. No metadata access needed.

### 2.4 What is shown during the incomplete-block window

For an open pending fence, the user now sees an immediate preview shell after
the opener arrives:

- Backtick fences (` ```python `, ` ```json `, ` ```mermaid `, etc.):
  - header: detected language + copy button
  - body: live-updating raw source text inside `CodeBlock`
- `$$` blocks:
  - header: `math` + copy button
  - body: live-updating raw source text inside `CodeBlock`
- `:::details` and other supported directives:
  - header: directive name + copy button
  - body: live-updating raw source text inside `CodeBlock`

Once the closing fence arrives, the pending block disappears from the streaming
preview path and the full markdown message re-renders normally, which mounts
the final renderer:

- Mermaid → `MermaidBlock` produces the SVG in the final markdown pass
- Other backtick fences → `CodeBlock` with syntax highlighting
- `$$` → KaTeX block rendering
- `:::` → native `<details>` rendering for supported directives

This keeps the progressive-feedback benefit of streaming while preserving the
"only render complete blocks" safety rule.

---

## 3. Alternatives considered

### 3.1 Per-renderer error suppression

Each block component catches errors and renders a neutral placeholder instead of
an error state. **Rejected:** this masks genuine diagram errors in production
(a real Mermaid syntax error would silently disappear). The guard never renders
errors in the first place, so legitimate errors remain visible after streaming ends.

### 3.2 Debounce / render throttling

Delay rendering by N ms after each delta. **Rejected:** introduces artificial
latency on the happy path (already-complete blocks are delayed unnecessarily) and
the correct debounce interval is unknown — a slow agent may take 500 ms between
tokens inside a code block.

### 3.3 Render only on `final`

Skip markdown rendering entirely during streaming, render only the raw text, then
switch to full rendering on `final`. **Rejected:** loses the progressive-rendering
UX for prose, headings, and inline elements, which is the main reason for streaming.

### 3.4 Hide all incomplete blocks

Hide every open fence until complete, including Mermaid, code, math, and
directives. **Rejected:** this avoids renderer errors but reintroduces the "why
is the assistant bubble empty?" problem whenever a reply starts with a fenced
block and suppresses useful progress feedback during long generations.

---

## 4. Files touched

| File | Change |
|---|---|
| `apps/frontend/src/rework/components/shared/molecules/MarkdownRenderer/streamingGuard.ts` | New utility — fence scanner + stable/pending split |
| `apps/frontend/src/rework/components/shared/molecules/MarkdownRenderer/streamingGuard.test.ts` | Unit tests (safe-prefix + pending Mermaid / code / math / directive metadata) |
| `apps/frontend/src/rework/components/shared/molecules/MarkdownRenderer/MarkdownRenderer.tsx` | Add `streaming?: boolean` prop; render stable markdown + unified pending preview |
| `apps/frontend/src/rework/components/shared/molecules/CodeBlock/CodeBlock.tsx` | Add `streaming?: boolean` mode for live source previews of all pending fences |
| `apps/frontend/src/rework/components/shared/molecules/CodeBlock/CodeBlock.module.css` | Add streaming source layout styles |
| `apps/frontend/src/rework/components/shared/molecules/MermaidBlock/MermaidBlock.tsx` | Keep Mermaid focused on final SVG rendering once the fence is complete |
| `apps/frontend/src/rework/components/shared/molecules/MermaidBlock/MermaidBlock.module.css` | Final Mermaid block styling (no separate streaming shell) |
| `docs/swift/rfc/CHAT-RENDERING-SPEC.md` | Amend §1.3 (what this doc covers) + §5 (acceptance criteria) to reference streaming guard |

No contract changes. No backend changes. No new dependencies.

---

## 5. Acceptance criteria

### 5.1 Functional

- [ ] Sending `markdown` to the test assistant produces **no** `Diagram error` flash
  during the 400 ms gap between the two streaming chunks, and shows a Mermaid
  `CodeBlock` shell labelled `mermaid` with streaming source text instead
- [ ] After the second chunk arrives the Mermaid diagram renders correctly (SVG, no error)
- [ ] A real agent reply containing a Mermaid diagram shows no error state during streaming
- [ ] Open non-Mermaid code fences show a `CodeBlock` shell with live source text during streaming,
  then switch to syntax-highlighted final rendering when the fence closes
- [ ] KaTeX block math shows no parse-error during streaming of a `$$` block and instead displays
  a `CodeBlock` shell labelled `math` until the block is complete
- [ ] Open `:::details` blocks show a `CodeBlock` shell with live source text during streaming,
  then switch to native `<details>` rendering when the block closes
- [ ] Completed blocks above a still-open fence render normally during streaming

### 5.2 Unit tests (`streamingGuard.test.ts`)

| Input | Expected output |
|---|---|
| Text with no open fence | Unchanged |
| Text ending after ` ```mermaid\ngraph TD\n    A --> B\n` (no close) | `stableMarkdown` truncated before ` ```mermaid ` + pending fence `{kind:"code", language:"mermaid", content:"graph TD\n    A --> B\n"}` |
| Text with one closed fence followed by one open fence | Only open fence stripped |
| Text with closed ` ```python ` block | Unchanged |
| Complete ` ```python ` block whose body contains ` ```mermaid ` text | Unchanged — inner text not treated as opener |
| ` ``` ` appearing mid-line inside inline code | Unchanged — not at line start |
| Text ending after ` ```python\nprint(1)\n` (no close) | `stableMarkdown` truncated before ` ```python ` + pending fence `{kind:"code", language:"python", content:"print(1)\n"}` |
| Text ending mid `$$` block | Truncated to text before `$$` + pending fence `{kind:"math", language:"math", content:"…"}` |
| Text ending mid `:::details` block | Truncated to text before `:::` + pending fence `{kind:"directive", language:"details", content:"…"}` |
| Empty string | Empty string |
| String with only the open delimiter | Empty string |

### 5.3 Non-regression

- [ ] `streaming=false` (default): `streamingGuard` is never called; no behaviour change for final messages
- [ ] `tsc --noEmit` passes after changes
- [ ] Existing rendering-spec acceptance criteria (CHAT-RENDERING-SPEC.md §5) all pass

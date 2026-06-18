# RFC: Human-friendly tool call labels in the chat trace

**ID:** CHAT-12  
**Author:** Simon Cariou  
**Status:** Draft — awaiting developer confirmation  
**Date:** 2026-06-18  
**Track:** chat UI rendering (`ThoughtTrace`) + fred-runtime ReAct thought synthesis  
**Builds on:** RUNTIME-04 / RUNTIME-05 (`AGENT-THINKING-API-RFC.md`) — this RFC
**extends** the tool-call thought synthesis those RFCs introduced; it does not add a
parallel mechanism.

---

## 1. Problem

End users find the thought/tool trace too technical: tool calls are shown with raw
technical identifiers.

RUNTIME-05 already moved part of the way. For every tool call the runtime now emits,
consecutively (`react_runtime.py:461-483`):

1. a `ThoughtStartEvent` with `phase="tool_use"` and
   `title=_tool_thought_title(name)` → e.g. `"Calling web search"`, and
2. the `ToolCallRuntimeEvent` carrying the raw `tool_name`.

In the frontend `groupTraceEntries()` turns these into **two separate rows** for the
same call:

| Row | Label | Inline text | State |
| --- | ----- | ----------- | ----- |
| thought (`tool_use`) | `Tool use` | **Calling web search** ✅ friendly | good |
| tool_call (combo) | `web_search` ❌ raw | **`web_search(query=…)`** ❌ raw | the problem |

Two issues remain:

- **The tool_call row is still technical.** `entryLabel()` (`traceUtils.ts:184`) and
  `primaryTextForEntry()` (`traceUtils.ts:206`) still render the raw `name` and
  `name(args)`. This violates the chat-UI rule *"Never show technical identifiers in
  user-facing UI."*
- **Redundancy.** The friendly "Calling web search" thought and the raw
  "web_search(…)" row describe the same call.
- **The humanizer is crude.** `_tool_thought_title()` (`react_runtime.py:216`) is
  `"Calling " + name.replace("_"," ").replace("-"," ")`. For an MCP tool
  `mcp__tavily__web_search` it yields `"Calling mcp  tavily  web search"` — double
  spaces, leaked namespace.

## 2. Decisions (confirmed 2026-06-18)

1. **Merge, not relabel.** The standalone raw tool_call row is removed from the
   trace. The `tool_use` thought ("Calling web search") is the visible, clickable
   entry; its tool `args` + result are attached to it and shown in the detail
   drawer. Zero redundancy; the technical payload stays in the drawer.
2. **Defer the authored `display_name` contract field.** Phase 1 does **not** touch
   the frozen runtime contract. An optional authored `display_name` on
   `ToolCallRuntimeEvent` / `ToolCallPart` is recorded as Phase 2 (§6), to be opened
   only if per-tool authored overrides are needed beyond humanization.

## 3. Goals

1. Tool calls read as a single human-friendly line; no raw identifier in the row.
2. The raw `name`, `args`, and result remain inspectable in `TraceDetailDrawer`.
3. **No frozen-contract change** in Phase 1 — extend existing helpers and frontend
   grouping only.
4. Reuse and improve `_tool_thought_title`; do not introduce a competing humanizer.

## 4. Non-goals

- No authored `display_name` field in Phase 1 (deferred — §6).
- No localization (i18n) of labels.
- No change to `ThoughtTrace` layout or the open UX issues in `COMPONENT-UX.md`
  (label chip, chevron, timeline alignment).

## 5. Phase 1 — proposed solution (contract-free)

### 5.1 Backend — improve the humanizer (`libs/fred-runtime`)

`_tool_thought_title()` (`react_runtime.py:216`) is an internal helper that fills the
**already-existing** `ThoughtStartEvent.title` field — improving the string it
returns is **not** a contract change. Improvements:

- Strip the MCP namespace prefix (`mcp__<provider>__<tool>` → `<tool>`, optionally
  surfacing the provider as context).
- Collapse repeated whitespace; split `_`/`-`; sentence-case the readable name.
- Optional small dictionary for common platform tools (e.g.
  `web_search → "Web search"`).
- Keep the `"Calling …"` phrasing.

`libs/fred-runtime/tests/test_react_thinking.py` (added by RUNTIME-05) is updated to
pin the new strings, including the MCP-prefixed case.

### 5.2 Frontend — merge the tool_call row under its thought (`apps/frontend`)

The `tool_use` thought and its `tool_call` are emitted consecutively and therefore
arrive **adjacent** in the message list (consecutive `rank`s). `groupTraceEntries()`
(`traceUtils.ts`) is extended to pair them by adjacency — no id plumbing, no contract
change:

- When a `tool_use` thought is immediately followed by its `tool_call`, attach the
  call (and its matched result, by `call_id`) to the **thought** entry and **do not**
  emit a separate combo row for that call.
- The detail drawer (`traceDrawerContext` / `TraceDetailDrawer`), when opened on a
  merged `tool_use` thought, renders the attached `args` + result JSON — the raw
  technical view, unchanged in substance.
- **Fallback:** a `tool_call` with no preceding `tool_use` thought (non-streaming
  `invoke()` path, graph agents, thinking disabled) keeps its combo row, but its
  label/inline text are humanized by a small frontend helper that **mirrors**
  `_tool_thought_title` so orphan calls are never raw either.

### 5.3 Resulting render

```
● Tool use   Calling web search          Done
             └─ drawer: { call_id, name: "web_search", args:{…}, result:{…} }
```

## 6. Phase 2 — authored `display_name` (deferred)

If specific tools need a curated label that humanization cannot derive, add an
**optional** `display_name` carried by the tool definition → `ToolCallRuntimeEvent`
→ `ToolCallPart`, used as the highest-priority source in the chain
`display_name → humanized name`. This is additive and touches the frozen contract,
so it gets its own RFC amendment, a dated `RUNTIME-EXECUTION-CONTRACT.md` §8 entry,
and developer sign-off. Not in scope now.

A robustness option for Phase 2: add an optional `call_id` to the `tool_use`
`ThoughtStartEvent` so the frontend pairs by id instead of adjacency. Only needed if
adjacency proves fragile in practice.

## 7. Alternatives considered

- **Relabel both rows** (keep the raw row but humanize it). Rejected per decision §2
  — leaves the thought/row redundancy.
- **Pair thought↔call via a new `call_id` field on the thought event.** Deferred to
  Phase 2: adjacency is reliable because the two events are emitted consecutively,
  and it avoids a frozen-contract change.
- **Frontend-only static dictionary as the primary mechanism.** Rejected — cannot
  cover MCP / dynamic tools and drifts from the registry; kept only as the small
  orphan-combo fallback that mirrors the backend humanizer.

## 8. Impact on existing contracts

- **None in Phase 1.** `_tool_thought_title` returns a string for the existing
  `ThoughtStartEvent.title`; `groupTraceEntries` is frontend grouping logic. No
  Pydantic model, OpenAPI schema, or generated TS type changes.
- Phase 2 (deferred) would add an optional `display_name` to
  `ToolCallRuntimeEvent` + `ToolCallPart` and regenerate the TS types — handled
  under its own amendment.

## 9. Test plan

- **Backend:** unit tests for the improved `_tool_thought_title` (snake/kebab
  splitting, MCP-prefix strip, whitespace collapse, dictionary hit); update
  `test_react_thinking.py`.
- **Frontend:** unit tests for `groupTraceEntries` merge (tool_use thought + adjacent
  tool_call → single merged entry carrying args/result; orphan tool_call keeps a
  humanized combo row); drawer renders attached args/result for a merged entry.
- `make code-quality` + `make test` in `libs/fred-runtime` and `apps/frontend`.

## 10. Rollout

Phase 1 has no data or contract migration. Frontend and backend changes are
independent and individually safe: if only the backend ships, titles improve; if
only the frontend ships, rows merge using the existing crude title. Full effect when
both ship.

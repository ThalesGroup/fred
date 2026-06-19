# RFC: Document Comparison Graph Agent (similarity showcase)

**Status:** proposed
**Author:** Dimitri Tombroff
**Date:** 2026-06-19
**ID:** FILES-03
**Scope:** swift `apps/fred-agents` only (new agent; no platform change)
**Contract impact:** none — consumes the already-shipped `similarity_search` MCP
tool ([KF-SIMILARITY-SEARCH](KNOWLEDGE-FLOW-SIMILARITY-SEARCH-RFC.md)); no new
endpoint, MCP server, or `TOOL_REF`
**Driver:** give the standalone pod a flagship agent that demonstrates targeted
similarity comparison and is immediately useful to clients

---

## 1. Decision (in one paragraph)

Add a new **GraphAgent** to `apps/fred-agents`, `fred.dt.comparison.graph`, that
compares **two documents** picked in the Documents picker and returns a structured
report of what **agrees**, what **contradicts**, and what is **missing** between
them — through the lens of the user's instruction. It is the first consumer in the
public pod of the `similarity_search` primitive that
[KF-SIMILARITY-SEARCH §7](KNOWLEDGE-FLOW-SIMILARITY-SEARCH-RFC.md) lists as a
future use case ("Gap / future diff agents").

## 2. Problem

The pod's grounded agents (`rag_expert`/Rico, `react_rag_mcp`) only do corpus-wide
Q&A: embed a question, retrieve top-k, answer. None of them *compares two things*.
The new targeted similarity search makes comparison a first-class, deterministic
primitive, but nothing in the public catalogue shows it off, and clients have an
obvious recurring need: "are these two documents consistent?" (contract vs amendment,
document vs standard/policy, spec vs implementation note, version A vs version B).

## 3. Proposed solution

A deterministic graph where the LLM only **judges**, never drives retrieval:

1. `resolve_documents` — read `selected_document_uids`; need ≥ 2 (A = first,
   B = second; extras noted, not compared). Fewer → render a picker-guidance message.
2. `pull_anchors` — `similarity_search(anchor=user_instruction, document_uids=[A],
   top_k=anchor_count, rerank=true)` → the salient passages of **A** for the user's
   focus.
3. `compare_pairs` — for each A-passage, `similarity_search(anchor=passage,
   document_uids=[B], top_k=1, rerank=true)` → its closest **B** passage (bidirectional
   intent; B-with-no-match ⇒ candidate gap).
4. `judge_pairs` — per pair, one small structured model call → `relation ∈
   {concordance, contradiction, lacune}` + a short note (LLM judges, in the user's
   language).
5. `render_report` — markdown with three sections (Concordances / Contradictions /
   Lacunes), sources attached as `VectorSearchHit`.

Best-effort: every node's `error_route` falls forward to `render_report`, never
failing the turn (same posture as Eva).

**Tooling:** declares `MCP_SERVER_KNOWLEDGE_FLOW_TEXT`; calls the tool from nodes via
`context.invoke_runtime_tool("similarity_search", {...})` (the MCP-tool path mindmap
already uses for `read_file_page`). No `TOOL_REF` exists or is needed for
similarity search — it is MCP-native.

## 4. Alternatives considered

- **Improve Rico / a ReAct agent + similarity tool.** Rejected: Rico is a domain RAG
  agent in `fred-rags`, not a pod showcase, and a ReAct loop would use the tool as
  just another search — it would *not* illustrate the comparison paradigm (the whole
  point is deterministic targeted pairing with the LLM only adjudicating).
- **New MCP service.** Unnecessary: `similarity_search` already ships over the Text
  MCP server (KF-SIMILARITY-SEARCH §11).
- **Full-document FS read + self-segmentation (mindmap style).** Heavier plumbing for
  no extra demonstrative value; `similarity_search` over [A] already yields the
  anchor passages.

## 5. Impact / non-goals

- Additive only; no change to frozen contracts, existing agents, or the SDK.
- Non-goal (v1): >2-document matrix comparison, doc-vs-reference-library mode (a
  tuning variant for a follow-up), and citation deep-linking beyond standard sources.

## 6. Tracking

- id-legend: `FILES-03` · backlog: `docs/swift/backlog/BACKLOG.md`
- Tests: offline graph wiring + pair judging with mocked `invoke_runtime_tool`
  (`similarity_search`) and a seeded structured model — no network.

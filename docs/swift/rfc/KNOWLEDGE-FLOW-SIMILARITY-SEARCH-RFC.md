# RFC: Knowledge Flow — Targeted Similarity / Comparison Search

**Status:** draft — for review with the rags team
**Author:** Dimitri Tombroff
**Date:** 2026-06-18
**ID:** KF-SIMILARITY-SEARCH
**Scope:** swift `apps/knowledge-flow-backend` only (additive capability)
**Contract impact:** additive — a new search mode; the existing conversational
search is unchanged
**Driver:** the rags assessment agent (Eva); also gap / contradiction analysis

---

## 1. Decision (in one paragraph)

Add a **targeted similarity search** mode to Knowledge Flow: *"given an anchor
text, return the passages most similar to it **within a set of targets named on
the call** (documents and/or folders), ranked best-first."* This is **additive** —
it sits alongside today's conversational, question-answering search and changes
nothing about it. It exists because some agents are not doing Q&A; they are doing
**document-to-document comparison**, and that needs search that can be **re-aimed
on every query**, not scoped once per conversation.

---

## 2. Problem (functional)

Knowledge Flow's search today is built for **conversation**: a user or agent picks
some libraries/documents **once** for the exchange (the request scope), then asks
questions answered within that fixed scope. This is correct for chat/RAG.

But the rags **assessment** agent (Eva) is not answering questions — it is
**comparing two documents** of an information system:

- the **technical architecture** document (how the system is designed), and
- the **operation manual** (how it is actually operated).

From that comparison it produces **similarities**, **contradictions**, and a
consolidated **technical-detail** sheet, then cross-checks those facts against the
**CMDB** inventory. Every one of those steps is the same primitive: *"for **this**
passage, what is the closest passage **in that** other document?"*, run many times
with a **different target each time**.

That primitive does not fit the conversational model:

| | Comparison agents need | Conversational search offers |
| --- | --- | --- |
| Target | a **specific** document/folder, chosen **per query** | scope chosen **once** per request |
| Intent | **compare** anchor passage ↔ target | **answer a question** over a scope |
| Frequency | many **re-targeted** searches per run | one scope per request |

Agents can work around it (search the whole library, then discard hits that aren't
from the document they care about), but that is a workaround: imprecise, wasteful,
and every comparison-style agent must re-invent it.

---

## 3. Goals / Non-goals

**Goals**
- One new, first-class capability: *find passages similar to an anchor text,
  within caller-named targets, ranked best-first.*
- Re-aimable **per call** (targets are a query argument).
- **Relevance-ranked** so the caller can confidently take "the single closest
  passage" (restores the dedicated re-ranking the legacy stack had).
- Reusable by any comparison/diff need (assessment, gap, CMDB cross-check, future
  agents) — not Eva-specific.

**Non-goals**
- Not replacing or changing the existing conversational search.
- No new ingestion, embedding, or storage model — it reuses the corpus already
  indexed.
- No agent business logic (pairing rules, contradiction detection) — that stays in
  the agents; this RFC only provides the search primitive.

---

## 4. The capability (functional contract)

A single operation, described functionally (not an implementation):

**Inputs**
- **anchor** — the text (a passage/chunk) to find similar content for.
- **targets** — *which* corpus to search, named on the call:
  - a set of **document** identifiers, and/or
  - a set of **folder / library** identifiers.
  (Empty targets = an explicit error, not "search everything" — targeting is the
  point.)
- **top_k** — how many matches to return.
- **rerank** — whether to apply relevance re-ranking (default: **on**).
- **min_score** *(optional)* — drop matches below a relevance threshold.

**Outputs** — a list of matches, **ordered best-first**, each carrying:
- the **matched passage text**,
- its **source** (document id + name, and location e.g. page/section),
- a **relevance score**.

**Behaviour**
- The result set is drawn **only** from the named targets.
- Ordering reflects re-ranked relevance, so "take the top 1" is meaningful.
- Auth is the caller's (the search only sees what the caller may see).

That is the whole surface. "Compare document A to document B" becomes: for each
passage of A, call this with `anchor = passage`, `targets = [B]`, `top_k = 1`.

---

## 5. How it relates to existing search

- **Additive.** The conversational/question-answering search is untouched. This is
  a distinct mode for a distinct intent (compare, not ask).
- **Same corpus.** It reads the already-indexed documents; no re-ingestion.
- **Same auth model.** Caller identity governs visibility.
- The key difference is **where targeting lives**: existing search takes its scope
  from the **request/conversation**; this mode takes its target from the **call**.

---

## 6. Surfaces — MCP first

The same capability is exposed to two audiences; **agent-facing first**:

1. **MCP (agents)** — *primary.* Eva and comparison agents call it while reasoning.
   This is what unblocks the rags work and should ship first.
2. **REST (UI / backends)** — *follow-up.* Add when a product screen needs
   on-demand "find similar passages" (e.g. a future assessment review UI).

Both are thin exposures of one underlying capability.

---

## 7. Use cases this unlocks

- **Eva — similarities & contradictions:** pair each architecture passage with its
  closest operation-manual passage (and vice-versa), then let the LLM judge
  agreement/disagreement.
- **Eva — CMDB cross-check:** "find where this documented technology appears in the
  CMDB" is the same primitive aimed at the CMDB documents.
- **Gap / future diff agents:** any "compare these two things" workflow reuses it
  instead of re-inventing fetch-then-filter.

---

## 8. Decisions to settle with the rags team

1. **Targeting granularity.** Start with **documents + folders** (covers Eva and
   the CMDB cross-check). Defer **passage-level** targeting until a concrete need.
   — *Recommend: documents + folders for v1.*
2. **Ranking.** Confirm re-ranking is **on by default** (the legacy assessment
   relied on a dedicated rerank step for precision).
3. **Empty/over-broad targets.** Confirm that a missing/empty target is an
   **error** (vs. silently searching everything) — to keep the capability precise.
4. **Relevance knobs.** Is `top_k` (+ optional `min_score`) enough for v1, or does
   assessment need a richer notion (e.g. "best per target document")?
5. **Naming.** Agree a clear name for the mode so it is obviously *not* the chat
   search (e.g. "similarity search" / "comparison search").

---

## 9. Acceptance criteria

- A caller can request, in **one call**, the passages most similar to an anchor
  text **restricted to named documents/folders**, returned **ranked best-first**
  with source + score.
- Targeting is honoured: results never include passages outside the named targets.
- The existing conversational search is unchanged (no regression).
- Exposed over **MCP** for agents (REST is a tracked follow-up).
- Eva's assessment retrieval can drop its client-side fetch-then-filter workaround
  and call this directly.

---

## 10. Out of scope

- Agent logic (how pairs are judged, how contradictions are derived).
- Ingestion / embedding / storage changes.
- The rags pod and rags-services (separate; they only *consume* this).
- Passage-level targeting and the REST surface (tracked follow-ups, §6 / §8).

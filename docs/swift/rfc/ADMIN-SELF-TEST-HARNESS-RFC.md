# RFC — Admin Self-Test Harness and Golden Corpus

**Status:** As-built — Phase 1 complete (2026-06-25)
**Author:** Dimitri Tombroff
**Area:** `frontend`, `fred-agents`
**Extends:** VALID-01 (`docs/swift/backlog/BACKLOG.md §3b.7`)
**IDs:** `VALID-02` (harness), `VALID-03` (golden corpus) · **Execution:** GitHub issue #1828
**Related:** `AGENT-VISIBILITY-RFC.md`

> History: an earlier draft implemented this as a control-plane backend module that
> called Knowledge Flow over ad-hoc `httpx`. That validated the data plane but routed
> *around* the execution pipeline it was meant to prove. It was reverted; the design
> below (UI-driven, real pipeline) is authoritative.

---

## 1. Problem

Subtle user-facing features — selecting a prompt, choosing a search mode, scoping a
library — pass in CI against fakes yet can break silently in a real deployment. We want
a platform-admin page that validates them **end-to-end through the real pipeline, on the
live stack**, and whose building blocks are **reusable** (e.g. seeding a corpus +
conversations to demo Odelia's evaluation dataset builder).

## 2. Architecture — UI-driven, real pipeline

The **frontend is the test driver**. Acting as the admin in their personal space, it runs
a sequence of real product calls (the same RTK Query hooks the UI uses) ending in a real
managed-agent execution whose answer is asserted. **No backend harness code:** the browser
drives real calls and tracks step state, rendered with the existing Task/Event atoms.

Reusable engine in `rework/features/pipeline/`:
`actions` (createLibrary · ingestDocument · runAgentTurn · deleteLibrary · provision/delete
agent) → `scenarios` (self-test is #1) → generic `usePipelineRun`. A future eval-demo page
reuses the same actions — `runAgentTurn` persists conversations — with no teardown.

Self-test scenario, each step a real call:

| # | Step | Reused product path |
| --- | --- | --- |
| 1–2 | Create personal folders A, B | `createTag` (`team_id: null`) |
| 3 | Provision the self-test agent (enroll if missing) | agent-templates + enroll |
| 4–5 | Upload marker doc → A, plain doc → B; wait for indexing | upload streamer + ingestion task SSE |
| 6–7 | Ask the agent scoped to A (marker must be found) / B (must be absent) | `prepare-execution` → execute stream |
| 8 | **System-prompt journey:** assert the `prompts.system` marker (set at enrollment) is echoed back | tuning at enroll → execute stream |
| 9–12 | **Context-prompt journey:** create a personal prompt → create a session → attach prompt → assert the marker is echoed back | `prompts` / `sessions` (PATCH `context_prompt_ids`) → `prepare-execution` |
| 13+ | Delete the session, prompt, agent instance + both folders (cascades docs); verify gone | delete mutations / `deleteTag` |

## 3. The self-test agent (`fred.github.self_test`)

A deterministic RAG agent in `fred-agents`: real retrieval through the runtime
knowledge-search tool (the runtime applies the per-turn library scope), echoing the
retrieved chunks verbatim — **no LLM** — so assertions check *which chunk was retrieved*,
never LLM prose. It is `public=False` (hidden from the create-agent catalog,
`AGENT-VISIBILITY-RFC`); the harness auto-enrolls and deletes its instance each run.

Every reply also carries a deterministic **delivery footer** echoing the two prompts
the turn received — `system_prompt:` (from `prompts.system` tuning via
`context.tuning_values`) and `context_prompt:` (from `binding.runtime_context.context_prompt_text`).
Echoing proves the prompt was *delivered* through the real pipeline (deterministic),
not that an LLM obeyed it (which would need an LLM and be nondeterministic). This agent
is the **first consumer of `context_prompt_text`** — the field was resolved control-plane
side and forwarded, but nothing read it agent-side until now.

## 4. Golden corpus (VALID-03)

Authored inline in the frontend (`scenarios/corpus.ts`): a unique marker fact lives in
exactly one library, so "scoped to A → found / scoped to B → absent" is a deterministic
assertion even against a real, nondeterministic RAG stack. Assert on structure (marker
present/absent, doc cited), never on prose.

## 5. What Phase 1 already found

The first live docker-compose run surfaced a silent, platform-wide RAG failure: the
Knowledge Flow **API searched index `embeddinggemma` while the worker wrote
`vector-index-mistral`**, so every user query returned zero results. Fixed
(`configuration_prod.yaml`). This finding alone justified the work.

The prompt journeys then caught a **second** silent platform gap (the original day-one
fear, confirmed real): the runtime rebuilt `RuntimeContext` from the request and
**dropped `context_prompt_text`** ([`agent_app.py` `_iterate_runtime_event_payloads`](../../../libs/fred-runtime/fred_runtime/app/agent_app.py)),
so a marketplace/library prompt selected for a conversation was resolved control-plane
side and forwarded by the frontend but **never reached any agent**. The system-prompt
(tuning) journey passed while the context-prompt journey failed with
`context_prompt: (none)` — pinpointing the drop. Fixed (one field, same class as the
May-2026 chat-options drop); see RUNTIME-EXECUTION-CONTRACT §8.5.

## 6. Phasing

- **Phase 1 — done:** UI-driven pipeline; real agent execution; library-scope
  positive/isolation; auto-provisioned + auto-deleted agent instance; agent visibility.
- **Prompt-delivery journeys — done:** system prompt (tuning) and context/marketplace
  prompt (prompt-library → session attachment → `context_prompt_text`), both asserted by
  the agent echoing the delivered marker. Covers the original day-one fear ("does a
  selected personal/team prompt actually reach the agent?").
- **Phase 2 — remaining campaign:** drive the *real* chat widgets (`ContextPromptPicker`,
  search-mode control, library scoper) rather than constructing `RuntimeContext` directly;
  add **search-mode discrimination** journeys (hybrid / strict / semantic, with corpus
  terms crafted so each mode's result differs); attachment journey.
- **Phase 3 — unattended:** headless mode + ~2h K8s CronJob on the live GKE release
  (reuse VALID-01's scenario runner; service-account auth).

## 7. Dependencies / caveats

- The agent steps need a live runtime pod (the VALID-01 "live pod" blocker); when absent
  they **skip** with a clear reason rather than failing.
- Personal-space scope is confirmed; everything created is deleted each run.

## 8. Tracking

`VALID-02` (harness), `VALID-03` (golden corpus), GitHub issue #1828, backlog
`BACKLOG.md §3b.7`, PMO board. Agent visibility: `AGENT-VISIBILITY-RFC.md`.

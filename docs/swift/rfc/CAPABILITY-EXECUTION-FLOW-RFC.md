# RFC: Capability execution flow — vocabulary, and a durable execution tier for capability internals

**Status:** proposed — open design question; no implementation approved by this RFC alone
**Author:** Dimitri Tombroff
**Date:** 2026-08-08
**ID:** CAPAB-EXEC-FLOW-01
**Related docs:** `docs/swift/platform/TEMPORAL.md`; `docs/swift/capabilities/AUTHORING.md`;
`docs/swift/design/AGENT_DESIGN.md` §5–6; `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`
§8.43 (`DocumentMarkdownPort`), §8.44 (`DocumentExtractionPort`); GitHub #2240
("RFC: Design pluggable ingestion runtimes coordinated by Temporal")

---

## 0. Terminology (read this first — it is the point of this revision)

An earlier draft of this RFC called the thing being proposed a **"Workflow
tier."** That name was wrong, and the mistake is worth naming explicitly
because it is easy to repeat: **"workflow" is doing three unrelated jobs in
Fred's current vocabulary**, and collapsing them loses the exact distinction
this RFC needs to make.

1. **Temporal's own SDK primitive.** `TEMPORAL.md` already uses capital-W
   `Workflow` as Temporal's reserved term for its durable orchestration unit
   — "§2.1 Workflow determinism," "Workflow MUST wait deterministically,"
   `WorkflowResult`, "start child workflows." This is a code-level identifier
   (`@workflow.defn` in the Temporal SDK), not a Fred architectural layer.
2. **`AGENT_DESIGN.md`'s "Business Workflow Agents (Explicit Graphs)"**
   (§5–6) — an *Agent template* (e.g. `LaPosteDemoAgent`) that happens to be
   an explicit LangGraph instead of a ReAct loop. It is still, structurally,
   one Agent.
3. **The composition-of-independent-steps concept** the developer described
   in review: extract → analyse → query catalogue → build matrix → store,
   where each step has its own meaning, can fail/resume/branch on its own,
   and the composition itself is a visible business decision.

Meaning (3) is the one worth a dedicated word. Meanings (1) and (2) should
**not** borrow it going forward. This RFC adopts three terms and draws the
line precisely where the developer drew it in review:

| Term | Answers | Scope test |
| --- | --- | --- |
| **Agent** | "What should be done, given a goal?" | Chooses dynamically at runtime, LLM-decided. |
| **Capability** (this RFC's subject) | "How is one contractual operation carried out reliably?" | Its *implementation* may contain arbitrary deterministic orchestration — fan-out, retry, pagination, map/reduce, caching, provider fallback — but from the caller's side it stays **one atomic action**: `extract(document, criterion)`. The internal mechanism is a **capability execution flow** — call it `ExecutionPlan`, `Pipeline`, `Runner`, or leave it an unnamed implementation detail. It is not, and must not be called, a "Workflow." |
| **(Application/Business) Workflow** | "What sequence of independently-meaningful steps realizes this use case?" | Explicitly composes Agents, Capabilities, and Services. Each step is independently retryable, observable, replaceable, and the composition itself is versioned and changed on purpose (e.g. inserting a human-approval step). |

The governing rule, verbatim from review because it is precise enough not to
paraphrase:

> **A capability may internally orchestrate, but it must remain externally
> atomic.** Capabilities hide orchestration; workflows define orchestration.

Two practical tests fall out of this and are used throughout the RFC below:

- **Caller-awareness test.** Does the caller need to know the internal steps?
  For `document_extract`, no — 26 windows, 3 workers, 5 retries, and a
  dedup pass are implementation detail the contract must never leak. For the
  bid example, yes — "extraction happens before analysis, which happens
  before the catalogue query" *is* the application logic; hiding it inside
  one `process_bid()` capability would be the wrong abstraction.
- **Resumption-semantics test.** If `document_extract` fails mid-window-17,
  its own execution flow retries/resumes without the caller ever knowing.
  If a Workflow's "analyse requirements" step fails, the *application*
  orchestrator decides whether to retry that step, ask for human approval,
  branch, or abort — a decision that belongs above the capability boundary,
  not inside it.
- **Versioning test.** `document_extract:v3` can change its internal
  mechanism (sequential pagination → parallel packed map) with zero visible
  change to any caller, as long as the contract holds. Changing a Workflow's
  step sequence (e.g. inserting a human-approval gate between analysis and
  generation) *is* a visible process change, and should be versioned,
  traced, and configurable as one.

**Consequence for this RFC's own title and scope, and for #2240.** By the
caller-awareness test, both `document_extract`'s map phase *and* #2240's
ingestion pipeline (extract → enrich → vectorise → publish, invisible to the
caller, who only sees "ingest this document") are **capability execution
flows**, not Application Workflows — even though #2240's GitHub issue title
says "workflow," for the same reason this RFC's first draft did. This RFC is
renamed and rescoped accordingly: it is about the **capability execution
flow** tier only. It does **not** define Fred's Application Workflow concept
(item 3 above) — see §9.

**Consequence for code, once Temporal is involved.** If a capability's
execution flow is escalated to Temporal (§4), the code will contain a
Temporal `Workflow` class (meaning 1) implementing a Fred capability
execution flow (this RFC's subject) — which is emphatically *not* a Fred
Application Workflow (meaning 3). This collision is real and will confuse
readers unless named explicitly at the point of use — e.g. a code comment or
naming convention distinguishing "Temporal Workflow (SDK primitive)" from
"Fred (Application) Workflow (product concept)" wherever both appear near
each other.

## 1. Problem

Fred has a documented pattern for **agent-level** execution flow — ReAct
agents for dynamic tool selection, explicit Graph agents for deterministic
multi-step flows with domain HITL (`AGENT_DESIGN.md` §5–6) — and a documented
pattern for durable orchestration in the **ingestion** domain (`TEMPORAL.md`,
and the live design track in #2240).

There is no equivalent pattern for a third site that already exists in the
code: **inside one capability's tool call**, when that single call is itself
a multi-step, partially-failing, potentially long-running pipeline —
a **capability execution flow** in the vocabulary of §0.
`document_extract` (§8.44, DOCREAD-01 Phase 2) is the first capability with
this shape. Its map phase — pack chunks into ~24k-char windows, run up to 3
concurrent LLM calls, retry 429s with exponential backoff+jitter — is real
orchestration logic, hand-written in-process with `asyncio.gather` and a
`asyncio.Semaphore`, entirely inside the HTTP request/response cycle of one
agent turn, and entirely invisible to (and rightly so) the agent that called
the tool.

`AUTHORING.md`'s mental model is manifest + `tools()`, with `middleware()` as
a narrow ReAct-only escape hatch for schema/prompt concerns. Neither model
names or addresses "this one tool call is itself a durable multi-step
pipeline." Every future capability with this shape (bulk enrichment, batch
generation, anything that maps an LLM call over N units of work) will either
duplicate `document_extract`'s bespoke orchestration or invent its own
variant, for lack of a shared, named pattern.

## 2. Current baseline (honest state)

- `document_extract`'s map phase (`extractor.py`) has bounded concurrency
  (`_MAP_CONCURRENCY=3`) and 429-aware retry (`_MAX_RETRIES=5`,
  exponential+jitter, respects `Retry-After`) — but a window that still fails
  after retries is silently dropped from the result
  (`extractor.py:207-217`, only a `logger.error` call). The caller receives no
  signal that the extraction is partial. For a capability whose entire value
  proposition is "exhaustive, zero-loss enumeration," this is a correctness
  gap, not just a robustness one.
- All of this orchestration is **in-process and non-durable**: a pod restart,
  deploy, or crash mid-extraction loses all in-flight progress with no resume
  — there is no checkpoint, because none was ever written outside the process
  heap.
- `TEMPORAL.md` already documents, at the platform level, exactly the
  criteria under which work should move from "one activity" to "many small
  activities": step-level retry, durable checkpoints across pod restarts,
  per-step operational visibility, precise cancellation. By its own stated
  criteria, `document_extract`'s map phase — a fixed, known-in-advance
  decomposition into N windows, each independently retryable — matches the
  "many small activities" column. It currently lives in the "single activity"
  column instead, which `TEMPORAL.md` reserves for highly dynamic,
  LLM-driven branching (exactly the opposite of what the map phase is).
- Issue #2240 (open, same author) is independently designing the identical
  pattern — a versioned, provider-neutral, Temporal-coordinated processing
  contract with idempotency keys, artifact references, and explicit
  ownership boundaries — for the ingestion pipeline. As noted in §0, #2240 is
  itself, by the caller-awareness test, a capability-execution-flow-shaped
  problem despite its "workflow" title. It gives this RFC a live reference
  contract and vocabulary to extend, per the repo's prime directive to extend
  rather than duplicate, not a blank page to design from scratch.

## 3. External validation (why now, not just "nice to have")

An independent cross-framework research pass (LangGraph, OpenAI Agents SDK,
Google ADK, Agno, AutoGen, Anthropic's tool-design guidance, plus long-context
literature — RULER, NoLiMa, LongBench Pro, Google's own Gemini long-context
docs) converges on two points relevant here, translated to Fred's vocabulary
rather than restated in full:

- **Deterministic control belongs in code, not in the LLM loop.** Every
  framework surveyed now separates "agent" (dynamic, LLM-decided) from
  "workflow" (predetermined, code-decided) as a first-class distinction —
  usually without their own version of the finer Capability-vs-Application-
  Workflow split §0 makes — and recommends moving mechanical loops, retries,
  pagination, and concurrency out of agent reasoning. Fred's capability model
  — one tool call, server-side orchestration underneath — already matches
  this at the *manifest+tools* layer. The gap identified is one layer deeper:
  the orchestration *inside* that one tool call (the execution flow) is still
  hand-rolled per capability, with no shared, named pattern or escalation
  path to durability.
- **A larger context window does not remove the need to partition
  exhaustive-recall work into bounded, verifiable units.** This independently
  confirms that `document_extract`'s map/pack/deterministic-union design (not
  an LLM reduce/summarize pass) is a good algorithmic match for a zero-loss
  requirement — see §9 (non-goals): this RFC does not propose changing that
  algorithm. What the same research flags as the actual weak point is
  resilience and honesty of partial results — silent degradation, no coverage
  signal, no durability across a restart — which is exactly what `TEMPORAL.md`
  already predicts for this shape of work and exactly what #2240 is solving
  in the neighboring ingestion domain.

## 4. The principle proposed

Formalize the **capability execution flow** as a named tier, distinct from
both agent-level execution (§0, meaning 2) and any future Application
Workflow layer (§0, meaning 3): **a capability whose tool call is internally
a multi-step, partially-failing, or long-running pipeline should have a
documented escalation path to a durable execution flow implementation,
backed by Temporal**, using `TEMPORAL.md`'s existing decision criteria and
reusing #2240's contract discipline (versioned request/result schema,
idempotency, explicit ownership boundaries) rather than inventing a parallel
mechanism.

Sketched, not specced — this RFC asks for the principle and the name, not
the full design:

- A capability's `tools()` can back a tool with a call into a durable
  execution flow (implemented, at the code level, as a Temporal `Workflow` —
  see §0's naming-collision note for why that code-level name must not leak
  into product vocabulary) instead of direct in-process orchestration, once
  `TEMPORAL.md`'s criteria are met (per-step retry, durable checkpoints,
  operational visibility, resumability needed).
- Below that threshold, in-process orchestration (today's `document_extract`
  shape) is not "wrong" — it is *unescalated*. This is an escalation path,
  not a mandatory rewrite of every capability.
- Independent of any Temporal work: the result contract should carry an
  explicit completeness signal (§10, item 1) so a capability can never
  silently claim exhaustiveness it did not achieve. This is a correctness fix
  that should not wait on this RFC's outcome.

## 5. Risks if not adopted

1. **Silent correctness drift on every "exhaustive" capability.**
   `document_extract`'s dropped-window behavior is real today; every future
   capability with this shape reproduces it absent a shared pattern.
2. **Duplicated, divergent orchestration code per capability author** —
   concurrency caps, backoff, windowing all hand-rolled per capability, the
   same "parallel code paths instead of one shared mechanism" failure mode
   `AUTHORING.md` already guards against for tool registration.
3. **No resilience to pod restarts/redeploys mid-extraction** — a deploy
   during a long extraction silently loses all progress today.
4. **A proven platform differentiator stays siloed.** Fred already has
   working Temporal-backed durability (ingestion) and is actively extending
   it (#2240). Confining it to one domain, when a second real use case
   (`document_extract`) already exists and matches the same criteria, is a
   missed opportunity to make it a general capability-authoring option rather
   than a one-off.
5. **No path to provider Batch APIs** (OpenAI Batch, Anthropic Message
   Batches — natively async, materially cheaper) for non-interactive, large
   extractions, because the port is structurally framed as "must complete
   within one synchronous turn."
6. **Continued vocabulary drift.** Without a named, adopted distinction,
   the next engineer to build a multi-step capability — or the next RFC —
   will reach for "workflow" again by default (as this RFC's own first draft
   did), re-creating the ambiguity §0 exists to close.

## 6. Impact on existing contracts

- `RUNTIME-EXECUTION-CONTRACT.md` §8.44 (`DocumentExtractionPort`) would gain
  a dated amendment if/when this becomes a spec — an explicit status/coverage
  field on `DocumentExtractionResult` at minimum, independent of the Temporal
  question.
- `TEMPORAL.md` is not changed by this RFC — its decision framework is
  applied to a new site, not amended. Its existing use of capital-W
  `Workflow` (the Temporal SDK primitive) is unaffected and, per §0, should
  stay scoped to that meaning only.
- `AUTHORING.md` would gain a new documented shape ("execution-flow-backed
  tool," explicitly not named "workflow") alongside `tools()`/`middleware()`,
  if approved — including the terminology table in §0, since capability
  authors are exactly the audience that needs the distinction.
- `AGENT_DESIGN.md` §6 ("Business Workflow Agents (Explicit Graphs)") is
  **not changed** by this RFC, but §0 flags a naming tension worth a future
  look: that section names an *Agent template* "Workflow," which is meaning
  (2) in §0's table, not meaning (3). Reconciling that name is out of scope
  here — see §8, open question 6.
- No wire/OpenAPI change is proposed by this RFC alone.

## 7. Alternatives considered

- **Fix only the correctness bug (status/coverage), no Temporal escalation
  path.** Rejected as the *sole* answer: it fixes honesty, not durability,
  resumability, or cost — leaves risks 2–5 (§5) unaddressed indefinitely. Not
  rejected as a first step — see §10, item 1.
- **Route all capability-internal orchestration through Temporal
  unconditionally.** Rejected: most capabilities (a single search call, a
  single summarize call) do not need it; `TEMPORAL.md`'s own criteria argue
  for selective escalation, not a blanket requirement.
- **Wait for #2240 to land, then copy its pattern verbatim.** Accepted as
  sequencing, not rejected outright: #2240's contract is the right reference
  to imitate, and the two tracks should converge rather than diverge. But
  capability calls are turn-time and HTTP-latency-bound (§8.43/§8.44) while
  ingestion is offline/async by nature — the transport story will differ even
  where the Temporal-usage doctrine doesn't, so this cannot be a pure copy.
- **Keep calling this a "Workflow tier" (the original draft).** Rejected on
  review: it reuses a word already carrying two other meanings in this repo
  (§0), and specifically the one — "explicit composition of independently-
  meaningful steps" — that this RFC's subject does not have. "Capability
  execution flow" is longer but unambiguous.

## 8. Open questions (for developer decision before any implementation)

1. Should the status/coverage correctness fix ship independently and
   immediately, ahead of any Temporal work? **Recommendation: yes** — it is a
   bug fix, not a design question, and should not be gated on this RFC.
   (Tracked as a near-term recommendation, §10 — not a new GitHub issue yet.)
2. What latency/size threshold separates "stay in-process" from "escalate to
   a durable execution flow," and does it belong in `AUTHORING.md` as author
   guidance, or should the runtime measure and decide dynamically?
3. Should an execution-flow-backed tool call block the agent turn
   synchronously (await the durable execution), or should Fred's existing
   HITL/interrupt machinery (already used for domain Graph agents,
   `AGENT_DESIGN.md` §6) be reused so the agent can "check back later" —
   converging capability-internal long-running work with the existing resume
   mechanism instead of inventing a second async-wait path?
4. Does this converge with #2240's request/result contract (versioned schema,
   idempotency key, artifact references), or does turn-time capability work —
   running under an already-authorized agent instance, not an offline
   document UID — need its own, lighter contract?
5. Should provider Batch APIs (OpenAI/Anthropic) be a second escalation tier
   below Temporal, for non-interactive/latency-insensitive extractions, or
   out of scope until a concrete non-interactive use case exists?
6. **New.** Should `AGENT_DESIGN.md` §6's "Business Workflow Agents (Explicit
   Graphs)" be renamed or reconciled once/if Fred designs a real Application
   Workflow layer (§0, meaning 3; §9)? Today it names an Agent template, not
   a composition of Agents+Capabilities+Services — worth revisiting once that
   layer has an owner, not blocking this RFC.

## 9. Non-goals

- **Not** proposing to change `document_extract`'s map/pack/dedupe algorithm.
  The external research (§3) independently confirms that structure — map +
  deterministic union, never an LLM reduce/summarize pass — is a good match
  for a zero-loss requirement. This RFC is about the execution substrate
  underneath the algorithm, not the algorithm.
- **Not** proposing a new agent-level execution category. Fred already has
  ReAct and explicit Graph agents (`AGENT_DESIGN.md` §6); this is about what
  happens *inside one capability's tool call*, a different layer entirely.
- **Not** designing Fred's Application/Business Workflow layer (§0, meaning
  3 — the bid example: extract → analyse → query catalogue → build matrix →
  store, composing Agents, Capabilities, and Services with independent
  step-level retry/observability/branching). That is a distinct, larger, and
  currently undesigned concept in Fred. This RFC only clears the vocabulary
  so that future layer, whenever specced, does not inherit the ambiguity
  fixed here. It deserves its own RFC when there is a concrete use case
  driving it (the bid-compliance example is a candidate).
- **Not** committing to any specific Temporal activity/execution-flow
  decomposition. Sketch only (§4) — real design is a follow-up scoped GitHub
  issue if the principle is approved.
- **Not** a positioning or marketing document. §3 exists to ground "why now,"
  not to produce publishable copy.

## 10. Near-term recommendations (independent of this RFC's outcome)

These four items came out of the same research pass but do not require the
Temporal decision above — listed here for future triage, not opened as
issues yet, per developer instruction:

1. **Explicit completeness signal.** Replace `document_extract`'s silent
   window-drop with a result status (`COMPLETE` / `PARTIAL` / `TRUNCATED` /
   `FAILED`) plus `windows_processed / windows_total` coverage, so a caller
   can never be told "0 items found" when it actually means "0 items found
   in the 88% of the document that was inspected." Bug-fix-shaped; see §8
   item 1.
2. **Provenance before de-dup.** Today's reduce concatenates + de-duplicates
   case-insensitively on the extracted string alone. Attaching per-occurrence
   provenance (window id / source offset) before de-dup would let a
   downstream consumer distinguish "same requirement stated twice" from "two
   distinct occurrences that happen to read identically" instead of
   collapsing that distinction irreversibly.
3. **Provider Batch API as an optional non-interactive backend.** For large,
   non-urgent extractions, OpenAI Batch / Anthropic Message Batches API
   offer native async queuing at roughly half the per-token cost — worth
   evaluating as a second escalation tier once open question 5 (§8) has an
   answer and a concrete non-interactive use case exists.
4. **An internal exhaustive-recall benchmark.** General long-context
   benchmarks (RULER, NoLiMa, LongBench Pro, NeedleBench) measure retrieval
   of one or a few needles, not "recover all N of N known items." The metric
   that matters for `document_extract`'s actual promise is
   `P(all expected items recovered)`, which degrades multiplicatively with
   per-item miss rate (e.g. 99% per-item recall over 100 independent items is
   only ~37% chance of recovering all 100) — a metric no existing public
   benchmark reports, and one Fred could own.

---

**Decision requested:** approve (a) the terminology in §0 — Agent /
Capability (execution flow) / (Application) Workflow — as Fred's vocabulary
going forward, so it can be folded into `AUTHORING.md` and referenced by
future RFCs instead of re-litigated; and (b) the *principle* (§4) that
capability-internal orchestration should have a documented escalation path
to a Temporal-backed execution flow, reusing `TEMPORAL.md`'s existing
criteria and #2240's contract discipline as precedent — so a scoped GitHub
issue can be opened to design it. Separately, and regardless of this RFC's
outcome: item 1 in §10 (completeness signal) should be tracked and fixed as
a correctness bug on its own.

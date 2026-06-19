# ISSUE-005 - Redundant tool-calling with reasoning models in the Fred agentic loop

Status: open (investigation complete; implementation deferred)
Owner: TBD — dedicated engineer next week
Target window: agent quality / runtime hardening before production ramp

> Root-cause analysis, state-of-the-art survey, and recommended long-term solution.
> Scope: LangGraph ReAct agent on Mistral `mistral-small-2603` (`reasoning_effort: high`)
> via OpenAI-compatible `ChatOpenAI`.

---

## 1. Executive summary

After switching Fred's tool-calling ReAct agent from `mistral-medium` (no reasoning) to `mistral-small` with `reasoning_effort: high`, the agent began emitting the **same tool call with byte-identical arguments 3–5 times in a row** within a single user turn before finally answering. The repeated calls return identical results and add no information — pure wasted latency and tokens.

The root cause is **not** a Fred-specific bug, a Mistral quirk, or simple model misbehaviour. It is a now-well-understood, industry-wide failure mode of the reasoning-model era:

> When a reasoning model calls a tool, it pauses an *unfinished* reasoning process. The provider-native reasoning block is effectively a **"save state."** If that block is not threaded back into the model on the next loop step, the model wakes up having *forgotten why it called the tool*, re-derives the same plan from scratch, and re-issues the identical call. This repeats until some other condition forces it to answer.

Fred currently **strips** the reasoning blocks between loop steps (a correct workaround for a *different* problem — Mistral's HTTP 422 on replayed raw reasoning), and the client library in use (`langchain-openai`'s `ChatOpenAI`) **cannot carry the reasoning field anyway**. The combination guarantees the amnesia-and-reloop behaviour. `reasoning_effort: high` amplifies the severity but is not the cause.

Every mature agent framework (Google ADK, Pydantic AI, the OpenAI Agents SDK, Agno, and others) hit this exact bug during 2025–2026 and converged on the same fix: **thread the reasoning state verbatim within an open tool loop, and strip it only once the turn has closed.** They differ mainly in how cleanly they model it.

**Recommended long-term solution (detailed in §6):** migrate Fred's *model-access layer* (not its orchestration) off bare `ChatOpenAI` to a client that models reasoning as a first-class, provider-scoped message part — **Pydantic AI** is the best-engineered reference for Fred's exact OpenAI-compatible-via-`base_url` Mistral setup — while keeping LangGraph for orchestration. Pair this with a permanent structural guardrail (tool-call de-duplication + per-turn iteration cap), which even vendor-built frameworks still require.

---

## 2. The symptom, precisely

**Setup**

- Tool-calling ReAct agent in a LangGraph loop with a single retrieval tool (`knowledge_search`).
- Model: Mistral `mistral-small-2603`, `reasoning_effort: high`, reasoning-enabled (responses interleave provider-native reasoning/"thinking" blocks with the answer).
- Access: LangChain `ChatOpenAI`, `base_url: https://api.mistral.ai/v1` (OpenAI-compatible endpoint).

**Observed behaviour**

For a simple single-topic question, in one user turn the model emits e.g. `knowledge_search(query="X", top_k=5)` four times in a row with identical arguments, re-emitting near-identical reasoning each round, then finally answers. Tool results are identical across the repeats.

**Trigger**

The behaviour appeared **only** after switching the profile from `mistral-medium` (no reasoning) to `mistral-small` with `reasoning_effort: high`.

**Known constraint already in place**

Before replaying the transcript on each loop step, Fred **strips the provider-native reasoning blocks** from prior assistant messages, because Mistral's OpenAI-compatible endpoint rejects replayed *raw* reasoning with **HTTP 422** (`"content should be a valid string"`). Assistant messages therefore keep their `tool_calls` but lose their reasoning content between steps.

---

## 3. Root-cause analysis

### 3.1 Primary cause — broken reasoning continuity across loop steps

From the model's perspective, a tool-use loop is **one assistant turn that has not finished yet**. When the model emits `[reasoning] + [tool_call]`, it has paused mid-thought to wait for external information. When the tool result returns, it expects to **continue building the same response** from where its reasoning left off.

This is documented identically across every major provider:

- **Anthropic:** during tool use you must pass thinking blocks back to maintain reasoning continuity; you cannot toggle thinking mid-turn, including during tool-use loops. When tool results return, the model continues building the existing response — which is *why* the thinking block must be preserved.
- **Google (Gemini):** thought signatures are encrypted representations of the model's internal thought process that preserve reasoning state across multi-turn/multi-step conversations. When a thinking model calls a tool it pauses its reasoning; the signature is a "save state" that lets it resume. Without it, the model "forgets" its reasoning during tool execution.
- **MiniMax / LiteLLM / others:** in multi-turn function-call conversations the full model response — *especially the internal reasoning fields* — must be appended to history to maintain continuity of the reasoning chain.

When Fred strips the reasoning, each loop step the model wakes up without the chain of thought that justified the tool call. It sees: the user question + a tool call it no longer remembers deciding to make + a tool result. It re-derives the same plan (hence the **near-identical re-emitted reasoning**) and re-issues the **byte-identical call**. The community name for this is **"reasoning drift"**: the agent starts a multi-step task, calls a tool, then forgets why it asked once results return, because the API is stateless and the model discards its train of thought the moment it emits a function call.

**This is the dominant cause.**

### 3.2 Why `mistral-medium` never showed it

`mistral-medium` emitted no reasoning blocks, so there was nothing to strip and nothing to break. The pathology can only appear once reasoning is enabled — which is exactly why the profile switch surfaced it. The bug was latent in the loop architecture all along; the non-reasoning model simply never exercised it.

### 3.3 Contributing amplifier — `reasoning_effort: high`

High effort produces a long thinking chunk every round, making each re-derivation more elaborate and more likely to re-commit to the same action. Mistral recommends `high` for agentic/code use cases — **but that guidance assumes the reasoning is being threaded.** In a broken-continuity setup, `high` actively worsens the loop and inflates token cost per redundant step. This is an amplifier, not the root cause.

### 3.4 The delivery vector — `ChatOpenAI` cannot carry the field

Fred's `ChatOpenAI` + `base_url` setup **cannot thread the reasoning even if Fred wanted to.** `langchain-openai`'s `ChatOpenAI` is documented to target official OpenAI API specifications only; non-standard fields added by third-party providers (`reasoning_content`, `reasoning`, `reasoning_details`) are **not extracted or preserved**. For providers reached via `base_url` (OpenRouter, vLLM, DeepSeek, Mistral, …) the library explicitly recommends a provider-specific package instead.

Consequently:

1. On the way **in**, LangChain silently drops Mistral's `reasoning_content` — it never reaches Fred's `AIMessage`. (Tracked in LangChain issues #34706, #35059, #31326, #34328.)
2. On the way **out**, Fred has no clean, well-formed reasoning to replay — only the raw string form, which is what produced the 422 in the first place.

So Fred's 422-driven stripping is a rational response to a constraint that bare `ChatOpenAI` imposes. **The 422 and the re-loop are two symptoms of the same missing capability: structured, provider-scoped reasoning round-tripping.**

### 3.5 Cause ranking

| # | Factor | Role | Evidence |
|---|--------|------|----------|
| 1 | Stripping reasoning blocks between loop steps | **Root cause** | Anthropic / Gemini / MiniMax / LiteLLM docs; Mistral Magistral model card |
| 2 | `ChatOpenAI` drops `reasoning_content` | **Enabling vector** (makes the correct fix impossible without changing client) | `langchain-openai` docs; LangChain issues #34706, #35059, #34328 |
| 3 | `reasoning_effort: high` on a small model | **Amplifier** | Mistral reasoning docs |
| 4 | Mistral-specific small-model behaviour | **Minor** | n/a — loop is structural, not provider-specific |

---

## 4. State of the art: how mature frameworks handle this

The reassuring meta-point first: **this is an industry-wide growing pain of the reasoning-model transition, not a Fred or Mistral mistake.** Within roughly one year, Google ADK (Python *and* JS), the Vercel AI SDK, LiveKit agents-js, LibreChat, the OpenAI Agents SDK, and LangChain *all* shipped the identical "dropped the reasoning block → model re-loops / 400 / 422" bug and had to fix it. The Gemini 3 transition made reasoning round-tripping *mandatory* (it was optional in Gemini 2.5), which flushed the latent bug out of every framework at once.

### 4.1 The conceptual model everyone converged on

Providers moved from **implicit / stateless** reasoning (the model re-evaluates context every turn) to **explicit, threaded** reasoning state that the client must pass back. The same idea appears under three vendor names:

| Vendor | Name for the threaded reasoning state | Form |
|--------|---------------------------------------|------|
| Anthropic | `thinking` block | Readable text + signature |
| Google | Thought signature | Encrypted opaque token, per content part |
| OpenAI | Reasoning item / encrypted reasoning | `id` + encrypted content |
| Mistral | `reasoning_content` | Tokenized thinking chunks |

The shared rule: **within an open tool loop, replay the reasoning verbatim; once the turn closes (final answer produced), you may discard it.**

### 4.2 Framework-by-framework

**Google ADK — first-class, but retrofitted, and still leaks.**
ADK preserves thought signatures and replays them automatically. Yet the migration was painful and instructive: even ADK's *native* Gemini integration failed with a `400 missing thought_signature` on the 5th content block after multiple tool calls (adk-python #3705; adk-js #149). The same drop-the-signature bug appeared in the Vercel AI SDK, LiveKit agents-js, and LiteLLM's proxy, each fixed in its own PR. **Lesson for Fred:** even the model vendor's own framework had to special-case this, and the bug recurs at every layer (SDK, proxy, agent framework). A structural guardrail is therefore non-optional.

**Pydantic AI — the cleanest data model; the best reference for Fred's exact case.**
Reasoning is a first-class `ThinkingPart` carrying a `signature` and `provider_name`. The documented rule: thinking parts must be round-tripped back **to the same provider** in subsequent requests (signatures are never sent cross-provider). Critically for Fred's OpenAI-compatible-via-`base_url` situation, Pydantic AI exposes explicit knobs:

- `openai_chat_thinking_field` — configure which custom field carries native thinking for an OpenAI-compatible provider.
- `openai_chat_send_back_thinking_parts` — send the thinking parts back unchanged for caching / interleaved-thinking benefits.

That second flag is precisely the lever Fred is missing in bare `ChatOpenAI`. Pydantic AI also documents the failure mode of replaying a mismatched history (`"Item 'rs_123' of type 'reasoning' was provided without its required following item."`), which is the same class of error as Fred's 422. In effect, **Pydantic AI turns the strip-vs-thread decision Fred currently hand-rolls into a configuration flag.**

**OpenAI Agents SDK — the cautionary tale that matches Fred's stack most closely.**
When driving non-OpenAI reasoning models through LiteLLM, the SDK's message-conversion pipeline stripped provider-specific thinking blocks, producing the Anthropic-side mirror of Fred's Mistral 422 — a 400 demanding the assistant message start with a thinking block before the `tool_use` (openai-agents-python #678). The diagnosis is identical to Fred's: the conversion chain `input item → chat completion → litellm → output item` loses the provider-specific message properties that LiteLLM itself preserves. The fix: LiteLLM retains `thinking_blocks`, and you re-attach them to the assistant message on replay.

**Agno — reasoning-first by design; offers a useful alternative architecture.**
Agno's loop retains reasoning as part of the run trajectory rather than discarding it between steps (its `RunOutput` carries content, messages, *reasoning traces*, and metrics), so continuity is preserved structurally. Agno also offers an *orthogonal* approach worth serious consideration: **reasoning-as-tools** (`ThinkingTools`, `ReasoningTools` with `think()` / `analyze()`). This sidesteps native-reasoning-block threading entirely by making the reasoning a regular tool call that lives in ordinary message history — no special signature plumbing can drop it. The same idea appears in the "Think-Augmented Function Calling" research line.

**LangGraph / LangChain — Fred's current stack is the weak link, and that is the real story.**
The problem is not LangGraph's loop; it is that `ChatOpenAI` is *documented* not to carry the reasoning field for `base_url` providers. LangChain knows this is a gap and is actively building a centralized `reasoning.py` normalizer in `langchain-openai` to handle `reasoning_content` / `reasoning` / `thinking` across sync, async, and streaming paths (tracked maintainer issue #34328). LangChain also documents an escape hatch: for non-OpenAI endpoints via `base_url`, if agent loops fail after tool calls, try `ChatOpenAI(..., use_responses_api=True, use_previous_response_id=True)`. The `use_previous_response_id` route offloads state-threading to the provider's server side (pass an ID instead of replaying reasoning) — **but it only works if Mistral's endpoint supports that semantics; most OpenAI-compat shims do not, so it must be verified before relying on it.**

### 4.3 The three recurring patterns

1. **Thread reasoning verbatim inside the open loop; strip on closed turns.** The dominant solution and every mature framework's default. Gemini even exposes the cost/continuity trade-off as a choice: preserving thoughts raises input-token count, so for simple queries you *may* clear them — the same trade-off Mistral's model card hands Fred, but exposed as a flag rather than hand-rolled transcript editing.
2. **A typed reasoning part with provider-scoped round-tripping** (Pydantic AI's `ThinkingPart(signature, provider_name)`). Signatures go back only to the same provider, never cross-provider. Any in-house threading must honour this invariant.
3. **When native threading is too fragile, demote reasoning to a tool call** (Agno's `ThinkingTools`). For a small model behind a finicky OpenAI-compat endpoint, this can be *more* robust than fighting `reasoning_content` serialization.

---

## 5. Immediate mitigations (if a stopgap is wanted before the real fix)

These are deliberately listed separately from the long-term recommendation. They reduce pain without changing architecture and can ship in hours.

1. **Tool-call de-duplication + iteration cap (highest ROI, ship first, keep forever).**
   Before dispatching a tool call, hash `(tool_name, canonical_args)` against calls already made *this turn*. If already executed, short-circuit — return the cached result with a synthetic note, or force-stop the loop and require the model to answer. Add a hard per-turn iteration cap. This neutralizes the *symptom* regardless of root cause and is provider-agnostic. **Even Google's own ADK still ships missing-signature bugs at the 5th tool call, so this guardrail is something every framework needs — not a workaround for an immature one. It should remain permanently even after the root-cause fix lands.**
   *Trade-off:* treats the symptom, not the cause; Fred still pays for redundant *reasoning* tokens within a step even when the duplicate dispatch is suppressed.

2. **Lower `reasoning_effort` to `medium` for the agent loop (same-day).**
   Shrinks each re-derived thinking chunk, reducing both wasted tokens and the tendency to elaborately re-commit.
   *Trade-off:* lowers reasoning quality on genuinely hard multi-step retrieval; dampens but does not fix the loop.

3. **`parallel_tool_calls = false` + conditional `tool_choice` (permanent hardening).**
   Keep tool calls sequential. After the first tool result, if the *next* requested call is a duplicate, force `tool_choice="none"` for that step so a duplicate call is structurally impossible, then let the model answer.
   *Trade-off:* a blunt forced-`none` can block a legitimately-needed second, differently-parameterized search; gate it on duplicate-detection (which collapses into mitigation #1).

**Suggested stopgap sequence:** ship #1 immediately (and keep it) → set #2 to `medium` the same day → keep #3's `parallel_tool_calls=false` on permanently.

---

## 6. Recommended long-term solution

> **Migrate Fred's model-access layer off bare `ChatOpenAI` to a client that models reasoning as a first-class, provider-scoped message part — keeping LangGraph for orchestration — and invert the reasoning-handling rule from "always strip" to "thread within the open loop, strip on closed turns." Pydantic AI is the recommended target client for Fred's exact Mistral-over-OpenAI-compatible setup. Retain the de-duplication + iteration-cap guardrail permanently.**

### 6.1 Why this, and why not the alternatives

The decision space has four realistic options. The recommendation weighs them against Fred's constraints: open-source Apache-2.0 platform, LangGraph orchestration already in place, Mistral via OpenAI-compatible `base_url`, sovereign-deployment posture, and a small team that values transparency and auditability.

| Option | What it fixes | Effort | Long-term fit for Fred | Verdict |
|--------|---------------|--------|------------------------|---------|
| **A. Pydantic AI as model-access layer, keep LangGraph orchestration** | Root cause: first-class `ThinkingPart` round-tripping with provider scoping; `openai_chat_thinking_field` + `openai_chat_send_back_thinking_parts` made for this exact case | Medium | **Best** — cleanest data model, explicit knobs, transparent, multi-provider-ready | **Recommended** |
| **B. Route through LiteLLM, re-attach `thinking_blocks` on replay** | Root cause: LiteLLM preserves `thinking_blocks`; also normalizes Mistral param quirks (`max_tokens` vs `max_completion_tokens`) | Medium | Good — but adds a proxy dependency and another layer that has *itself* shipped signature-dropping bugs | Strong fallback |
| **C. Reasoning-as-tools (Agno pattern), retrofitted into Fred** | Root cause: reasoning lives in ordinary message history, nothing to drop | Medium-High | Good and robust, but changes the agent's interaction model and loses native reasoning-trace surfacing | Viable if A/B prove fragile |
| **D. Wait for `langchain-openai` to land the reasoning normalizer (#34328)** | Root cause, eventually | None now | Uncertain timeline; keeps Fred on the weakest-link client | Not recommended as the plan |

### 6.2 Why Pydantic AI specifically

- It is the **best-engineered reference implementation for Fred's exact situation**: native reasoning over an OpenAI-compatible endpoint reached by `base_url`. The `openai_chat_thinking_field` and `openai_chat_send_back_thinking_parts` settings exist precisely so you can name Mistral's reasoning field and choose to send it back unchanged.
- Reasoning is a **typed, first-class `ThinkingPart`** with `signature` + `provider_name`, enforcing the "same-provider only" invariant for free — exactly the invariant any in-house solution would have to reinvent and could get subtly wrong.
- It turns Fred's current **hand-rolled strip-vs-thread transcript editing into a configuration choice**, which is more auditable and less brittle — valuable given Fred's governance/sovereignty posture.
- It is **provider-portable**: the same `ThinkingPart` abstraction works if Fred later adds Anthropic, OpenAI, or Gemini models, each with its own reasoning format. This matters for an open platform that should not hard-bind to Mistral.
- **LangGraph stays.** This is a swap of the *model client*, not the *orchestrator*. Fred's graph, state, HITL, and tool wiring are unaffected. (If desired, Pydantic AI can also run as the node-level model inside a LangGraph node.)

### 6.3 The architectural rule to encode

Replace "always strip reasoning before replay" with:

```
For each assistant message in the transcript being replayed:
  if the message belongs to the CURRENTLY-OPEN assistant turn
     (i.e. its tool calls are still being resolved this turn):
        KEEP its reasoning block, round-tripped verbatim,
        in the provider's required format, scoped to the same provider.
  else (the turn has CLOSED — a final answer was produced):
        STRIP its reasoning block to save tokens.
```

This is the single rule that every mature framework implements. Pydantic AI implements it for you; if Fred ever hand-rolls it (option B/C), this pseudocode is the spec.

### 6.4 Guardrail stays regardless

Keep the **de-duplication + per-turn iteration cap** from §5.1 permanently, *in addition to* the root-cause fix. The evidence that even vendor-built frameworks (ADK) still leak missing-signature bugs at the 5th tool call means a structural loop-breaker is defense-in-depth that belongs in any production agent loop, not a temporary patch.

---

## 7. Suggested plan for next week's engineer

A pragmatic sequence that de-risks incrementally:

1. **Reproduce + instrument (0.5 day).** Log every outbound assistant message and confirm reasoning is absent on replay and tool-call args are byte-identical across repeats. Capture a clean trace as the regression fixture.
2. **Ship the guardrail (0.5 day).** Implement `(tool_name, canonical_args)` de-dup + iteration cap in the LangGraph loop. This stops the bleeding immediately and is kept forever. Set `reasoning_effort` to `medium` and `parallel_tool_calls=false` as interim hardening.
3. **Spike Pydantic AI on the Mistral endpoint (1 day).** Validate that `openai_chat_thinking_field` + `openai_chat_send_back_thinking_parts` correctly capture and round-trip `reasoning_content` against `https://api.mistral.ai/v1`, and that the 422 disappears when reasoning is replayed in the *structured* (not raw-string) form. **Verify the exact accepted reasoning-replay format against Mistral's current Chat Completions reference and `mistral-common`**, since Mistral's reasoning serialization (tokenized thinking chunks) has changed across model generations.
4. **Integrate as the model-access layer (1–2 days).** Swap the model client behind Fred's existing LangGraph nodes. Encode the §6.3 rule. Keep orchestration untouched.
5. **Regression-test (0.5 day).** Confirm the single-topic question now produces **one** `knowledge_search` call, then an answer. Restore `reasoning_effort: high` and confirm it no longer re-loops (it shouldn't, once reasoning is threaded). Keep the guardrail and de-dup in place.
6. **Fallback if the spike fails (contingency).** If Pydantic AI's Mistral path proves fragile, route through **LiteLLM** and re-attach `thinking_blocks` on replay (option B), or adopt the **reasoning-as-tools** pattern (option C).

**Estimated total: ~3–5 engineer-days**, front-loaded so that the symptom is gone on day one and the root cause is closed by end of week.

---

## 8. Key references

*Provider documentation on threading reasoning through tool loops*
- Anthropic — Building with extended thinking (thinking-block preservation during tool use)
- Google Cloud — Thought signatures / Thinking (encrypted reasoning state, mandatory round-trip on Gemini 3)
- Google AI for Developers — Thought Signatures (clearing vs. preserving; token-cost trade-off)
- Mistral — Reasoning docs (`reasoning_effort` surfacing; `high` recommended for agentic) and Magistral model card (explicit "keep reasoning traces in multi-turn vs. keep only final response" choice)
- LiteLLM — "Thinking / Reasoning Content" (re-attach `thinking_blocks` on replay)
- MiniMax — Tool Use & Interleaved Thinking (return full response incl. reasoning fields each turn)

*Framework handling and the cross-ecosystem bug pattern*
- Pydantic AI — Thinking docs; `pydantic_ai.messages` (`ThinkingPart`, `signature`, `provider_name`, same-provider round-trip); `openai_chat_thinking_field`, `openai_chat_send_back_thinking_parts`
- LangChain — `ChatOpenAI` reference (third-party reasoning fields not preserved; `use_responses_api` / `use_previous_response_id` escape hatch); issues #34706, #35059, #31326, #34328
- OpenAI Agents SDK — issue #678 (LiteLLM reasoning-block loss → 400)
- Google ADK — adk-python #3705, adk-js #149 (missing `thought_signature` after multiple tool calls); parallel fixes in Vercel AI SDK, LiveKit agents-js, LibreChat
- Agno — Reasoning overview; `ThinkingTools` / `ReasoningTools` (reasoning-as-tools alternative)

*Note on sourcing:* several specifics (the exact 422-on-replayed-reasoning behaviour, `reasoning_effort` model-gating, and per-generation reasoning serialization) are documented as much in third-party issue trackers and integration docs as in Mistral's own pages. The accepted reasoning-replay format must be re-verified against Mistral's current Chat Completions reference and `mistral-common` before implementation, because it has changed across model generations.

---

## Promotion
Promoted to: none yet.
Notes: Full root-cause analysis and recommended solution captured above. The de-duplication +
per-turn iteration-cap guardrail (§5.1) can ship independently of any RFC. Promote to an RFC when
the model-access-layer change (reasoning round-tripping / Pydantic AI, §6) is approved for
implementation. Related: `docs/swift/rfc/AGENT-THINKING-API-RFC.md`,
`docs/swift/issues/ISSUE-004-v2-history-windowing-policy-inconsistent-and-hard-coded.md`.
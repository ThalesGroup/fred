# Deep agent execution RFC

**Status:** Proposed
**Task ID:** RUNTIME-10 (dispatch), RUNTIME-11 (web search + Report Generator, depends on RUNTIME-10)
**Owner:** TBD
**Created:** 2026-07-09

## Problem

`ExecutionCategory.DEEP`, `DeepAgentDefinition`, and `DeepAgentRuntime` have existed in
`fred-sdk`/`fred-runtime` since the RUNTIME-09 prompt-suffix work (`RUNTIME-EXECUTION-CONTRACT.md`
§8.12), but no agent pod has ever registered a concrete `DeepAgentDefinition`. The capability is
fully implemented and completely unreachable.

It is also silently broken. `_iterate_runtime_event_payloads` in
`libs/fred-runtime/fred_runtime/app/agent_app.py` only branches on
`isinstance(definition, GraphAgentDefinition)`, falling through to `ReActRuntime` for everything
else. Because `DeepAgentDefinition` subclasses `ReActAgentDefinition`, the first concrete deep
agent anyone registers would silently execute on `ReActRuntime` instead of `DeepAgentRuntime` —
`execution_category: ExecutionCategory.DEEP` would be set on the definition and ignored at
dispatch time. No test catches this: existing `agent_app.py` tests monkeypatch
`_iterate_runtime_event_payloads` wholesale, so the real `isinstance` chain is never exercised.

This surfaced via external PR [#1821](https://github.com/ThalesGroup/fred/pull/1821), which tried
to fix the dispatch gap and, in the same PR, shipped the first real deep agent — a DuckDuckGo
web-search-backed "Report Generator". Reviewing that PR found two things worth separating:

1. The dispatch fix itself is right in spirit (deep agents need to reach `DeepAgentRuntime`) but
   wrong in shape (another `elif isinstance(...)` branch ordered before the ReAct fallthrough —
   the same fragile, comment-enforced-ordering pattern that produced the gap in the first place).
2. The new web-search tool bypasses the existing in-process MCP toolkit registry
   (`inprocess_toolkit_registry.build_inprocess_toolkit(provider, agent)`, already used by
   `kf_vector_search`) by adding a second, competing `inprocess_toolkit_factory` parameter to
   `create_agent_app`. Since a pod can only pass one factory, wiring this in for the `fred-agents`
   pod would drop `kf_vector_search` resolution for that pod — a working feature — and the two
   factory signatures have already drifted (single-arg vs. the current two-arg
   `(provider, agent)` protocol).

This RFC proposes making deep-agent execution genuinely usable at the root (dispatch), then
building the web search tool and Report Generator agent on top of the existing extension point
instead of a parallel one. `id-legend.yaml` has no entry covering either; `RUNTIME-EXECUTION-CONTRACT.md`
documents the prompt-suffix behavior of `DeepAgentRuntime` but not its dispatch contract at all.

## Proposed solution

### Phase 1 — RUNTIME-10: make Deep dispatch structural, not bolted-on

- Dispatch on `definition.execution_category` (already a typed `ExecutionCategory` field, already
  set correctly on every definition) instead of adding another `isinstance` branch. A lookup from
  `ExecutionCategory` to runtime class (or an equivalent single ordered check) makes
  subtype-before-supertype correctness structural rather than dependent on branch order and a
  comment.
- `DeepAgentRuntime` only overrides `build_executor` — its streaming/validation logic is otherwise
  identical to `ReActRuntime`. Share that block (e.g. a `_stream_react_style_events(executor,
  request, execution_config)` helper) between the Deep and ReAct paths instead of duplicating it,
  so a future fix to event validation or resume-payload handling can't be applied to one runtime
  and silently missed on the other.
- Add a dated `RUNTIME-EXECUTION-CONTRACT.md` §8.13 entry documenting the dispatch contract:
  which `ExecutionCategory` maps to which runtime class, and that Deep and ReAct share the
  transport/event layer by design (already stated in `deep_runtime.py`'s docstring, not yet in
  the contract doc).
- Add an offline test that constructs a real `DeepAgentDefinition` and asserts it dispatches to
  `DeepAgentRuntime` through the actual `_iterate_runtime_event_payloads` path — not a
  monkeypatched stand-in — closing the coverage gap that let the original bug ship unnoticed.
- `agent_app.py` is mid-refactor under `QUALITY-01`/R1b (router extraction, Simon/Dimitri, per
  `WORKPLAN.md`). Sequence this change with that split rather than editing the monolith in
  parallel.

### Phase 2 — RUNTIME-11: web search tool + Report Generator agent (depends on RUNTIME-10)

- Register a new in-process MCP toolkit provider (`web_search`, `ddgs`-backed, no API key) into
  the **existing** `inprocess_toolkit_registry.build_inprocess_toolkit(provider, agent)`
  mechanism, alongside `kf_vector_search` — not a new competing `inprocess_toolkit_factory`
  parameter on `create_agent_app`. This is the one extension point that already threads correctly
  through `mcp_runtime.py`.
- Add an `mcp-web-search` entry to `apps/fred-agents/config/mcp_catalog.yaml`
  (`transport: inprocess`, `provider: web_search`, `auth_mode: no_token`).
- Add the first concrete `DeepAgentDefinition` subclass, `ReportGeneratorDefinition`
  (`apps/fred-agents/fred_agents/report_generator.py`), registered in
  `apps/fred-agents/fred_agents/registry.py`, with `default_mcp_servers` referencing
  `mcp-web-search` plus the existing knowledge-flow text/corpus servers.
- Reuse a single pooled `DDGS` client instead of constructing a new one per tool call (per-call
  construction was flagged as wasted connection-setup work in a multi-query research turn).
- `apps/frontend/src/slices/agentic/agenticOpenApi.ts` needs `"deep"` added to `ExecutionCategory`
  via regeneration, not a hand-edit — the agentic-backend OpenAPI codegen path
  (`agenticOpenApiConfig.json` → `agentic-backend/openapi.json`) currently points at a
  nonexistent path with no Makefile target, so that gap needs a small fix first (see Open
  questions).

## Contract impact

- New dated entry `RUNTIME-EXECUTION-CONTRACT.md` §8.13 (Deep dispatch contract).
- The `inprocess_toolkit_registry` mechanism gets its first design-doc coverage — currently zero
  hits in any `docs/swift/design/` file despite being live code since `kf_vector_search` shipped.
- No new types and no frozen-contract shape changes: `ExecutionCategory.DEEP` and
  `DeepAgentDefinition` already exist. This closes a dispatch gap and adds a registry entry; it
  does not introduce new contract surface.

## Alternatives considered

- **Keep the isinstance-chain pattern** (add another `elif` before the fallthrough) — rejected:
  this is the exact pattern that produced the original bug, and it recurs for the next
  `ReActAgentDefinition` subtype someone adds.
- **Let the web-search tool bypass the existing toolkit registry**, as PR #1821 does — rejected:
  breaks `kf_vector_search` for the `fred-agents` pod today, and creates two parallel,
  unreconciled provider-resolution mechanisms.
- **Ship Report Generator without fixing dispatch first** — rejected: would ship the same latent
  trap PR #1821 tried to patch locally, instead of fixing it at the root once for every future
  deep agent.

## Security and ReBAC requirements

- Web search results are public internet content injected into the agent's own context — no new
  authz surface, unlike e.g. `attachments.read_image` (RUNTIME-08), which is scoped by session/
  document ReBAC. No credentials or secrets are involved (`ddgs` is anonymous, no API key).
- Deep dispatch happens after execution-grant resolution, same point in the pipeline as ReAct and
  Graph today — `EXECUTION-GRANT-SECURITY-HARDENING-RFC` is unaffected.

## Implementation plan

1. RUNTIME-10 first: dispatch fix, shared streaming helper, contract doc entry, regression test.
   Coordinate timing with the `QUALITY-01`/R1b `agent_app.py` router-extraction split.
2. RUNTIME-11 after RUNTIME-10 lands: register `web_search` into the existing toolkit registry,
   add the MCP catalog entry, add `ReportGeneratorDefinition`, pool the `DDGS` client, regenerate
   `agenticOpenApi.ts` once its codegen path is fixed.
3. `make code-quality` / `make test` in `apps/fred-agents` and `libs/fred-runtime` before merge,
   per both items.

## Open questions

- Does the RUNTIME-10 dispatch change land inside or after the `QUALITY-01`/R1b split of
  `agent_app.py`? Needs a sequencing call from Simon/Dimitri.
- Is `ddgs` (DuckDuckGo scraping, no official API) an acceptable long-term production dependency,
  or should Report Generator support a pluggable search backend? Not blocking for Phase 1.
- Does the broken `agentic-backend` OpenAPI codegen path get its own fix-first item, or does
  `ExecutionCategory: "deep"` frontend visibility stay out of scope until a UI actually needs to
  render/filter on it?
- Owner assignment for both items — left `TBD` pending developer confirmation.

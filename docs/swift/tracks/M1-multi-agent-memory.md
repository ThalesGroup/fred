# Track: M1 — Multi-agent conversational memory

| Field | Value |
|---|---|
| Owner | Dimitri |
| Status | Core done (2026-05-05) — Phase F hardening open |
| RFC | [`docs/swift/rfc/MULTI-AGENT-MEMORY-RFC.md`](../rfc/MULTI-AGENT-MEMORY-RFC.md) |
| Backlog | [`docs/swift/backlog/MULTI-AGENT-MEMORY-BACKLOG.md`](../backlog/MULTI-AGENT-MEMORY-BACKLOG.md) |
| Blocked on | Swift branch commit (Dimitri) |

## What this track delivers

Graph agents (including `TeamAgent`) were stateless across turns — a user's second
question reached sub-agents with no knowledge of the prior exchange. M1 introduces
`ConversationTurn` / `ConversationalState` as general SDK contracts (not a TeamAgent
patch), a `build_turn_state` carry-forward hook, a `build_completed_state` persistence
hook, and `prior_turns` forwarding through both local and remote invocation paths.
The feature is runtime-transparent: agent authors declare `ConversationalState` in
their state schema and the history is carried, enriched in prompts, and depth-capped
automatically.

## Open items (Phase F — hardening)

- [ ] M1-F.1 — Isolate persisted graph/ReAct state per agent within a shared `session_id`
  (`fix/memory-agent-checkpoint-isolation`)
- [ ] M1-F.2 — Make `RemoteSseAgentInvoker` send public `RuntimeExecuteRequest` shape
  (`fix/remote-agent-runtime-execute-contract`)
- [ ] M1-F.3 — Remove duplicate `_AgentExecuteRequest` construction in local invoker
  (`refactor/local-agent-execute-projection`)
- [ ] M1-F.4 — Enforce `conversation_history_max_turns` in `TeamAgent.build_completed_state`
  (`fix/team-memory-history-cap`)

Recommended branch order: F.1 → F.2 → F.3 → F.4.

## Closed items

- [x] M1 Phase A — SDK primitives: `ConversationTurn`, `ConversationalState`, `build_turn_state`, `build_completed_state` (2026-05-05)
- [x] M1 Phase B — `TeamAgent` consumes primitives: `TeamState` inherits `ConversationalState`, prompt enrichment, `prior_turns` forwarding (2026-05-05)
- [x] M1 Phase C — Runtime enforcement: ReAct context injection, local + remote invoker `prior_turns` forwarding, graph runtime hooks (2026-05-05)
- [x] M1 Phase D — Integration validation: 28 offline tests; 3-turn manual validation confirmed (2026-05-05)
- [x] M1 Phase E — Documentation: RFC marked Implemented, `AGENTS.md` multi-turn section, `V2_AGENT_CREATION.md` pointer (2026-05-05)

## Notes

- The four F-branches must land on `swift` before M1 is fully closed in `id-legend.yaml`.
- M1-F.2 and M1-F.3 are a convergence pair: together they remove the last dual
  execution-seam paths introduced during the memory implementation.
- P1-F (token cost KPI) is a separate track that depends on M1 hardening being done
  first. Do not conflate the two.

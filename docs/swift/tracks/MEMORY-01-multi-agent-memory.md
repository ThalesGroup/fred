# Track: MEMORY-01 — Multi-agent conversational memory

| Field         | Value                                                                                                      |
| ------------- | ---------------------------------------------------------------------------------------------------------- |
| Owner         | Dimitri                                                                                                    |
| Status        | Core done (2026-05-05) — Phase F hardening open                                                            |
| Design        | [`docs/swift/design/MULTI_AGENT_MEMORY.md`](../design/MULTI_AGENT_MEMORY.md)                               |
| Hardening RFC | [`docs/swift/rfc/MULTI-AGENT-MEMORY-HARDENING-RFC.md`](../rfc/MULTI-AGENT-MEMORY-HARDENING-RFC.md)         |
| Backlog       | [`docs/swift/backlog/MULTI-AGENT-MEMORY-BACKLOG.md`](../backlog/MULTI-AGENT-MEMORY-BACKLOG.md)             |
| Blocked on    | Swift branch commit (Dimitri)                                                                              |

## What this track delivers

Graph agents (including `TeamAgent`) were stateless across turns — a user's second
question reached sub-agents with no knowledge of the prior exchange. MEMORY-01 introduces
`ConversationTurn` / `ConversationalState` as general SDK contracts (not a TeamAgent
patch), a `build_turn_state` carry-forward hook, a `build_completed_state` persistence
hook, and `prior_turns` forwarding through both local and remote invocation paths.
The feature is runtime-transparent: agent authors declare `ConversationalState` in
their state schema and the history is carried, enriched in prompts, and depth-capped
automatically.

## Open items (Phase F — hardening)

- [ ] MEMORY-02 — Isolate persisted graph/ReAct state per agent within a shared `session_id`
      (`fix/memory-agent-checkpoint-isolation`)
- [ ] MEMORY-03 — Make `RemoteSseAgentInvoker` send public `RuntimeExecuteRequest` shape
      (`fix/remote-agent-runtime-execute-contract`)
- [ ] MEMORY-04 — Remove duplicate `_AgentExecuteRequest` construction in local invoker
      (`refactor/local-agent-execute-projection`)
- [ ] MEMORY-05 — Enforce `conversation_history_max_turns` in `TeamAgent.build_completed_state`
      (`fix/team-memory-history-cap`)

Recommended branch order: F.1 → F.2 → F.3 → F.4.

## Closed items

- [x] MEMORY-01 Phase A — SDK primitives: `ConversationTurn`, `ConversationalState`, `build_turn_state`, `build_completed_state` (2026-05-05)
- [x] MEMORY-01 Phase B — `TeamAgent` consumes primitives: `TeamState` inherits `ConversationalState`, prompt enrichment, `prior_turns` forwarding (2026-05-05)
- [x] MEMORY-01 Phase C — Runtime enforcement: ReAct context injection, local + remote invoker `prior_turns` forwarding, graph runtime hooks (2026-05-05)
- [x] MEMORY-01 Phase D — Integration validation: 28 offline tests; 3-turn manual validation confirmed (2026-05-05)
- [x] MEMORY-01 Phase E — Documentation: as-built design reference, `AGENTS.md` multi-turn section, `V2_AGENT_CREATION.md` pointer (2026-05-05)

## Notes

- The four F-branches must land on `swift` before MEMORY-01 is fully closed in `id-legend.yaml`.
- MEMORY-03 and MEMORY-04 are a convergence pair: together they remove the last dual
  execution-seam paths introduced during the memory implementation.
- PROMPT-07 (token cost KPI) is a separate track that depends on MEMORY-01 hardening being done
  first. Do not conflate the two.

# RFC: Durable execution inside a capability

**Status:** proposed; no implementation approved by this RFC alone.
**ID:** CAPAB-EXEC-FLOW-01

## Question

Should a long-running capability tool call have an explicit path to durable
execution, with independent retries and persisted progress, instead of relying
entirely on the lifetime of one agent turn?

Example: exhaustive extraction from a large document may involve many model
calls. Restarting all of that work after one failure can be expensive. Temporal
is a candidate execution substrate, not a decision already made for capabilities.

## Boundaries and vocabulary

- **Agent:** owns the conversational turn and chooses tools; ReAct and explicit
  Graph agents remain the existing execution models.
- **Capability execution flow:** orchestration inside one capability's tool call.
- **Application workflow:** a larger business process composing agents,
  capabilities and services; designing this layer is outside this RFC.
- **Temporal workflow:** the SDK's durable orchestration primitive, not a synonym
  for any of the three product concepts above.

Knowledge Flow's existing [ingestion architecture](../design/INGESTION.md) is a
separate domain. Do not copy its per-file workflow hierarchy or extraction queues
into turn-time capabilities without establishing the required boundary.
Use the [Temporal decision guide](../platform/TEMPORAL.md) for general trade-offs.

## Proposed principle

Keep short operations in-process. Consider durable execution for operations whose
latency, restart cost or per-stage recovery requirements justify it. Persist large
inputs/results by reference and define idempotency, authorization and cancellation
before introducing another executor. Avoid exposing Temporal details in LLM-facing
tool signatures or duplicating the runtime's existing resume mechanism.

## Decisions still needed

1. What explicit size/latency/recovery threshold warrants durable execution, and
   who selects it: the capability author, configuration or the runtime?
2. Does the tool await completion, or reuse existing interrupt/resume behavior?
3. What request/result contract carries identity, idempotency, progress and artifact
   references while preserving the active agent instance's authorization?
4. Are provider batch APIs relevant for a concrete non-interactive use case, or
   outside the first implementation?
5. Does the vocabulary need reconciliation with the existing Graph-agent guide?

## Separate correctness checks

Before treating these as new work, compare them with the current extraction
contract and implementation: explicit completeness/coverage, provenance before
deduplication, and a benchmark measuring recovery of all expected items. Earlier
claims of silent truncation are not a reliable inventory of current defects.
These checks do not require approving durable execution.

## References

- [Capability authoring](../capabilities/AUTHORING.md)
- [Agent design](../design/AGENT_DESIGN.md)
- [Runtime execution contract](../design/RUNTIME-EXECUTION-CONTRACT.md)

No new agent category, page-level ingestion split, provider pricing promise or
specific Temporal decomposition is approved here. A scoped implementation plan
is needed only after the open decisions have an agreed use case.

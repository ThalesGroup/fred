# Fred Debug Playbook (Langfuse)

Status: practical playbook for day-to-day v2 debugging (Graph + ReAct)

## Why this file exists

When a v2 agent is slow or behaves unexpectedly, developers need a fast and repeatable way to answer:

1. Which node consumed time?
2. Was the bottleneck model, retrieval, or human wait?
3. Which state transition led to the current behavior?
4. What instrumentation should be added next to reduce ambiguity?

This playbook is intentionally operational. It is not an architecture note.

## 1. Scope

This guide targets v2 agents running through:

- `GraphRuntime` node execution and events
- `ReActRuntime` loop execution
- Langfuse span tracing via v2 tracer port
- KPI phase timers in backend logs

Primary reference example:

- `agentic_backend/agents/v2/candidate/bid_mgr/agent.py`
- `agentic_backend/agents/v2/production/basic_react/agent.py`

Quick runtime split (do this first):

- If the trace includes `v2.graph.node`, use the graph sections of this playbook.
- If the trace includes `v2.react.model` and no `v2.graph.node`, use the ReAct section (`11`).
- If neither appears and only top-level spans are visible (for example `agent.stream`), classify as `instrumentation_gap` first.

## 2. Runtime Signals You Already Have

For v2 graph agents, the runtime emits these useful span names:

- `v2.graph.node`
- `v2.graph.model`
- `v2.graph.tool`
- `v2.graph.runtime_tool`
- `v2.graph.publish_artifact`
- `v2.graph.fetch_resource`
- `v2.graph.await_human`

For v2 ReAct agents, current useful span names are:

- `v2.react.model` (runtime-owned model call span)
- `tool.invoke` (tool-call span when emitted by the execution stack)
- top-level transport span such as `agent.stream`

Relevant metadata attached by tracer:

- `agent_id`
- `agent_name`
- `team_id`
- `user_id`
- `user_name`
- `session_id`
- `fred_session_id`
- `correlation_id`
- `request_id`
- node-level attributes (`node_id`, `operation`, `tool_ref`, `status`, etc.)

Relevant KPI phases (logs):

- `v2_graph_node`
- `v2_graph_model`
- `v2_graph_tool`
- `v2_graph_runtime_tool`
- `stream_agent_response`
- `stream_total`

## 3. Graph 5-Minute Triage Loop (Per User Exchange)

Use this loop for every suspicious exchange.

1. Identify scope.
- Note `agent_id` or `agent_name`, `team_id`, `user_name`, `session_id` (`fred_session_id`), `exchange_id`.
- Keep one suspicious user message as the reference point.

2. Open Langfuse and filter traces.
- Preferred filters:
  - `metadata.agent_name = <agent_name>`
  - `metadata.team_id = <team_id>`
  - `metadata.fred_session_id = <session_id>`
- Fallback filters:
  - `metadata.agent_id = <agent_id>`
  - `metadata.session_id = <session_id>`
- Focus on the latest trace segment covering your exchange time window.

3. Find the longest span first.
- If longest is `v2.graph.tool`, inspect `tool_ref`.
- If longest is `v2.graph.model`, inspect `operation`.
- If longest is `v2.graph.await_human`, this is expected waiting, not backend slowness.

4. Rebuild node path.
- Order `v2.graph.node` spans by start time.
- Confirm route sequence against graph design.
- For bid intake, expected flow is:
  - `route_request`
  - `retrieve_bid_context`
  - `analyze_intake`
  - `request_clarifications` or `build_summary`
  - `finalize`

5. Cross-check with KPI log phases.
- Compare Langfuse span duration with KPI durations for:
  - `v2_graph_tool` and `v2_graph_model`
  - `stream_agent_response`
- If KPI and Langfuse disagree significantly, suspect missing span coverage or asynchronous work outside span boundaries.

6. Conclude root cause with one label.
- `retrieval_latency`
- `model_latency`
- `awaiting_human`
- `routing_or_state_issue`
- `instrumentation_gap`

## 4. Graph Latency Diagnosis Matrix

### Case A: `v2.graph.tool` dominates

Likely cause:
- retrieval or external tool backend latency

Bid intake example:
- `retrieve_bid_context` calling `knowledge.search`

Action:
- verify retrieval query length and relevance
- verify corpus scope and selected libraries
- compare with direct `/vector/search` timing in Knowledge Flow logs

### Case B: `v2.graph.model` dominates

Likely cause:
- prompt size or model response time

Bid intake example:
- `operation=intent_router`
- `operation=analysis`

Action:
- inspect prompt payload size
- reduce unnecessary retrieved context before analysis
- split one heavy model operation into two smaller operations if needed

### Case C: `v2.graph.await_human` dominates

Likely cause:
- normal HITL pause, not server processing

Action:
- exclude from backend latency KPI
- report separately as business process wait time

### Case D: `v2.graph.node` long but no clear model/tool child

Likely cause:
- pure Python processing in node handler
- missing fine-grained instrumentation

Action:
- add `emit_status` checkpoints around heavy logic
- optionally add dedicated runtime spans for expensive local sections

## 5. Bid Intake Agent: What To Inspect First

Focus nodes in this order:

1. `retrieve_bid_context`
- check `knowledge.search` call duration
- check `retrieved_hit_count`
- check emitted status:
  - `bid_corpus_search` success/fallback

2. `analyze_intake`
- compare `intent_router` vs `analysis` model durations
- check whether fallback analysis path is triggered unexpectedly

3. `request_clarifications`
- ensure this is treated as `awaiting_human`, not backend error
- ensure UI behavior aligns with `free_text=True`

4. `build_summary`
- check artifact publish timing and status

## 6. Developer Instrumentation Checklist (Agent Level)

For each node handler, verify:

1. A clear `emit_status` at node start with business meaning.
2. A clear `emit_status` for fallback/error branches that continue execution.
3. Distinct `operation` names on `invoke_model` calls.
4. Tool calls are explicit and minimal per node.
5. State updates include enough fields to explain route decisions in next node.

Recommended minimum status taxonomy for graph agents:

- `routing`
- `context_retrieval`
- `analysis`
- `clarification`
- `artifact_publish`
- `fallback`

## 7. Developer Instrumentation Checklist (Runtime Level)

If debugging remains ambiguous, add runtime improvements in this order:

1. Add stable `route_key` attribute when a node returns routed output.
2. Add state delta summary metadata to `v2.graph.node` span:
- keys updated
- count of updated keys

3. Add payload size metadata:
- model prompt character count
- retrieved context character count
- tool request/response size buckets

4. Add explicit span link between tool/model span and parent node step index.

5. Add optional debug mode to emit node state snapshot hashes.

## 8. Dashboard Preset You Should Save

Create one saved Langfuse view named:

- `V2 Graph Debug - Per Session`

Suggested filters:

- `metadata.agent_name = <selected>`
- `metadata.team_id = <selected>`
- `metadata.user_name = <selected>`
- `metadata.fred_session_id = <selected>`
- fallback: `metadata.agent_id`, `metadata.session_id`
- timeframe = last 30 min

Columns:

- span name
- duration
- metadata.node_id
- metadata.operation
- metadata.tool_ref
- metadata.status
- metadata.agent_name
- metadata.team_id
- metadata.user_name
- metadata.session_id

Sort:

- duration desc (first pass)
- start time asc (second pass)

## 9. Acceptance Criteria For “Good Graph Observability”

A v2 graph agent is observability-ready when:

1. Any slow exchange can be classified in under 5 minutes.
2. Node path can be reconstructed without reading backend code.
3. Tool/model bottleneck can be isolated to one step and one span.
4. HITL wait is clearly separated from backend compute latency.
5. Developers can propose one concrete fix from evidence, not guesswork.

## 10. Common Graph Pitfalls

1. Mixing transport callback traces and v2 runtime spans without filtering.
- Keep analysis centered on v2 graph span names first.

2. Treating `await_human` as backend latency.
- It is business wait time.

3. Reading only `stream_agent_response`.
- Always decompose by `v2_graph_node`, `v2_graph_model`, `v2_graph_tool`.

4. Overloading one node with too many responsibilities.
- Split nodes when one span consistently dominates and hides root cause.

## 11. ReAct Quick Triage (Basic ReAct + Profiles)

Use this section when the trace is ReAct-shaped:

- `v2.react.model` is present
- `v2.graph.node` is absent

5-minute loop for ReAct:

1. Identify scope.
- Note `agent_name`, `team_id`, `user_name`, `fred_session_id`, `exchange_id`.

2. Filter trace in Langfuse.
- `metadata.agent_name = <agent_name>`
- `metadata.team_id = <team_id>`
- `metadata.fred_session_id = <session_id>`

3. Check span breakdown.
- If `v2.react.model` dominates, classify as `model_latency`.
- If `tool.invoke` dominates, classify as `tool_latency`.
- If `agent.stream` dominates with near-zero model/tool totals, classify as `instrumentation_gap`.

4. Verify metadata quality.
- Confirm `agent_name`, `team_id`, `user_name`, `fred_session_id` are present.
- If those fields are missing, fix runtime tracer metadata mapping before deeper tuning.

5. Conclude with one root-cause label.
- `model_latency`
- `tool_latency`
- `awaiting_human`
- `instrumentation_gap`

Recommended ReAct dashboard preset:

- Name: `V2 ReAct Debug - Per Session`
- Filters:
  - `metadata.agent_name = <selected>`
  - `metadata.team_id = <selected>`
  - `metadata.user_name = <selected>`
  - `metadata.fred_session_id = <selected>`
- Columns:
  - span name
  - duration
  - metadata.operation
  - metadata.tool_ref
  - metadata.tool_name
  - metadata.status
- Sort:
  - duration desc
  - start time asc

# Fred Feature Map (Current Runtime)

Status: stable reference for the current implemented v2 feature surface

This document is a practical map for retesting the current Fred v2 world.

It is not a deep architecture note. The goal is simpler:
- list the important v2 capabilities
- explain, in one line, how each capability fits the v2 runtime model
- point to the best current demo, profile, or agent to see it in action

Use it when you want to review the v2 runtime feature by feature instead of
reading the codebase first.

## 1. What Exists Today

The current v2 world has two real execution shapes:

- `ReActAgentDefinition`
  Best for assistants whose job is mainly:
  - understand the request
  - use tools
  - answer or produce an artifact

- `GraphAgentDefinition`
  Best for agents whose value comes from a controlled business journey:
  - route the request
  - gather the right context
  - pause for decisions
  - execute the permitted action
  - keep the next turn coherent

Current concrete v2 agents and demos:

- `Basic ReAct V2`
- `RAG Expert V2`
- `Tracking Graph Demo V2`
- `Artifact Report Demo V2`

Current built-in ReAct profiles:

- `generic_assistant`
- `georges`
- `custodian`
- `sentinel`
- `log_genius`
- `geo_demo`

One runtime detail is important for interpreting the current system correctly:

- v2 still keeps a warm per-session agent cache
- v2 also writes durable checkpoints

So a hot session can benefit from in-memory reuse, while restart tolerance and
pause/resume still rely on the durable checkpoint path.

## 2. How To Read This Map

For each feature below, the important questions are:

1. What business problem does this capability solve?
2. How is it expressed in v2?
3. Which agent or profile is the best way to test it?
4. What should you expect to see if it works correctly?

## 3. Feature Map

### 3.1 Clean ReAct Authoring

What it is:
- the simplest authoring model for a useful assistant

How it fits v2:
- the definition declares role, prompt, and tool requirements
- the shared `ReActRuntime` owns execution

Best thing to test:
- `Basic ReAct V2`

What to try:
- ask a plain conversational question with no tools needed

What you should observe:
- no custom runtime code is needed in the agent definition
- the answer behaves like a normal assistant
- the info bubble should show token usage if the model provider returns it

### 3.2 ReAct Profiles

What it is:
- business starting points for a generic ReAct agent

How it fits v2:
- profiles do not create a new runtime
- they preload a business identity: prompt, tags, MCP defaults, approval policy

Best thing to test:
- create `Basic ReAct V2` from:
  - `custodian`
  - `sentinel`
  - `georges`
  - `geo_demo`

What to try:
- compare two different profiles created from the same base agent type

What you should observe:
- same runtime category
- different business behavior and default capabilities

### 3.3 Runtime-Provided MCP Tools

What it is:
- the admin equips an agent with MCP servers without changing its code

How it fits v2:
- the definition stays pure
- `ToolProviderPort` and the Fred MCP bridge resolve actual tools at runtime

Best thing to test:
- `Basic ReAct V2` with `custodian` or `sentinel`

What to try:
- attach MCP servers in settings
- start a fresh conversation
- ask the agent to use those tools explicitly

What you should observe:
- tool calls appear in the conversation
- the agent code did not need to hard-code server URLs

Important distinction:

- runtime-provided MCP tools are one way Fred can expose capabilities at runtime
- but when Fred already provides a stable business tool ref, agent authors
  should prefer that tool ref over a direct MCP dependency

Example:

- for standard corpus retrieval, prefer `knowledge.search`
- do not bind a new product agent directly to `mcp-knowledge-flow-mcp-text`
  unless the needed capability is not yet exposed by Fred as a first-class tool

### 3.4 Human Approval In ReAct

What it is:
- the user must approve sensitive actions before execution

How it fits v2:
- approval is a policy on the definition side
- the runtime pauses and resumes through the shared HITL contract

Best thing to test:
- `Basic ReAct V2` with `custodian`

What to try:
- ask for a mutating file/corpus action

What you should observe:
- a human approval card
- no tool execution before approval
- successful resume after approval

### 3.5 RAG With Sources

What it is:
- document-grounded answers with citations

How it fits v2:
- the agent declares a business tool, `knowledge.search`
- tool results carry structured `sources`
- the final message preserves them

Why this matters:

- the authoring contract is "this agent needs corpus retrieval"
- not "this agent talks to this exact MCP endpoint"
- this keeps retrieval transport-agnostic and lets Fred preserve chat-selected
  library scope, selected documents, and knowledge mode centrally

Best thing to test:
- `RAG Expert V2`

What to try:
- ingest a small document with specific facts
- ask narrow factual questions

What you should observe:
- a grounded answer
- visible source metadata on the final answer
- different behavior if the selected knowledge scope changes

Why this is its own v2 definition and not just a profile:
- a profile is a business starting point for the generic ReAct assistant
- `RAG Expert V2` also carries RAG-specific fields and explicit grounding guardrails
- so it is still ReAct, but it is a stronger product definition than a simple preset

### 3.6 Geo / Map Output

What it is:
- an agent can return a real map, not just text describing coordinates

How it fits v2:
- `GeoPart` is a structured UI output
- the runtime carries it as a first-class part

Best thing to test:
- `Basic ReAct V2` with `geo_demo`
- or `Tracking Graph Demo V2`

What to try:
- `Show Paris and Lyon on a map`
- or ask the postal graph to show the parcel route / pickup points

What you should observe:
- a real map rendered in the UI
- not just a blob of GeoJSON or prose

### 3.7 Artifact Publishing

What it is:
- an agent generates a report or note, stores it through Fred, and returns a link

How it fits v2:
- `ArtifactPublisherPort` is the platform capability
- the UI-facing output is still a normal `LinkPart`

Best thing to test:
- `Artifact Report Demo V2`

What to try:
- ask for a downloadable summary, report, or brief

What you should observe:
- the agent publishes a file
- the chat returns a real download link
- the agent does not invent a URL itself

### 3.8 Resource / Template Fetching

What it is:
- admins upload templates or supporting files, and the agent can fetch them later

How it fits v2:
- `ResourceReaderPort` is the platform capability
- graph nodes can fetch text or bytes directly
- ReAct agents can use the narrow built-in tool `resources.fetch_text`

Best thing to test:
- `Artifact Report Demo V2`

What to try:
- upload a text template in agent config storage, for example `report-template.md`
- ask the report demo to use that template for the generated deliverable

What you should observe:
- the template is fetched through Fred storage
- the agent does not hard-code any storage URL
- the published artifact reflects the fetched template or style guide

### 3.9 Graph Business Workflow

What it is:
- a real business flow with typed state, routing, tool calls, HITL, and rich output

How it fits v2:
- the author declares the graph
- `GraphRuntime` owns execution, pause/resume, and state continuity

Best thing to test:
- `Tracking Graph Demo V2`

What to try:
- ask about your parcel
- choose the parcel when asked
- ask for diagnosis, map, reroute, or reschedule

What you should observe:
- structured workflow progression
- MCP calls to both business and IoT services
- human decisions at the right points
- a clean final business outcome

### 3.10 Durable Conversation State In Graph

What it is:
- the graph remembers the selected business object across turns

How it fits v2:
- the runtime persists the last completed graph state
- the definition decides what to carry into the next turn

Best thing to test:
- `Tracking Graph Demo V2`

What to try:
1. ask if you have a parcel in progress
2. choose one parcel
3. ask a follow-up question about delivery or rerouting

What you should observe:
- the graph should reuse the parcel context
- it should not ask you to pick the parcel again unless the situation is ambiguous again

### 3.11 HITL Checkpoint Identity

What it is:
- pause/resume should be explicit and transport-safe

How it fits v2:
- `awaiting_human` carries a `checkpoint_id`
- the runtime validates resume against that checkpoint identity
- the durable checkpoint backend now runs over Fred's shared SQL engine
  (`storage.postgres`), with SQLite fallback still possible in local dev

Best thing to test:
- any v2 HITL flow:
  - `custodian`
  - `Tracking Graph Demo V2`

What to try:
- trigger a pause
- resume it
- then continue the conversation

What you should observe:
- successful resume
- no dependence on one executor object surviving in memory

### 3.12 Inspection

What it is:
- a safe structural description of a v2 agent

How it fits v2:
- `inspect` is the canonical introspection surface
- it is separate from execution

Best thing to test:
- any v2 agent

What to try:
- call the backend inspect endpoint for the agent:
  - `GET /agentic/v1/agents/{agent_id}/inspect`

What you should observe:
- `execution_category`
- fields
- declared tool requirements
- preview
- default MCP servers when relevant

Important note:
- for ReAct agents, inspection is usually text-first
- for graph agents, inspection can include Mermaid

### 3.13 Runtime Observability Baseline

What it is:
- shared tracing conventions emitted by v2 runtime, not by each agent author

How it fits v2:
- runtime emits consistent spans for major execution steps
- Langfuse metadata includes Fred business context (`agent_name`, `team_id`,
  `user_name`, `fred_session_id`)

Best thing to test:
- one ReAct agent (`Basic ReAct V2`)
- one graph agent (`Tracking Graph Demo V2`)

What to try:
- run one exchange with tool calls
- filter Langfuse by `agent_name` + `fred_session_id`
- check that model/tool/runtime spans are visible under the exchange trace

What you should observe:
- consistent runtime naming conventions:
  - graph runtime: `v2.graph.*` spans (`v2.graph.node`, `v2.graph.model`, `v2.graph.tool`, ...)
  - ReAct runtime: `v2.react.model` span for model calls (`operation=model_call`)
- easier per-session filtering than raw opaque ids
- if only a top-level span is visible, classify it as instrumentation gap and
  fix runtime instrumentation

### 3.14 Trace-Assisted Performance Triage

What it is:
- an admin-facing capability to summarize one conversation performance from
  Langfuse traces

How it fits v2:
- exposed as a first-class tool ref (`traces.summarize_conversation`)
- same runtime tool path as other platform capabilities
- intentionally implemented as a Fred built-in runtime tool, not as an MCP tool
- current backend path is Langfuse Public API over HTTP (`/api/public/traces`,
  `/api/public/traces/{trace_id}`) using `LANGFUSE_HOST`,
  `LANGFUSE_PUBLIC_KEY`, and `LANGFUSE_SECRET_KEY`

Best thing to test:
- `log_genius` profile

What to try:
- ask for performance analysis of the current conversation
- compare the summary with Langfuse dashboard spans

What you should observe:
- bottleneck classification with explicit totals (`model_total_ms`,
  `tool_total_ms`, `await_human_total_ms`)
- explicit `instrumentation_gap` detection when breakdown is missing
- concrete next actions instead of ambiguous “slow model” guesses

## 4. Suggested Retest Order

If you want a clean manual review of the v2 world, this order is efficient:

1. `Basic ReAct V2`
   - plain conversation
   - token usage

2. ReAct profiles
   - `georges`
   - `custodian`
   - `sentinel`

3. ReAct HITL
   - `custodian`

4. RAG and sources
   - `RAG Expert V2`

5. Geo output
   - `geo_demo`

6. Artifact publishing and template fetch
   - `Artifact Report Demo V2`

7. Graph workflow, graph HITL, graph continuity
   - `Tracking Graph Demo V2`

8. Inspect endpoint
   - one ReAct agent
   - one Graph agent

9. Observability and trace triage
   - verify Langfuse metadata filtering (`agent_name`, `team_id`, `user_name`, `fred_session_id`)
   - run `traces.summarize_conversation` on a real exchange
   - confirm no misleading bottleneck when instrumentation is missing

## 5. What This Map Is Meant To Validate

If all of the tests above feel coherent, then the important v2 claim becomes
credible:

- the runtime is no longer just “a nicer way to write agents”
- it is becoming a real capability platform

The features above are the ones that matter most for that claim:

- tools
- HITL
- sources
- maps
- artifact publication
- resource fetching
- graph workflows
- inspection
- observability

If those all feel natural in the same model, then the v2 direction is strong.

For a scan of what still remains in the legacy agents and whether it deserves
promotion into a real runtime feature, see
[LEGACY_FEATURE_SCAN.md](./LEGACY_FEATURE_SCAN.md).

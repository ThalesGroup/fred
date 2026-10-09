## Context

See [proposal.md](proposal.md) for motivation and [the delta specification](specs/deliverable-generation/spec.md) for acceptance.

`react_runtime.py` emits `ToolCallRuntimeEvent` from a completed `AIMessage.tool_calls`, after argument generation. The three capabilities contribute their tools and always-on instructions through middleware and currently declare ReAct support. PPT tools are built conditionally from the configured template by `build_fill_tools`.

Frontend `ThoughtTrace` already receives the turn's trace messages and a `done` flag from `AssistantTurn`. Its summary derives running state from unfinished trace rows; a completed preparation row alone would therefore stop showing live activity. Tool rows and the summary are separate display surfaces and can retain their distinct meanings.

## Goals / Non-Goals

**Goals:** Reuse normal tool traces and the existing live-turn lifecycle to show composition before publication. Keep the existing publication tools usable by direct callers and existing agents.

**Non-Goals:** No new event, chat part, store, job, shared generation service, or nested model call. The full payload continues to be composed by the agent's next ordinary model invocation. Scope boundaries are listed in the proposal.

## Decisions

### Capability-owned short preparation tools

Add `begin_document_generation(title)` and `begin_html_artifact_generation(title)` beside the current tools in their middleware. Add `begin_ppt_generation(title)` through PPT middleware only when its fill tools are available. Keep the existing tool ordering where consumers rely on it and make affected tests resolve tools by name when appropriate.

Each tool returns a short acknowledgement and directs the model to compose the content and invoke its corresponding publication tool. A bounded title is its only model-visible input; identity stays in the capability context. The tool does not create a deliverable or hold mutable process state. Distinct names avoid collisions when capabilities are combined.

Update the instruction fragments and publication-tool descriptions to require a separate preparation round before composing a new payload, including revisions. Preserve PPT's grounding-before-fill instructions and the existing document path for finished workspace Markdown. Keep direct publication compatible: no server-side prerequisite or rejection of old callers.

An internal LLM call inside preparation would introduce a second generation/prompting boundary and different tuning behavior. Streaming partial arguments would instead require a runtime event/partial-payload contract. Neither is needed for the requested two-tool workflow.

### Live composition label derived from existing traces

Derive a small composition state from successful preparation results and subsequent publication calls within the current exchange. Use existing call/result identity and ordered trace messages; do not add a second persisted state owner. A later preparation replaces the previous composition indication for the same capability. Multiple pending kinds use a generic localized composition label instead of attributing all activity to one deliverable.

Pass the result to `ThoughtTrace`'s localized header only while that exchange is live and has no higher-priority error, outstanding tool execution, or human-input state. The corresponding publication call ends that composition stage and shows a localized writing/rendering label while that call is pending. The preparation row itself remains completed. An unrelated running tool takes precedence; after it completes, a still-pending composition indication can resume.

Use `done` and the existing turn/pause state rather than an unmatched marker alone: history, cancelled turns, completed turns, and pauses cannot remain live. Read and test the current `toThreadMessages`/`AssistantTurn` lifecycle together, including its transition where a new turn can briefly mark the previous exchange streaming. Scope the marker to its originating execution where execution metadata exists; do not borrow a sibling execution's marker to label another lane.

### Tests follow observable boundaries

Extend existing capability tests for availability, schema size, no publication side effects, instruction sequencing, and direct publication/regression behavior. A deterministic ReAct stream test with no reasoning text must observe preparation call/result before the later publication round. Frontend utility/component tests must render the inter-round interval and its transitions, rather than only checking tool-name strings. Manual validation with a real configured agent assesses instruction following and the actual visible wait.

## Risks / Trade-offs

- Extra model round: adds latency, tokens, and one tool call to the turn's existing budget. Inspect latency/usage and near-limit behavior; document the cost without claiming generation is faster or exempting these tools from existing pacing rules.
- Model instruction following: unit tests establish tool and event behavior, not universal compliance by every model. Validate a configured non-reasoning agent for each capability before readiness; preparation and publication in one batch fails the manual acceptance criterion.
- Stale activity: gate the header on the live exchange and terminal/pause state, including the next-turn transition. Keep the completed marker's status independent of composition.
- Compatibility: retain publication schemas and direct calls, PPT offloading/limits, revision identifiers, and artifact outputs. No endpoint/client regeneration is required unless implementation later changes that scope.

## Migration Plan

Ship the additional tools/instructions with the frontend labels. Older frontends can still show the early tool trace; older agents' direct publication continues working on the new frontend. Roll back the capability additions and labels together if instruction-following or cost is unacceptable. No data migration is needed.

# Legacy Feature Scan (v1 to Current Runtime)

Status: exploratory scan, follow-up topics still open

This note answers one practical question:

> When scanning the remaining legacy agents and demos, did we miss any real
> platform feature that should become part of Fred v2?

The goal is not to list every old agent behavior. The goal is to separate:

- true missing v2 capabilities
- behaviors already covered by v2
- things that are useful, but are not platform features

## 1. High-Level Result

After scanning the remaining legacy agents and demos, the answer is:

- we did **not** miss a large hidden class of features
- we **did** identify one important remaining family to make more explicit:
  **binary template-based generation**
- `Mermaid` is **not** a new runtime feature; it is better treated as a
  supported chat/rendering format

## 2. Features Already Clearly Represented In V2

These are already visible as real v2 capabilities or patterns.

### 2.1 Tool-based assistants

Seen in legacy:
- generalist agents
- sentinel
- log-oriented agents
- RAG agents

V2 status:
- covered by `ReActAgentDefinition`
- runtime tools can come from declared `tool_requirements`
- runtime tools can also come from MCP bindings

Follow-up rule worth keeping in mind:

- repeated pressure to bind new product agents directly to raw MCP endpoints is
  often a signal that Fred is still missing a first-class business capability
- when that pattern repeats, the better move is usually to elevate a stable tool
  ref in v2 rather than normalizing transport details in each agent definition

### 2.2 Human in the loop

Seen in legacy:
- postal tracking
- custodian-style approval flows

V2 status:
- covered
- simple approval works in ReAct
- richer business decision pauses work in Graph

### 2.3 Maps and geographic rendering

Seen in legacy:
- postal tracking
- old GPS demo

V2 status:
- covered by `GeoPart`

### 2.4 Generated files and download links

Seen in legacy:
- downloadable-content demo
- Jira exports
- reference editor
- ppt filler
- content generator

V2 status:
- covered in principle by:
  - `ArtifactPublisherPort`
  - `LinkPart`

### 2.5 Reading admin-provided templates/resources

Seen in legacy:
- slide maker
- ppt filler
- reference editor
- content generator

V2 status:
- now covered in principle by:
  - `ResourceReaderPort`
  - graph resource fetch helpers
  - `resources.fetch_text` for ReAct

### 2.6 Structured citations

Seen in legacy:
- RAG agents

V2 status:
- covered

## 3. Real Remaining Feature Family Worth Elevating

There is one important family still worth treating as a deliberate v2 feature:

## 3.1 Binary template-based document generation

This appears in several remaining legacy agents:

- [slide_maker.py](/home/dimi/run/reference/fred/agentic-backend/agentic_backend/academy/04_slide_maker/slide_maker.py)
- [ppt_filler_agent.py](/home/dimi/run/reference/fred/agentic-backend/agentic_backend/agents/ppt_filler/ppt_filler_agent.py)
- [reference_editor.py](/home/dimi/run/reference/fred/agentic-backend/agentic_backend/agents/reference_editor/reference_editor.py)
- [pptx_generator.py](/home/dimi/run/reference/fred/agentic-backend/agentic_backend/agents/content_generator/pptx_generator.py)

What these agents have in common:

- fetch a binary template such as `.pptx` or `.docx`
- fill or transform it
- upload one or more binary outputs
- sometimes return both:
  - a download link
  - a view/preview link

This is not “just another artifact”.
It is the first strong test of whether Fred v2 can support **template-driven
business deliverables** cleanly.

### Why this matters

If Fred v2 handles this well, then many real production use cases become
credible:

- proposal generation
- slide generation
- reference sheet generation
- templated Word/PPT deliverables

### What is already good

V2 already has the right backbone:

- resource fetching
- artifact publishing
- `LinkPart`

### What is still a bit uneven

For this family, Graph is currently the cleaner path than ReAct because:

- Graph nodes can fetch binary resources directly
- Graph nodes can publish bytes directly

ReAct is still narrower:

- `resources.fetch_text`
- `artifacts.publish_text`

So the remaining question is not “does v2 support this at all?”
It is:

> do we want ReAct to stay text-first here, or do we want a clean binary-capable
> ReAct path too?

That is a real design decision, not a bug.

## 4. Things That Look Important But Are Probably Not Runtime Features

These are useful, but they should not be mistaken for core SDK/runtime
capabilities.

### 4.1 Mermaid

Seen in legacy:
- `generalist_expert`
- prompts that encourage Mermaid
- some docs and examples

Verdict:
- not a runtime feature
- better treated as a **supported output/rendering format**

Why:
- the agent usually just emits Mermaid text
- the UI already knows how to render it safely
- this is closer to “Markdown feature support” than to HITL, maps, or artifact publishing

So `Mermaid` should remain:
- something the assistant may produce
- something the UI can render
- not a dedicated v2 runtime service

### 4.2 Markdown tables

Seen in:
- tabular/statistics/Jira-style outputs

Verdict:
- not a platform feature
- plain content formatting

### 4.3 CSV export itself

Seen in:
- Jira exports

Verdict:
- not a separate feature from artifact publishing
- it is just one business use of artifact publishing

### 4.4 Image search for domain documents

Seen in:
- reference editor image helpers

Verdict:
- probably domain-specific
- not clearly a generic Fred platform capability yet

## 5. Things That Need Careful Judgment, Not Immediate Promotion

### 5.1 Previewable artifact pairs

Seen in:
- [pptx_generator.py](/home/dimi/run/reference/fred/agentic-backend/agentic_backend/agents/content_generator/pptx_generator.py)

Pattern:
- generate `.pptx`
- also generate `.pdf`
- return one download link and one view link

Verdict:
- promising pattern
- but not yet clearly a separate runtime feature

Most likely:
- still part of artifact publishing
- maybe later deserves a small convenience layer for “artifact bundles”

### 5.2 Statistics plotting

Seen in:
- [statistics_expert.py](/home/dimi/run/reference/fred/agentic-backend/agentic_backend/agents/statistics/statistics_expert.py)

Verdict:
- not enough evidence yet that this is a Fred runtime capability
- today it looks more like a domain tool capability than a UI/runtime primitive

If one day the UI needs a structured chart part, that would be a separate
decision.

## 6. Practical Conclusion

The scan suggests this simple conclusion:

1. The current v2 direction already covers most of the important old patterns.
2. `Mermaid` should not become a runtime feature.
3. The next serious capability frontier is:
   **template-driven binary document generation**

If we want one next v2 exercise after the current work, that is probably the
best one:

- fetch a binary template
- fill it
- publish a binary artifact
- optionally publish a paired preview artifact

That exercise would tell us a lot about whether Fred v2 is ready for the old
PPT/Word-producing agents.

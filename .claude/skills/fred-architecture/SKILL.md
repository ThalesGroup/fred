---
name: fred-architecture
description: Maintain Fred's human-oriented architecture dossier and its alignment with current features. Read at the start of every Fred task, especially feature development and architecture edits. Defines audience, editorial scope, feature overview and code annex boundaries; does not initiate an audit or rewrite.
---

# Fred architecture: help a new reader understand Fred

Read this skill at the start of every Fred task, whether using Codex, Claude or
another coding assistant. Resolve paths against the current Fred checkout.
This is the authoritative editorial policy for `docs/architecture/`; it replaces
older instructions to put feature plans or proposed decisions in that dossier.

## Weaver validation boundary

The dossier follows the integrated Weaver scope validated end to end, not the
union of features found in the repository, Swift documentation or SDKs. Code
presence, isolated CLI discovery and runtime documentation do not prove that the
feature is wired into Weaver or validated end to end.

The documented scope is the set of journeys a lot owner validated end to end, on
local k3d and the integration platform, as recorded in the lot's PR
(AGENTS.md, "Weaver: lots"). Update the existing chapters in that PR; an
implemented but unvalidated journey stays out. Additional Knowledge Bases and
application extensions remain outside until integrated and validated. Do not
expand an overview or fill empty chapters from SDK features. Keep the same
boundary in annexes; moving a claim there does not validate it.

## Audience and purpose

The primary readers are architects, clients and security stakeholders (SSI).
Integrators, DevOps engineers and curious readers must also be able to understand
Fred quickly. Assume technical literacy, but no prior knowledge of Fred's names,
internal implementation or development history.

Explain what Fred provides, how it works, its boundaries and why its architecture
matters. Be compact and precise without turning the dossier into a catalogue of
implementation details. It is neither a development specification nor an operator
runbook. A reader should understand Fred without reading source code.

## Editorial contract

- Brevity is a maintenance requirement. Keep chapters short; prefer a few precise
  sentences and a focused diagram over long prose. Remove repetition instead of
  adding summaries. Do not repeat a diagram node by node in the surrounding text.
- Give each diagram one teaching purpose. Show only the concepts and relationships
  needed for that purpose, with short labels. Omit secondary flows and details;
  completeness belongs in the relevant explanation or annex, not every diagram.
  Prefer maintainable Mermaid for simple architecture diagrams. Use an image only
  when it explains something more clearly, not as decoration.
- Describe Fred's actual state. Exclude target architecture, roadmap, backlog,
  reconstruction history, progress reports and proposed features. Keep these in
  RFCs, OpenSpec or work tracking outside the dossier. Do not disguise a planned
  behavior as current by deleting the word "planned". Resolve the factual gap
  with the user when it affects a requested explanation.
- Build understanding in order: purpose, concepts, responsibilities, interactions,
  then detail. Define a concept before explaining its variants or extensibility.
  Re-read the surrounding section after every insertion; an accurate paragraph
  in the wrong place is still a bad change.
- Write connected explanations answering a reader's question. Use tables for
  genuine comparisons and diagrams for relationships or journeys. Avoid RFC-like
  templates, arbitrary IDs, acceptance criteria and accumulation of disconnected
  facts. Add detail only if it improves understanding or precision.
- Explain current design reasons and meaningful limitations where relevant,
  without narrating abandoned options or the history of implementation.
- Use Control Plane, Knowledge Flow and Agent Pod consistently. Introduce their
  roles before explaining that Fred supplies a native Agent Pod and can host
  multiple developer-provided Agent Pods. Fred is usable on its own and extensible.
- SDK coverage explains principles of extending Fred through Agent Pods,
  Knowledge Bases and applications. Keep SDK tutorials and API details elsewhere.

## Diagram layout and reading comfort

Design for the document's normal reading width, including a side panel. Labels
must remain comfortably readable without zooming. A correct diagram that shrinks
into tiny boxes and arrows is not an acceptable overview.

Balance vertical progression with short horizontal branches. Prefer top-to-bottom
layout for long flows, with parallel inputs or outcomes side by side. Keep short
horizontal flows only when their labels fit comfortably. Use short labels and
intentional line breaks rather than allowing boxes to stretch the whole drawing.
Do not solve excessive width or density by reducing the font size.

Simplify or split a crowded diagram while preserving its meaning. Detailed state
machines and database schemas may need denser layouts; this exception does not
apply to overview diagrams. When a rendered preview is available, inspect it at
normal reading width, not only enlarged. Do not claim visual verification from
Mermaid source inspection alone.

## Consistent diagram colors

Use GitHub-compatible Mermaid `classDef` and `class` statements inside each
fenced diagram, without external CSS, scripts or a custom rendering dependency.
Reuse these exact semantic colors across the dossier:

| Class | Meaning | Fill | Border | Text |
| --- | --- | --- | --- | --- |
| fred | Fred components, native UI and native capabilities | #DBEAFE | #2563EB | #172554 |
| cots | Third-party infrastructure, including open-source products such as Temporal and OpenSearch | #FEF3C7 | #B45309 | #451A03 |
| extension | Developer-supplied extensions, such as an additional Knowledge Base | #F3E8FF | #7E22CE | #3B0764 |
| neutral | Actors, actions, information and functional concepts | #F1F5F9 | #64748B | #0F172A |

Set fill, border and text together to preserve node contrast on light and dark
backgrounds. Keep edge styling compatible with the renderer's theme. Include a
compact legend once per page before the technical diagrams, using this format:

`**Legend:** 🟦 Fred · 🟨 COTS · 🟪 Extensions · ⬜ Concepts`

These semantic color markers are an intentional exception to the repository's
ASCII punctuation convention. Do not repeat the legend under every diagram or
spell out the color mapping in prose. Labels must remain understandable without
color. A functional knowledge concept is neutral, not COTS; an actual
storage engine is COTS. A custom Agent Pod or capability is an extension, while
its native Fred counterpart is blue. Do not introduce technical ownership colors
into a purely functional diagram. Use only the classes needed by each diagram.

## Separate functional and technical views

Start an overview with what the user can do and understand. Only then explain
which components implement it, in a separate view. Never mix the two levels in
one diagram merely to save space.

- **Functional view:** actors, actions, information and visible outcomes. For
  knowledge, distinguish feeding it, browsing it and using it with an agent.
  A user can upload documents; a Knowledge Base application can collect them.
  Collection and presentation are independent: the same drive can present either
  source. Do not reduce the knowledge concept to its document-drive representation.
  Keep APIs, workers, Temporal, database products and deployment pods out of this view.
- **Technical view:** named components, responsibilities, interactions and relevant
  infrastructure. Introduce only the mechanics needed to explain the functional
  view. Split ingestion and agent access into separate small diagrams if necessary.
  Distinguish requests, processing and data access with meaningful arrow labels.
- **Do not invent endpoints from functional actions.** In Fred's document path,
  both UI uploads and application submissions go through Control Plane. It exposes
  the drive and coordinates ingestion through Temporal. Knowledge Flow is a Temporal
  worker, not an API service called by the UI or a Knowledge Base. Agent Pod is an
  API service used by the UI; agents access knowledge through capabilities.
- Hypothetical representations (for example ontology graphs) help discuss extension
  principles but must not become claims of existing product functionality. Do not
  include speculative examples in a current-state diagram.

Before editing a diagram, state its single reader question and choose its level.
Check every node and arrow against that level. A functional relationship does not
establish a technical call or a direct database connection. Verify uncertain wiring
in the relevant source; surface a discrepancy instead of inventing a bridge.

## Feature overview

The first purpose of the feature list is to help readers compare Fred with other
solutions, especially a standalone agentic SDK. Describe macro capabilities and
the value they provide: for example roles and governance, scalable architecture,
and extensibility, where supported by the actual product. These examples guide
selection; they are not evidence that any particular guarantee is implemented.

Keep entries short, concrete and comparable. Link to explanations when useful.
Do not make a roadmap, exhaustive operation list or unsubstantiated competitor
comparison. No implementation status columns, slice IDs or acceptance scenarios.

## Main chapters and technical annexes

The main reading path explains product capabilities, architectural responsibilities,
security rules, journeys and extension principles. Every reference to source code
belongs in technical annexes: file paths, symbols, handlers, tests, generated API
inventories, SQL schema details and source maps. Explain necessary domain concepts
in the main chapters without requiring the reader to inspect their implementation.

Annexes serve Fred developers and coding assistants. Maintain useful traceability
in both directions: architectural explanation to implementation, and changed code
to the explanation it affects. Prefer stable symbols and existing generated
references over duplicated prose or fragile line numbers. Link a main chapter to
an annex when needed; do not embed a source inventory in the README or journey.

## Maintain with each feature

When adding or changing a Fred feature, read the relevant existing chapters and
update the affected explanation as part of the same work. Do not wait for a
separate documentation request. Integrate the behavior into its natural home;
do not append a new section for every code increment. Update the macro feature
list only when the change alters a capability meaningful at that level.

Keep the relevant annex references aligned with the code. Use focused source
inspection to establish behavior; old prose, a passing test name or an intended
UI flow is not sufficient evidence. Do not claim manual validation or test results
that were not observed. A change with no architectural impact needs no filler.

The agreed audience and editorial scope above authorize routine maintenance.
Ask about a genuinely new or ambiguous section's reader question and scope before
substantially filling it; do not repeatedly seek approval for agreed corrections.
This skill does not authorize broad audits, tests, commits, publication or a rewrite
of unrelated chapters. Follow the user's requested increment.

Before handing back an edit, read it as a newcomer: are terms introduced before
use, is the explanation current and useful, is detail in the correct home, and
does the section remain coherent rather than merely longer?

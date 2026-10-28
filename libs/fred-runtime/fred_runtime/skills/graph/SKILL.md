---
name: graph
description: Create or repair diagrams and charts for workflows, systems, relationships, hierarchies, timelines, plans and verified numerical data, using Mermaid for the chat renderer.
argument-hint: "[goal or source] [constraints]"
---

# Graphs

Establish the question the graph should answer and its source facts. For a
repair, preserve the intended meaning. Ask for information essential to the
result rather than inventing relationships, dates, measurements or scores.
Use supplied data or actual results from available tools for quantitative charts.
Prefer a short list or table when it conveys the information more clearly.

## Choose the representation

| What the reader needs to understand | Type |
| --- | --- |
| Steps, decisions or dependencies | Flowchart |
| Messages between participants in order | Sequence diagram |
| States and the events that change them | State diagram |
| Classes, members and their relationships | Class diagram |
| Entities, attributes and cardinalities | Entity relationship diagram |
| Ideas organized around a central topic | Mindmap |
| Events or milestones in chronological order | Timeline |
| Scheduled tasks, durations and dependencies | Gantt chart |
| A few verified parts of one total | Pie chart |
| Verified category comparisons or change over time | XY bar or line chart |
| User activities, actors and supplied experience scores | User journey |
| Git branches, commits and merges | Git graph |

Before drafting, read the selected type's section in
[syntax and examples](references/syntax-and-examples.md). Read
[compatibility](references/compatibility.md) for advanced or imported syntax,
version questions, external resources or rendering failures. Choose the type
that answers the question; a flowchart is not a universal substitute.

## Draft and deliver

- Keep labels concise and in the user's language, including accents. Use simple,
  stable identifiers where the chosen syntax requires them. Keep identifiers and
  display labels distinct; follow that type's quoting and relationship rules.
- Use the smallest useful graph, with one statement per line. Split dense graphs
  into focused views. Let the chat supply colors and typography; use text and
  built-in shapes rather than HTML, scripts, click handlers or remote images.
- Return a complete fenced `mermaid` block in chat. Its first line is the chosen
  diagram declaration. A Mermaid mindmap also uses a `mermaid` fence. Do not send
  the source to an HTML artifact tool or wrap it in HTML.
- Introduce it with a normal caption about the subject. Explain assumptions or
  important limitations, without discussing the rendering engine unless asked.
- Check that every relationship references the intended element, blocks and
  quotes are closed, and the graph agrees with the source. Use a parser or render
  check only if an appropriate tool is available; report only checks actually
  performed. If validity remains uncertain, simplify or use a list or table.

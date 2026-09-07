# How do I use Mermaid diagram design?

When you include Mermaid diagrams, follow these rules strictly so the diagram always parses:

1. Never emit intentionally invalid or fragile Mermaid, even to demonstrate a failure mode or "tricky syntax" someone asked for — explain risky patterns in normal prose instead.

2. Output Mermaid only as a complete, valid diagram inside a `mermaid` fence:

   - No placeholder Mermaid fences: no partial or intentionally broken examples.
   - To discuss Mermaid syntax, or show a literal example, without rendering it: use inline code or a `text` fence labeled as non-rendered — never nest a `mermaid` fence inside another, wrap it in a four-backtick fence, or echo the fence's own opening/closing backticks inside its body.
   - The fence body starts directly with `flowchart TD` or `graph TD` — never with backticks, `subgraph`, a node, or an edge.

3. Default to `flowchart TD` or `graph TD`. Use the smallest diagram that answers the request; split it or switch to a Markdown list/table if it gets too complex.

4. Quote every node label — `ID["Label text"]` — and never write `ID[Label text]` once the text has spaces, punctuation, or parentheses.

5. Keep labels short, plain ASCII: letters, numbers, spaces, and simple hyphens only. No emojis, markdown, raw HTML (`<b>`, `<br/>`, ...), embedded or escaped quotes, or bracket characters — rewrite accented or special text into simple ASCII (e.g. `DB_CLUSTER["Donnees Cluster"]`, not `DB_CLUSTER["Données \"Cluster\" 🗃️"]`) and check the result is still readable. If a label needs a line break or formatting, shorten it and move the detail to the prose around the diagram.

6. Node IDs: letters, numbers, and underscores only (`API_1`, `DB_MAIN`) — no accents, spaces, hyphens, dots, or emojis. Always reference a node by its ID, never by its label text — wrong: `A --> LLM Azure`; right: declare `LLM_AZURE["LLM Azure"]` on its own line, then write `A --> LLM_AZURE`.

7. Edges: only `A --> B` and `A -->|text| B`, with plain ASCII edge text. Drop a long or complex edge label rather than fight the syntax, and avoid `-.->`, `==>`, and other exotic variants unless there is no simpler option.

8. Subgraphs: at most one nesting level, ASCII ids and titles. Prefer an untitled `subgraph ID` / `end` block; do not write subgraph titles with node-label syntax such as `subgraph SUBGRAPH_ID["Title"]` — for a visible title, add a plain node inside the subgraph instead. Avoid mixing several direction overrides.

9. One Mermaid statement per line — one node, edge, or subgraph boundary — never two declarations sharing a line, even where Mermaid would accept it.

10. Avoid styling and advanced syntax (`style`, `classDef`, `class`, `linkStyle`, `click`, custom directives) unless genuinely necessary, and never mix several styling mechanisms in the same diagram.

11. Before returning, re-check: the fence opens with `flowchart TD`/`graph TD` and nothing else, there is no four-backtick wrapping, every opened subgraph is closed, every special-character label is quoted and ASCII-only, every edge endpoint is a node ID rather than label text, no line holds two declarations, and the diagram is Mermaid v11 compatible.

12. If you are unsure the diagram will parse, return a Markdown list or table instead of Mermaid.

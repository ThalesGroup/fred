When you include Mermaid diagrams, follow these rules strictly so the diagram always parses:

1. Do not intentionally generate invalid or fragile Mermaid:
- Even if the user asks for a Mermaid diagram "that may fail", "that stresses the renderer", or "with tricky syntax", stay inside the safe subset below
- Do not try to demonstrate Mermaid failure modes by emitting broken Mermaid
- If the user wants risky patterns, explain them in normal Markdown prose instead of putting them in the Mermaid code block

2. Output Mermaid inside fenced code blocks only:
- Use a Markdown fence tagged `mermaid` when, and only when, you are returning a complete valid diagram
- Do not show placeholder Mermaid fences such as three dots, partial snippets, or intentionally broken examples
- If you need to explain Mermaid syntax, use inline code or a `text` fence so the renderer does not try to execute it
- Inside a Mermaid fence, do not include the opening or closing backticks themselves; the diagram text must start directly with `flowchart TD` or `graph TD`
- Never nest a Mermaid fence inside another Mermaid fence
- Never wrap a Mermaid fence inside a four-backtick Markdown fence
- If you want to show a literal Mermaid example instead of rendering it, use a `text` fence and label it as non-rendered

3. Prefer simple flowcharts over fancy Mermaid features:
- Default to `flowchart TD` or `graph TD`
- The first non-empty line inside every Mermaid fence must be `flowchart TD` or `graph TD`
- Never start a Mermaid diagram directly with backticks, `subgraph`, a node declaration, or an edge
- Use the smallest diagram that answers the request
- If the content becomes too complex, split it into simpler nodes or switch to a Markdown list/table

4. For flowcharts, always quote node labels:
- Use `ID["Label text"]`
- Never use `ID[Label text]` when text has spaces, punctuation, HTML, or parentheses

5. Keep visible labels plain and conservative:
- Prefer short ASCII labels only
- Use letters, numbers, spaces, and simple hyphens only inside labels
- Do not use emojis, markdown, backticks, or decorative symbols in labels
- Do not use embedded double quotes inside labels
- Do not use backslash escapes such as `\"` or `\'`
- Do not use raw HTML tags such as `<b>`, `<i>`, `<span>`, or `<br/>`
- Do not use bracket characters, braces, or parentheses inside labels unless absolutely unavoidable
- If the natural wording contains quotes, accents, or special symbols, rewrite it in simpler ASCII
- Example: use `DB_CLUSTER["Donnees Cluster"]`, not `DB_CLUSTER["Données \"Cluster\" 🗃️"]`

6. Do not rely on HTML for layout:
- Do not use `<br/>` for line breaks
- Do not use bold, italic, spans, or inline HTML formatting in Mermaid labels
- If a label would need line breaks or formatting, shorten it and move the detail to the prose around the diagram

7. Keep node IDs simple and stable:
- Letters, numbers, and underscores only (for example `API_1`, `LB2`, `DB_MAIN`)
- Do not use accents, spaces, hyphens, dots, or emojis in IDs

8. Use only the safest edge syntax:
- `A --> B`
- `A -->|text| B`
- Keep edge text simple ASCII too
- If edge text would be long or complex, remove the edge label entirely
- Do not use `-.->`, `==>`, `.->`, or other exotic edge variants unless there is no simpler alternative
- Do not put quote characters, HTML, fake arrows, or Mermaid syntax fragments inside edge labels

9. Keep subgraphs conservative:
- Use at most one nesting level
- Keep subgraph IDs and titles ASCII and simple
- Prefer untitled subgraphs: use `subgraph SUBGRAPH_ID` on its own line, then close with `end`
- Do not write subgraph titles with node-label syntax such as `subgraph SUBGRAPH_ID["Title"]`
- If a visible title is needed, add a normal node inside the subgraph, for example `TITLE["Title simple"]`
- Do not put emojis or special symbols in subgraph names
- Do not mix many different direction overrides unless the structure is still very simple

10. Write one Mermaid statement per line:
- One node declaration per line
- One edge declaration per line
- One subgraph declaration or closing line per line
- Never place two declarations on the same line, even if Mermaid sometimes accepts it

11. Avoid styling and advanced syntax unless absolutely necessary:
- No custom directives or macros
- Avoid `style`, `classDef`, `class`, and `linkStyle` in default behavior
- Avoid `click`, inline styles, comments with special symbols, and unusual shape syntax unless absolutely necessary
- Do not mix several styling mechanisms in the same diagram

12. Keep examples renderer-safe:
- Do not put invalid, partial, or "bad" Mermaid examples inside `mermaid` fences
- Do not use four-backtick fences to display Mermaid syntax examples
- When contrasting good and bad Mermaid syntax, put both examples in `text` fences or describe the bad pattern in prose
- A `mermaid` fence should contain only the final diagram that you expect the frontend to render successfully

13. Before returning, self-check:
- The first line inside the Mermaid fence is `flowchart TD` or `graph TD`, not backticks
- The response contains no four-backtick fence around Mermaid content
- Every opened subgraph is closed
- No subgraph line contains brackets or quoted labels
- No line inside the Mermaid fence starts with triple backticks
- Every node label with special characters is quoted
- No label contains emojis
- No label contains escaped quotes
- No label contains raw HTML
- No edge label contains tricky syntax
- No declaration shares its line with another declaration
- Every label and edge text is still readable after simplifying to ASCII
- The diagram is Mermaid v11 compatible

14. If you are unsure the Mermaid will parse, do not return Mermaid, return a simpler Markdown list or table instead.

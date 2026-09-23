# Slide patterns

The frame (`deck-frame.html`) is copied verbatim; slides are written with the
patterns below. Every block keeps the height of its content and the body
centres the group vertically — never stretch a block to fill space. Curly
braces are placeholders to replace with real content from the spec and code.

## Slide skeleton

```html
<section class="slide" data-part="{1-5, 0 for title/agenda}">
  <p class="kicker">{Part n} · {subject} <span class="sub">· {detail}</span></p>
  <h2>{One full sentence, ≤ 14 words, the message of the slide}</h2>
  <p class="lede">{One line: what the reader is looking at and why it matters}</p>
  <div class="body">
    {one main block, optionally a second that explains it}
  </div>
  <p class="takeaway">{optional: the consequence, one sentence}</p>
</section>
```

Title: `<section class="slide title" data-part="0">` with `h1`, a `.lede` in
plain words (what changes for whom), and a `.meta` row (talk type, slide
count, date, `.chips` of the sub-projects touched). Agenda: `.body.agenda`
with five `<div><div class="n">1</div><h3>{part}</h3><p>{what it answers}</p><small>slides a–b</small></div>`.
Divider: `<section class="slide divider" data-part="n">` with `.kicker`,
`.body` holding `<div class="n">n</div><h1>{the part's message}</h1>`, then
`.contents` listing `<span><b>{slide no}</b> {title}</span>`.

## Sub-project chip — before every path, everywhere

`<span class="chip c2">fred-runtime</span> capabilities/skills/registry.py`
— assign `c1…c8` once per sub-project and keep it for the whole deck.

## Impact map (one tile per sub-project, all of them)

```html
<div class="body grid cols4">
  <div class="group">libs/</div>
  <div class="tile c1"><b>{fred-sdk}</b><div class="cnt">{4}</div><p>{one line: what changes}</p><div class="badges"><i class="mod">~3</i><i class="del">−1</i></div></div>
  <div class="tile c8 same"><b>{fred-core}</b><div class="cnt">0</div><p>untouched</p></div>
  <div class="group">apps/ · deploy/</div>
  …
</div>
```

## Touch map (what changes in one sub-project, one card per module)

```html
<div class="body grid cols3">          <!-- cols2 for 4 cards, cols3 for 5–6, cols4 for 7–8 -->
  <div class="group">{libs/fred-sdk/fred_sdk/contracts/}</div>
  <div class="card mod"><span class="tag">~</span><b class="name">{MCPServerConfiguration}</b>
    <small><span class="chip c1">fred-sdk</span> {contracts/models.py · l. 209}</small>
    <p><span class="minus">− {agent_instructions}</span> · <span class="plus">+ {skills}</span> — {what it means, ≤ 12 words}</p></div>
  <div class="card add"><span class="tag">+</span>…</div>
  <div class="card del"><span class="tag">−</span>…</div>
  <div class="card same"><span class="tag">=</span>…</div>
</div>
```

## Vocabulary (≤ 4 terms) and numbers (≤ 3)

```html
<div class="body grid cols4">
  <div class="card sec"><h3>{Term}</h3><p>{definition, one sentence}</p><div class="ex">{a real example: path, command, value}</div></div>
</div>
<div class="body stats">
  <div><div class="n">{3.3 KB}</div><div class="l">{what it measures}</div><div class="s">{source in the repo}</div></div>
</div>
```

## Panel pair (what a person or the model receives, before / after)

```html
<div class="body duo">
  <div class="panel"><h3>{Today · <span class="chip c3">fred-agents</span> mcp_catalog.yaml}</h3>
    <pre><span class="line">{unchanged line}</span><span class="line del">{removed line}</span><span class="line add">{added line}</span><span class="line c">{← comment}</span></pre></div>
  <div class="panel"><h3>{After brick 1}</h3><pre>…</pre></div>
</div>
```
Real text from the repo, ≤ 12 lines of ≤ 60 characters; trim to the lines
that change plus two lines of context.

## Table (implications, comparison, divergences, questions)

```html
<div class="body"><table>
  <thead><tr><th>{Criterion}</th><th class="opt">{Option 1}</th>…</tr></thead>
  <tbody><tr><td>{row}</td><td class="add dot">{≤ 6 words}</td><td class="mod dot">…</td><td class="del dot">…</td></tr></tbody>
</table></div>
```
Up to 8 rows when cells stay on one or two lines. **A table never sits alone**:
with fewer than 7 rows it gets a context column beside it, and every table
gets a takeaway under it — the one conclusion the reader should leave with.

```html
<div class="body split">
  <table>…</table>
  <div class="notes"><h3>{How to read it / why it matters}</h3>
    <p>{Two sentences of context: what this decides, what happens if it is ignored}</p>
    <ul><li>{key fact or consequence}</li><li>{what to do next}</li></ul></div>
</div>
<p class="takeaway">{the conclusion of the table, one sentence}</p>
```

## Diagrams (flows, architectures, lots, sequences)

Generated: `scripts/diagram.py flow|seq spec.json --caption "…"` prints a
complete `<figure class="diagram">` — paste it as the body's main block; it
takes the remaining height. Specs: columns of nodes + explicit edges (flow),
participants + numbered steps + phase bands (seq); see the script's docstring.
Every node that is code carries a chip; the legend is built from what is used.

## Option slide, phases strip, recommendation

```html
<div class="body">
  {figure from diagram.py flow — the lots and their "must be merged before" arrows}
  <div class="proscons">
    <div class="pro"><h3>For</h3><ul><li>{≤ 14 words}</li></ul></div>
    <div class="con"><h3>Against</h3><ul><li>…</li></ul></div>
  </div>
</div>
<div class="phases">
  <div class="ext"><b>Lot 0 · spike</b>{…}</div><div class="mod"><b>Brick 1</b>{…}</div><div class="add"><b>Brick 3</b>{…}</div><div class="del"><b>Brick 5</b>{…}</div>
</div>
<p class="reco">{Recommendation in one sentence, and the title of the first issue}</p>
```

## Appendix

`<section class="slide appendix" data-part="5">`: full paths, line numbers,
today/after, ≤ 6 rows per slide at normal type (`table.dense` is 15 px, not
smaller) — split across slides so nothing scrolls. Each appendix slide keeps
the lede ("behind slides 14–16, for whoever opens the first PR") and a
`.notes` column or a takeaway saying what to do with the rows (which file to
open first, which line is the risky one). An appendix slide that is a lone
small table in an empty frame is a bug, not an appendix.

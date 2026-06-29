# PPT Filler Toolkit — PRD / RFC

Status: Draft
Provider key: `ppt_filler`
Area: Agentic Backend (inprocess toolkits, agent tuning) + Frontend (agent creation form)

---

## Problem Statement

Agent creators frequently need an agent to take unstructured source material (a resume,
a project brief, financial figures) and produce a **branded, formatted PowerPoint
deliverable** — not free-form prose. Today this is only possible by forking Fred and
hand-coding a bespoke agent (as was done in the `ppt_filler` POC), with hardcoded slide
indices, a fixed brace notation, and a fixed extraction schema baked into Python. A
non-developer creating an agent cannot:

- bring their **own** PowerPoint template,
- have Fred figure out **what the agent must fill in** from that template,
- get **clear, early feedback** when the template is misconfigured (before the agent is
  even saved), or
- get an agent whose fill tool **matches the template they uploaded**.

As a result, "fill my PowerPoint template" is a one-off engineering task instead of a
self-service capability in the agent creation form.

## Solution

A generic, self-service **PPT Filler toolkit** that any agent creator can enable from the
agent creation form. When enabled, the creator uploads a `.pptx` template. Fred analyzes
it and extracts, **per slide**:

- the template **keys** written as `{{key}}` inside text boxes, and
- a human **description** for each key, written in that slide's **notes**.

The creator sees the extracted schema and any configuration errors **immediately and
inline** — before saving — with the **slide number** and a clear explanation for each
error. Once saved, the agent gains a fill tool whose **input shape is derived from the
template** (grouped by slide). At chat time the agent extracts values from the
conversation/documents, calls the tool, and the user receives a **download link** to the
filled deck.

The uploaded template is the **single source of truth**: the schema is always recomputed
server-side from the actual file, and recomputed whenever the template is replaced.

The toolkit is built on a **generic, reusable seam** ("toolkit asset processor") so that
future toolkits needing an uploaded document processed at save time can plug in the same
way, without new endpoints or bespoke save logic.

## User Stories

### Discovering & enabling the toolkit

1. As an agent creator, I want to see "PPT Filler" available in the agent's tools/toolkits
   selection, so that I can enable PowerPoint-filling for my agent.
2. As an agent creator, when I enable PPT Filler, I want a dedicated configuration form
   (not the generic workspace/asset manager), so that I am not asked to invent or pick a
   storage key.
3. As an agent creator, I want the PPT Filler configuration to live inline in the agent
   creation/edit form alongside other tool parameters, so that configuring it is part of
   the normal agent-authoring flow.

### Uploading the template

4. As an agent creator, I want to upload a `.pptx` file from the configuration form, so
   that the agent fills *my* template rather than a generic one.
5. As an agent creator, I want the upload control to only accept PowerPoint files, so that
   I don't accidentally upload the wrong file type.
6. As an agent creator, I want exactly one template per agent (replacing it swaps the
   template), so that the configuration stays simple and unambiguous.
7. As an agent creator editing an existing agent, I want to replace the template with a new
   `.pptx`, so that I can iterate on the deck without recreating the agent.
8. As an agent creator, I want unrelated edits (changing the role, description, prompt, or
   other fields) to **not** require me to re-upload the template, so that small edits are
   frictionless.

### Analysis & immediate feedback

9. As an agent creator, when I pick a template, I want Fred to analyze it immediately and
   show me the extracted keys and their descriptions, so that I can confirm the agent will
   fill the right things.
10. As an agent creator, I want the extracted keys grouped **by slide**, so that I can see
    which fields belong to which slide.
11. As an agent creator, I want each extracted key shown together with the description I
    wrote in the slide notes, so that I can verify my descriptions are correct.
12. As an agent creator, when my template is misconfigured, I want to see each error with
    the **slide number** and a clear explanation, so that I know exactly what to fix.
13. As an agent creator, I want to be told when a key appears on a slide but has **no
    description** in that slide's notes, so that I add the missing guidance.
14. As an agent creator, I want to be told when my notes describe a key that **does not
    appear** in that slide's text boxes, so that I fix the typo or remove the stale
    description.
15. As an agent creator, I want this feedback **before** I save the agent, so that I never
    save a broken configuration.
16. As an agent creator, I want errors displayed in my own language, so that the feedback
    is understandable (error messages are i18n-driven via stable error codes).

### Authoring the template (notes format)

17. As a template author, I want to write keys as `{{key}}` inside any text box on a slide,
    so that the agent knows where to place values.
18. As a template author, I want to describe a key by writing `{{key}}:` on its own line in
    the slide notes followed by free-text (possibly multiline) description, so that I can
    give the agent guidance on what to put there.
19. As a template author, I want to describe several keys at once with a single
    `{{a}}, {{b}}:` header line, so that I don't repeat the same description for related
    keys.
20. As a template author, I want to reuse the **same key multiple times on one slide** (it
    is filled in every occurrence on that slide), so that I can repeat a value (e.g. a name
    in a header and a footer).
21. As a template author, I want the **same key on different slides** to be treated
    independently (its own description, its own value), so that slide-local context is
    respected.
22. As a template author, I want my description text to be able to mention `{{...}}` inline
    without it being mistaken for a key header, so that I can write natural guidance.

### Saving

23. As an agent creator, I want saving the agent to atomically upload the template, compute
    the schema, and store it, so that I never end up in a half-configured state.
24. As an agent creator, if the template has configuration errors at save time, I want the
    save to fail with the same clear, slide-numbered errors, so that the persisted agent is
    always valid.
25. As an agent creator, if PPT Filler requires a template and I have not provided one, I
    want the Save button disabled and (defensively) the request rejected, so that I cannot
    create a non-functional agent.
26. As an agent creator, I want the actual template file to be the source of truth for the
    schema (the backend recomputes it), so that what the agent fills always matches the real
    deck.

### Using the agent (chat time)

27. As an end user chatting with a PPT Filler agent, I want the agent to extract the needed
    values from my message/attached documents and fill the template, so that I get a
    finished deck without manual data entry.
28. As an end user, I want the agent's fill tool to "know" the structure of the template
    (which fields, grouped by which slide, with descriptions), so that it fills the right
    values in the right places.
29. As an end user, I want to receive a **download link** to the filled `.pptx`, so that I
    can open and use the result.
30. As an end user, I want each occurrence of a key on a slide filled consistently, so that
    repeated placeholders (header/footer) all get the same value.

### Future-facing / platform

31. As a platform developer, I want a single clear extension point ("toolkit asset
    processor") for any future toolkit that uploads a document and derives configuration from
    it at save time, so that I don't have to add a new endpoint or bespoke save logic per
    toolkit.
32. As a platform developer, I want a toolkit to declare whether its asset is **mandatory**
    and what file types it accepts, so that the UI and backend enforcement are driven by
    declarative metadata rather than special-cased code.

## Implementation Decisions

### Provider & registration

- New inprocess toolkit provider key: **`ppt_filler`** (snake_case, consistent with
  `kf_vector_search`).
- Registered as a tool factory in the inprocess toolkit factory registry (same registry
  used by `kf_vector_search`, `writable_documents`, `web_github_readonly`).
- Advertised to the UI via an **MCP catalog entry** (`transport: inprocess`,
  `provider: ppt_filler`) so it is selectable in the agent's tool picker.
- A typed params model **`PptFillerParams`** is added to the `ToolParams` discriminated
  union (discriminated by `provider`), mirroring `KfVectorSearchParams`.

### Schema shape (the data contract)

The extracted template schema is **grouped by slide**, not a flat key list:

```
[
  { "slide": 2, "keys": [ { "key": "name", "description": "..." }, ... ] },
  { "slide": 5, "keys": [ { "key": "name", "description": "..." } ] }
]
```

- `slide` is the 1-based slide number as the author sees it.
- The **same key string on different slides is two independent fields** with independent
  descriptions and independent values.
- A reserved place exists for a future per-slide `slide_purpose` describing the whole
  slide; not implemented now.

### `PptFillerParams`

- Carries the **derived schema** (the per-slide structure above) — persisted.
- Carries a **fixed template key** convention (one template per agent, e.g.
  `ppt_filler_template.pptx`); the creator never chooses it.
- Carries a **transient base64 upload field** used only to transport the new `.pptx` bytes
  from the form to the backend on save. This field is **stripped before persistence** and
  must never reach the store.

### Parsing & validation (analyze)

- **Keys** are extracted from text-frame shapes (`has_text_frame`) using a run-merging
  traversal that reconstructs `{{key}}` even when PowerPoint splits it across runs. Regex:
  `\{\{([^}]+)\}\}`.
- **Descriptions** are parsed from slide **notes**. A line is a **header** only if it
  matches `^\s*\{\{key\}\}(\s*,\s*\{\{key\}\})*\s*:\s*$` (one or more comma-separated keys,
  optional surrounding whitespace, ending in `:`). Any other line is description text
  (including lines that merely contain `{{...}}` inline). Lines following a header — blank
  lines included — form that header's multiline description until the next header or end of
  notes; leading/trailing blank lines are trimmed.
- A multi-key header applies the **same description** to each listed key.
- **Validation is per-slide.** For each slide, the set of text-box keys and the set of
  described keys must match. Two error cases, both reported with the slide number:
  - `key_without_description` — a `{{key}}` appears in a text box on slide N but has no
    description in slide N's notes.
  - `described_but_not_in_slide` — slide N's notes describe `{{key}}` that never appears in
    a text box on slide N.
- A key appearing in **multiple text boxes on the same slide** is valid (deduped to one
  schema field for that slide; filled in every occurrence on that slide).

### Shared parse ↔ fill traversal

- A **single** text-frame-walking utility is used by **both** the analyzer (list all
  `{{keys}}` on a slide) and the filler (replace `{{keys}}` on a slide). They must never
  diverge: any key the parser surfaces must be fillable, and vice versa.

### Fill tool (chat time)

- The tool's dynamic `args_schema` is **nested by slide** (derived from the persisted
  schema):

```
{
  "slide_2": { "name": "<value>", "role": "<value>" },
  "slide_5": { "name": "<value>" }
}
```

  Each slide group is an object keyed by `slide_<n>` (1-based). Each leaf property carries
  its note **description** as the schema-level description so the model gets inline
  guidance. The grouping is intentional so the agent understands slide-local context. (The
  future `slide_purpose` would become the per-slide object's description.)
- Filling ports the POC's run-merging replacement logic but driven **per-slide from the
  schema** — no positional `zip`, no hardcoded slide indices, `{{double}}` braces.
- Output: render to a temp file, upload to **user storage** (session-scoped
  `upload_user_blob`), and return a `LinkPart(kind=download)` for the UI download button.
- Shape coverage: the traversal walks `has_text_frame` shapes, **table cells**, and
  **grouped shapes** (recursively). SmartArt (`DIAGRAM`/`IGX_GRAPHIC`) and chart text are
  still **not** supported (no clean `text_frame` API in python-pptx) and are documented as
  such rather than silently dropped.

### Save flow — generic "toolkit asset processor" seam

A reusable abstraction so this and future toolkits process uploaded assets uniformly at
save time:

- A **`ToolkitAssetProcessor`** contract: a pure `params → params` transform that may
  upload a config blob and derive params, raising a typed error on invalid input.
- A **registry** of processors keyed by provider, parallel to the tool-factory registry.
- Declarative metadata per processor: **`asset_required`** and accepted file types, read by
  both the UI (to gate Save and configure the upload control) and the backend (to enforce).
- A **single generic hook** in the agent create/update service: for each
  `mcp_server.params` whose provider has a registered processor, run it; persist the
  **returned** (processed) params.

Processor behavior is **conditional on the presence of upload bytes**:

| Incoming params state | Action |
| --- | --- |
| Upload bytes **present** | Upload blob (fixed key), **re-parse server-side**, write schema, **strip bytes** |
| Bytes **absent**, schema **present** | **No-op** pass-through (ordinary edit; template unchanged) |
| Bytes **absent**, schema **absent**, asset **mandatory** | Reject — fail create/update |

- The **uploaded file is the source of truth**; the frontend's inline analyze is preview
  only. The backend always re-parses the actual bytes on save and persists *that* schema.
- Bytes transport **inside the typed params as base64** (Decision A): the save stays a
  single atomic call and the processor stays a pure `params → params` transform. Hard
  invariant: processors strip the raw upload field before persistence.

### API contracts

- **Analyze (inline, stateless):** an endpoint that accepts a `.pptx` and returns
  `200 { schema, errors }`. Stateless — it stores nothing (no agent instance exists yet at
  configuration time). Used purely for instant preview + error display in the form.
- **Save (atomic, source of truth):** the existing agent create/update path. When the
  toolkit params carry upload bytes, the generic processor uploads + re-parses + stores.
  On validation failure the request fails with **422** carrying the structured errors.
- **Shared error contract** (identical shape for analyze and save):

```
{ "errors": [
    { "slide": 5, "key": "ghost", "code": "described_but_not_in_slide",
      "message": "{{ghost}} is described in the notes of slide 5 but never appears in a text box on that slide." },
    { "slide": 2, "key": "age", "code": "key_without_description",
      "message": "{{age}} appears on slide 2 but has no description in the slide notes." }
] }
```

  `code` is the stable, machine-readable key the frontend maps to an i18n message;
  `message` is an English fallback. Analyze returns `200`-with-errors (so schema and errors
  show together); save returns `422` when errors are non-empty.

### Frontend

- A new entry in the tool-params registry keyed by `ppt_filler`, rendering a **custom
  configuration form** that: uploads/selects the `.pptx`, calls the analyze endpoint on
  file pick, previews the per-slide schema, and renders slide-numbered errors (i18n by
  `code`).
- The form holds "did the user pick a new file this session?" state so that the base64
  upload is only sent when the template is actually (re)placed — ordinary edits send params
  without bytes.
- Save is disabled while the mandatory template is missing; the existing create-mode
  rollback (delete the just-created agent on tuning failure) covers a failed atomic save.
- Regenerated OpenAPI types include `PptFillerParams`.

### Storage

- The template lives in the **agent config blob store** (admin/agent-config scoped),
  uploaded under the fixed per-agent key. Filled outputs go to **user storage**
  (session-scoped), surfaced as a download link.

## Testing Decisions

Good tests here assert **external behavior** — given a `.pptx`, what schema and what error
codes/slide numbers come out; given params, what the processor persists — not the internal
traversal mechanics. Tests are offline and fixture-driven (small `.pptx` files built in-test
or checked in as fixtures). Prior art: `tests/test_kf_vector_search_tools.py` (same
inprocess-toolkit family and params pattern) is the template for structure and style.

Seams, highest first:

1. **Parser/validator** (`parse(.pptx) → { schema, errors }`) — the core seam. Pure, no
   I/O. Tests assert:
   - per-slide grouping of keys;
   - same key on two slides → two independent fields;
   - same key twice on one slide → one field;
   - multi-key header (`{{a}}, {{b}}:`) → both keys get the shared description;
   - description containing inline `{{...}}` is not mistaken for a header;
   - multiline descriptions (including internal blank lines) captured;
   - `key_without_description` and `described_but_not_in_slide` produce the right `code`
     and `slide` number.

2. **Shared parse ↔ fill round-trip** — guarantees parser and filler cannot silently
   diverge. `parse(deck) → fill(values for every field) → re-parse` expects no remaining
   `{{keys}}`. This is the single most important regression guard for the feature.

3. **`ToolkitAssetProcessor`** (`params → params`, storage faked/injected). Tests assert:
   - upload bytes present → schema computed and persisted, base64 bytes **stripped** from
     the returned params (persisted params never contain the upload field);
   - bytes absent + schema present → no-op pass-through;
   - bytes absent + schema absent + `asset_required` → raises / rejects.

4. **Analyze endpoint** — a thin HTTP smoke test asserting the `200 { schema, errors }`
   shape (most logic already covered by seam 1).

## Out of Scope

- SmartArt (`DIAGRAM`/`IGX_GRAPHIC`) and chart text as key sources: python-pptx exposes
  no clean `text_frame` for them (text lives in low-level DrawingML XML). Text boxes,
  table cells, and grouped shapes **are** supported.
- The future `slide_purpose` notation describing a whole slide's purpose (reserved in the
  schema shape; not implemented).
- Multiple templates per agent (v1 is one template per agent; replacing swaps it).
- Multipart/streamed binary upload transport (v1 carries bytes as base64 inside params).
- Any LLM-side extraction logic specific to a domain (resume/CV/financials). The toolkit is
  generic; domain guidance lives in the agent's system prompt, authored by the creator.
- Localization of the template content itself (only the *error messages* are i18n).

## Further Notes

- **Highest-risk watch-points** (call out in review):
  1. The strip-before-persist invariant is the only thing keeping multi-MB base64 blobs out
     of the agent store — covered by a processor test asserting persisted params never
     contain the upload field.
  2. The shared parse/fill traversal — if these diverge, failures are silent (the agent
     fills a value that never lands) — covered by the round-trip test.
- The POC (`ppt_filler_agent.py`, `export_tools.py`, `powerpoint_template_util.py` in the
  prism fork) is the reference for the run-merging fill algorithm and the
  fetch-config-blob / upload-user-blob / `LinkPart` output pattern. This PRD generalizes the
  POC: removes hardcoded slide indices and the fixed extraction schema, switches `{name}` →
  `{{name}}`, and moves template + schema from code into per-agent configuration.
- The generic toolkit-asset-processor seam is intended to outlive this feature: it is the
  sanctioned path for any future toolkit that uploads a document and derives configuration
  from it at save time.

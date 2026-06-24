# RFC: Knowledge Flow — Excel-as-Document Ingestion (faithful-layout Markdown for RAG)

**ID:** XLSX-DOC · **Status:** draft (awaiting developer confirmation)
**Author:** Dimitri Tombroff
**Date:** 2026-06-23
**Scope:** swift `apps/knowledge-flow-backend` — a new **input processor** (no new
pipeline, no contract change)
**Extends:** the existing markdown ingestion path (`BaseMarkdownProcessor` →
`output.md` → `VectorizationProcessor`). Mirrors `DocxMarkdownProcessor` /
`LiteCsvMarkdownProcessor`.
**Related:** `CORPUS-REVECTORIZE-RFC.md` (MIGR-07 — re-vectorisation reuses the
`output.md` this processor writes), `RAG-AGENT-QUALITY-RFC.md` (the RAG consumer),
`KNOWLEDGE-FLOW-SIMILARITY-SEARCH-RFC.md`.
**Contract impact:** **additive only.** New `.xlsx/.xls/.xlsm` rows in the processor
registry + `EXTENSION_CATEGORY`. No change to frozen contracts, no new endpoint, no
new output processor.

---

## 1. Decision (one paragraph)

Add a single new input processor, **`XlsxMarkdownProcessor(BaseMarkdownProcessor)`**,
that converts an Excel workbook into a **layout-faithful Markdown document** (`output.md`)
and lets it flow through the **existing** vectorization/RAG path unchanged. Excel is
treated here as a **document to read and question**, not as a dataset to compute over.
Clean rectangular data that belongs in SQL is already served by the existing **CSV/tabular
path** and is explicitly out of scope (see §3). The goal is a *simple, powerful* "ask
questions about my Excel" assistant, achieved by reusing every stage downstream of
extraction and writing only one new converter.

---

## 2. Problem (functional)

Enterprise users have many Excel files and a natural, recurrent request: *"let me question
my Excels."* The request is vague because "Excel" is not one thing. We disambiguate on two
axes:

- **Shape** — a *clean table* (one header row, rows = records) vs a *document* (merged
  cells, titles, sub-totals, several blocks per sheet, formatting that carries meaning).
- **Intent** — *read/question* the content vs *compute* over the data (sum, filter,
  aggregate).

A clean table where the user wants to compute is a CSV problem and **already solved** by
the tabular path (DuckDB/Parquet/SQL). The **unserved** quadrant — and the one this RFC
targets — is **Document × Read**: messy, layout-bearing spreadsheets that the user wants to
ask questions about in natural language. Today `.xlsx` is **not ingestible at all** (no
processor is registered in any profile; only an attachment-only `FastSpreadsheetProcessor`
exists). This RFC fills exactly that gap and nothing more.

## 3. Non-goals (scope fence)

- **No analytical/numeric query path.** We do not route Excel to DuckDB/SQL. "Sum column C
  where B = X" over flattened text is unreliable; that is the tabular path's job, and a
  user who needs it should ingest the relevant sheet as CSV. Stated here so the two paths
  never get merged.
- **No per-file / per-template processors.** The long tail of bespoke templates is handled
  later by a pluggable registration mechanism, *if and when* a recurring template is
  identified. It must not block this generic v1.
- **No formatting-as-data extraction in v1** (e.g. cell colour ⇒ "status: OK"). Markdown
  loses it; we add it only if the need is demonstrated (§7).
- **No new chunking, embedding, vector-store, or contract work.** All reused verbatim.

## 4. What already exists (extend, do not duplicate)

| Building block | Location | Reuse |
|---|---|---|
| `BaseMarkdownProcessor.convert_file_to_markdown()` contract (writes `output/output.md`) | `core/processors/input/common/base_input_processor.py` | **implement** for xlsx — same contract as PDF/DOCX |
| Markdown table annotation `<!-- TABLE_START:id=N -->…<!-- TABLE_END -->` | `pdf_markdown_processor.py`, `docx_markdown_processor.py` | **emit the same markers** so the splitter preserves table boundaries |
| `VectorizationProcessor` (load `output.md` → split → embed → index) | `core/processors/output/vectorization_processor/` | **unchanged** — consumes our `output.md` |
| `RecursiveSplitter` with `preserve_tables: true` | `recursive_splitter.py` + `configuration.yaml` text_splitter | **unchanged** — keeps annotated tables intact |
| Profile-based processor registry (`{suffix, class_path}`) | `config/configuration.yaml` `processing.profiles.*` | **register** the new class per profile |
| `EXTENSION_CATEGORY` / `DEFAULT_OUTPUT_PROCESSORS` | `application_context.py` | **add** `.xlsx/.xls/.xlsm → "markdown"` |
| `pandas` + `openpyxl` (already deps) and `tabulate` (already used for md tables) | `pyproject.toml` | **reuse** — no new dependency |
| `FastSpreadsheetProcessor` (pandas `ExcelFile` → text, attachment path) | `core/processors/input/fast_text_processor/fast_spreadsheet_processor.py` | **reference** for read logic; not the ingestion processor |

The only genuinely new artifact is **one converter class**. Everything downstream of
`output.md` is reuse.

## 5. Design — faithful 2D → annotated Markdown

`XlsxMarkdownProcessor.convert_file_to_markdown(file_path, output_dir, document_uid)`:

1. **Open the workbook** with `openpyxl` (`data_only=True` → read computed **values**, not
   formula strings). Iterate sheets in order.
2. **Per sheet, emit a section** headed by the sheet name (`## <sheet name>`) so retrieval
   and the "map" (§6) have stable anchors.
3. **Merged-cell forward-fill.** Read `sheet.merged_cells`; propagate each merged region's
   top-left value into every covered cell before rendering, so headers/labels don't "drop
   out". This is the single most important fidelity step.
4. **Block ("island") detection.** Split each sheet into contiguous non-empty rectangular
   regions separated by fully blank rows/columns. Each block becomes one annotated Markdown
   table (`<!-- TABLE_START:id=N -->` … `<!-- TABLE_END -->`). This handles "several tables
   on one sheet" generically — no config.
5. **Render each block** as a piped Markdown table via `tabulate`. Keep in-block title and
   sub-total rows (in a *document* they carry meaning — unlike the tabular path which strips
   them).
6. **Locale normalisation (FR).** Render numbers/dates from the typed cell values, not raw
   strings, so the French decimal comma and `DD/MM/YYYY` are represented consistently. (Cell
   *values* via openpyxl are already typed; we format on output.)
7. **Write `output_dir/output.md`.** From here the standard markdown path takes over
   (PREVIEW_READY → vectorize → VECTORIZED). `extract_file_metadata()` reports sheet count
   as `page_count` and total non-empty rows as `row_count`.

Example fragment of produced `output.md`:

```markdown
## Synthèse Q3

<!-- TABLE_START:id=0 -->
| Région | CA réalisé | Objectif | Statut  |
|--------|-----------:|---------:|---------|
| Nord   |   1 240,50 | 1 200,00 | Atteint |
| Sud    |     980,00 | 1 100,00 | En retard |
| **Total** | **2 220,50** | **2 300,00** | |
<!-- TABLE_END -->
```

## 6. Retrieval strategy (no new infra in v1; v2 is a fast-follow)

- **v1 — full document in context (default, simplest, powerful).** For workbooks under a
  size threshold (token budget of the team's configured model), the faithful `output.md` is
  small enough that ordinary top-k retrieval returns the relevant block(s), and for small
  files the whole document fits in the answer context. No new code beyond §5 — this is just
  the existing RAG path doing its job over a well-structured document. **This alone satisfies
  the roadmap request.**
- **v2 — "map + drill-down" for large workbooks (separate, later RFC/backlog item).** Naïve
  vector RAG embeds rows of numbers poorly and questions are often navigational ("which
  sheet?"). For big files we give the agent a **map** (sheet names, block titles, headers —
  derivable from §5 at zero extra cost) plus a tool to **read a specific sheet/block on
  demand**. Called out so the v1 design (stable `##` anchors + block ids) is forward-
  compatible; **v2 is not built in this RFC.**

## 7. Open items / risks

- **Size threshold for v1.** Above which a workbook is too large to lean on plain RAG and
  should defer to v2. Propose a config knob (`xlsx.max_inline_cells`) with a sane default;
  large files still ingest, they just rely on chunked retrieval until v2 lands.
- **Formatting-as-meaning.** Colour/conditional-format semantics are lost in Markdown. Out
  of scope for v1; revisit only if a concrete need surfaces (would extract to a `Statut: …`
  column).
- **`.xls` (legacy binary).** openpyxl reads `.xlsx/.xlsm` only; `.xls` needs `xlrd` or an
  upstream convert. Propose: support `.xlsx/.xlsm` first, treat `.xls` as a follow-up
  (avoid a new dependency unless required).
- **Huge sheets / blow-up.** Bound rows/cols per block when rendering (reuse the
  `render_markdown_preview` truncation idea) and log when truncation occurs — never silently
  drop content.
- **Profile mapping.** Register under all profiles (fast/medium/rich) pointing at the same
  class initially; richer handling can diverge later if justified.

## 8. Verification plan

- Unit tests for the converter on fixtures covering: merged headers, multiple blocks per
  sheet, multi-sheet workbook, sub-total rows, FR locale numbers/dates, empty sheet.
- An end-to-end ingestion test: `.xlsx` → `output.md` written → vectorized → retrievable,
  reusing the existing ingestion test harness.
- `make code-quality && make test` in `apps/knowledge-flow-backend`.

## 9. Decision requested

Approve adding **one** input processor, `XlsxMarkdownProcessor(BaseMarkdownProcessor)`,
routing `.xlsx/.xlsm` through the existing markdown→vectorization path (faithful-layout
Markdown, §5), with retrieval **v1 = existing RAG over the structured `output.md`** and a
**v2 map+drill-down** deferred to a separate item. Tracked as **XLSX-DOC**. On approval:
register the id-legend entry, add the backlog item (RAG/ingestion area), and open the
GitHub execution issue per the task lifecycle.

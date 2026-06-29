# RFC: Excel Extraction — Strategies and Deterministic Reconstruction Pipeline

**ID:** INGEST-02
**Status:** proposed
**Author:** Timothé Le Chatelier
**Date:** 2026-06-26
**Scope:** `apps/knowledge-flow-backend` — Excel extraction strategy and deterministic processing pipeline
**Extends:** [EXTENSIBLE-DOCUMENT-PROCESSOR-RFC.md](EXTENSIBLE-DOCUMENT-PROCESSOR-RFC.md) (INGEST-01 — processor architecture) · [XLSX-DOCUMENT-INGESTION-RFC.md](XLSX-DOCUMENT-INGESTION-RFC.md) (XLSX-DOC — first naïve faithful-layout processor)
**Contract impact:** additive — new processor registered in the EDP registry; no change to frozen contracts, no new endpoint.

---

## 1. Decision

Adopt a **deterministic table and metadata reconstruction** approach as the primary Excel extraction strategy in Fred. This approach processes each workbook in three ordered phases (document → table → consolidation) and produces structured, traceable artifacts consumable by the existing RAG pipeline.

The two other strategies considered — multimodal LLM extraction and Excel agent with Skills — are documented here as future options, reserved for use cases that the deterministic path cannot cover. They are **not built in this RFC.**

---

## 2. Problem

An Excel file is not a neutral document. It is a composite object that can simultaneously contain:

- clean data tables (candidates for the existing CSV/DuckDB path);
- management reports with hierarchical headers, merged cells, subtotals, and non-tabular blocks (notes, isolated KPIs, labels);
- calculation formulas that carry business logic sometimes as valuable as the data itself;
- formatting (colours, indents, outline levels) that conveys meaning that raw text cannot restore.

No single extraction strategy covers this entire spectrum at reasonable cost. The choice of a strategy must be explicit, reasoned, and aligned with the reality of the files encountered.

The existing XLSX-DOC processor treats Excel files as documents to read (faithful Markdown), but does not model the internal structure of tables — no orientation detection, no targeted merge propagation, no type coercion, no schema validation. This RFC describes the complete pipeline that is missing from that first version.

---

## 3. Three extraction strategies — comparative analysis

### 3.1 Strategy A — Deterministic table and metadata reconstruction

**Approach.** Parse the workbook with `openpyxl`, identify non-empty islands (blocks), reconstruct headers (multi-level, merged), propagate merged cells, normalise types, validate schemas, and produce a set of annotated DataFrames plus a residue of non-tabular metadata.

**Strengths.**

- Reproducible, deterministic, no LLM cost at extraction time.
- Traceable step by step: every decision (orientation, header/data boundary, propagated merge) is logged.
- Covers the majority of common business cases — budgets, dashboards, structured lists — without human intervention.
- Recurring patterns identified during analysis (transposed orientation, pivot table, multi-level headers) can be captured as reusable, composable rules.

**Limitations.**

- Highly atypical tables (ad hoc structures, complex nested merges, purely visual logic) may defeat the heuristics.
- Pattern detection logic must be maintained as new edge cases emerge.
- Semantic metadata (cell colours, indentation as level indicators) is lost unless explicitly extracted (out of v1 scope).

**Decision:** strategy selected for v1 (see §5).

---

### 3.2 Strategy B — Multimodal LLM extraction (vision)

**Approach.** Render each Excel sheet as an image (via a rendering library — see §4.1) and send it to a multimodal model (e.g. claude-sonnet-4-6, GPT-4o) that extracts the structure and textual content.

**Strengths.**

- Captures visual formatting that raw text loses (colours, indents, cell styles indicating a status or hierarchy level).
- Tolerates atypical structures that a deterministic parser cannot model.
- Ideal for tables whose interpretation requires strong visual context.

**Limitations and risks.**

- **LLM bias.** A generalist model hallucinates on very dense or very sparse tables. In particular, a table where 95% of cells are empty (sparse matrix typical of a schedule or comparison grid) generates confusion: the model fills in gaps by inference, produces values absent from the source, or ignores entire columns. A complex table carrying strong business semantics (product codes, nomenclatures, technical terms) requires grounding that the model does not have without a dedicated business prompt.

- **Cost and latency.** Sending a sheet image to a vision model represents several hundred to several thousand tokens depending on resolution. For a workbook with 20 dense sheets, the cost per ingestion becomes significant. Accuracy tends to decrease as image surface grows — very wide tables suffer from resolution loss or tile splitting that breaks headers and merged cells.

- **Rendering dependency.** Extraction quality is directly tied to the fidelity of the image produced (see §4.1). An approximate render produces an approximate extraction.

- **Non-deterministic.** Two calls on the same sheet may produce different outputs. Observability is more difficult.

**Verdict:** complementary strategy, activatable as a fallback for islands that strategy A fails to parse (see §5.5). Not in the primary path.

---

### 3.3 Strategy C — Excel agent with Skills

**Approach.** Define an LLM agent equipped with tools (Skills) capable of programmatically interacting with an Excel workbook: reading a cell or range, filtering, sorting, navigating between sheets, evaluating a formula, etc. The agent orchestrates these tools to respond to an extraction or analysis request.

**Strengths.**

- Maximises expressiveness: the agent can reason about structure, choose which sheets to explore, decide how to merge ranges, and adapt its strategy to the content.
- Naturally handles non-uniform workbooks where fixed rules fail.
- Potentially capable of processing complex business logic if the Skills expose enough primitives.

**Limitations and uncertainties.**

- **Unknown scalability.** It is not yet known whether this approach is viable for very large workbooks in terms of sheet count or information density. An agent navigating a 50-sheet workbook with thousands of rows per sheet may consume a prohibitive token budget with no guarantee of full coverage.

- **Implementation complexity.** Defining a set of Skills rich enough to cover common patterns while remaining composable is a design effort in its own right. The Skills surface must be designed, tested, and documented before deployment.

- **Cost and reliability.** Each tool call is an LLM request. On complex workbooks, the number of calls can explode. Incorrect reasoning loops are difficult to detect and correct.

- **Silent regression risk.** An agent that has not found the information may invent a plausible answer rather than fail explicitly. Output validation is imperative but tricky.

**Verdict:** high-potential but high-risk strategy. Reserved for use cases where both previous strategies fail; requires a dedicated RFC before any implementation.

---

## 4. Cross-cutting challenges

### 4.1 Faithful workbook rendering

For a user to question an Excel file, the system must first *see* it as the user sees it. An openpyxl parser produces values and structures, but not a render. Strategy B (LLM vision) depends on it directly; strategy A relies on it indirectly to validate that the reconstruction matches the expected display.

Two solution families:

- **Native headless rendering.** LibreOffice in headless mode (`soffice --headless --convert-to png`) produces high-fidelity rendering at the cost of a heavy dependency and a few seconds of latency per sheet.
- **Python rendering.** Libraries such as `xlwings` (Windows/Mac only), `openpyxl-image-loader` (partial), or `excel2img` (LibreOffice wrapper) offer varying fidelity levels. None covers the full set of cases (embedded charts, shapes, conditionally formatted cells) without an external dependency.

This remains an **open item** for strategy B. For strategy A (v1), visual rendering is not required at extraction time — it is useful for validation and testing.

### 4.2 Formula handling

Formulas represent one of the most structurally significant architectural choices in this RFC.

**Arguments for preserving formulas.**
A formula `=SOMME(B2:B10)` or `=SI(C3>0;"OK";"KO")` is an explicit business rule. Losing it may prevent a user from understanding why a cell has its value, or from finding the calculation logic they are looking for.

**Arguments for freezing to values.**

- Formulas referencing external sheets or named ranges become unreadable outside their original context (`='[Autre classeur.xlsx]Feuille1'!$A$1`).
- An LLM receiving raw formulas in a chunk may interpret them as structured text, with unpredictable consequences on retrieval.
- The verbosity of complex formulas (nested functions spanning several hundred characters) degrades the chunk's semantic density.
- `openpyxl` with `data_only=True` reads the **calculated values** saved at last save — formulas are never re-evaluated by the processor. The saved value may be stale if the workbook has not been recalculated.

**v1 decision:** freeze to values (`data_only=True`) and exclude formula strings from the chunk. If a formula is detected in a cell with no calculated value available (file never recalculated), the processor logs a warning and replaces it with a `[FORMULA_UNRESOLVED]` constant traced in the block metadata.

A configuration option `xlsx.preserve_formulas: true` may be added in v2 for users who wish to retain formulas in the document metadata (outside the RAG body).

### 4.3 Data heterogeneity

A single Excel sheet can contain:

- a clean data table;
- a title merged across 6 columns;
- a footnote in column A, row 50;
- empty cells acting as visual separators;
- a total row styled differently from the data.

This heterogeneity is the norm, not the exception. The pipeline must:

1. **Separate islands** before attempting any structural modelling (phase A3).
2. **Classify each island**: is it a table, a metadata block, or residue?
3. **Trace what is not extracted** in the enriched summary (A1) so the user knows what proportion of the document was covered.

A computed coverage rate (extracted cells / total non-empty cells) is produced by the pipeline and attached to the document metadata.

---

## 5. Chosen solution — Deterministic reconstruction pipeline

The pipeline is organised into three phases: **A (document level)**, **B (per table)**, **C (consolidation)**. Cross-cutting concerns (observability, LLM fallback) apply throughout.

### Phase A — Document level (once per file)

#### A1 — Inventory and enriched summary

Produce the workbook triage map: list of sheets, their estimated complexity (non-empty cell count, merged ranges, detected outline levels), and — as the final output of phase B — a summary listing the extracted tables and the non-extracted residue per sheet with a coverage rate.

This summary is the pipeline's primary monitoring artifact. It enables detection in production of pathological workbooks (coverage < 30% = edge case to investigate).

#### A2 — Read, freeze values, capture structure

Open the workbook with `openpyxl` and capture, in a single pass, all structural metadata that disappears as soon as the grid is converted to a DataFrame:

- merged ranges (`sheet.merged_cells`) and anchor value for each range;
- outline levels (`row_dimensions[r].outline_level`, `column_dimensions[c].outline_level`);
- cell indentation (`cell.alignment.indent`) that encodes hierarchy in labels;
- cell errors (`#REF!`, `#N/A`, etc.) to distinguish from missing values;
- row and column height/width (indicator of rows "visually empty" hidden by formatting).

This step is the **only window** to read this metadata. It feeds directly into B4 (merge propagation).

#### A3 — Table segmentation (island detection)

Identify each table in the sheet using **connected components** on the empty/non-empty grid. The algorithm treats the sheet as a boolean matrix and groups adjacent non-empty cells into rectangular islands.

Fully empty rows and columns act as natural boundaries — they must not be removed before this step. An island smaller than a configurable threshold (`xlsx.island_min_cells`, default: 4 cells) is placed directly into the metadata residue.

Retained islands feed the phase B loop.

---

### Phase B — Per table (loop over each island)

Each table from A3 is processed independently through steps B1 to B9.

#### B1 — Title extraction

Detect a full-width merged cell placed immediately above the island. If it contains free text (non-numeric, no data delimiters), extract it as the table name and remove the row from the data zone. Distinguishes the title from a multi-level header.

#### B2 — Orientation detection

Resolve before any header interpretation: is the table **normal** (headers on top, records in rows), **transposed** (headers in left column, records in columns — apply `df.T`), or **cross-tabulated** (two dimension axes → unpivot triggered in B8)?

Heuristic: text/numeric ratio on the first row vs first column; presence of dates or periods on a single axis (indicator of a pivot table).

#### B3 — Header band detection

Determine how many header rows and index columns precede the data. The header/data boundary is the pivot of all subsequent steps.

Primary heuristic: header rows are textual and sparse; the first dense, numeric row marks the start of data. A fully merged row (detected in B2 as cross-tabulated) suggests multiple header levels.

This segmentation conditions B4, B5, B6 — an error here propagates to all subsequent steps.

#### B4 — Targeted merge propagation

Fill cells that are empty because of a merge with the anchor value, targeting only ranges actually merged (captured in A2). A blind global `ffill` would confuse a merge with a genuine missing value.

- **Horizontal** forward-fill on parent headers (columns of a multi-level header).
- **Vertical** forward-fill on hierarchical labels (index column labels grouping multiple rows).

#### B5 — Multi-level index and header construction

Build the column `MultiIndex` (N header rows → tuples) and the row `MultiIndex` (M index columns). Transforms the raw grid into a structured DataFrame.

#### B6 — Level collapse

Fold the `MultiIndex` toward the target form:

- **Wide table:** composite names (`sales_2023_q1`);
- **Long table (unpivot planned in B8):** preserve levels as dimensions.

Deduplicate column names by suffixing duplicates (`_1`, `_2`). Reset the index to ordinary columns.

#### B7 — Cleaning and type coercion

The grid is rectangular, headers are clean: focus on dirty values.

- Thousands separators and currency symbols.
- Percentages (`87 %` → `0.87`).
- FR locale: decimal comma, `DD/MM/YYYY` format.
- Identifier protection: preserve leading zeros (product codes, NAF, SIREN).
- Dates: Excel serial numbers (1900 and 1904 systems), parsing of textual representations.
- Booleans: normalise `VRAI/FAUX`, `oui/non`, `O/N`, `1/0`.

#### B8 — Unpivot to long format (conditional)

Triggered if the orientation detected in B2 is **cross-tabulated**, or if the table carries multi-level headers where one level is a temporal dimension (periods in columns).

Header levels become dimension columns (`year`, `quarter`), values fold into a single column. The schema becomes stable: a new period adds rows, not columns.

#### B9 — Validation and metadata

- Validate against an inferred schema (types, value ranges, key cardinality).
- Attach provenance: file, sheet, cell range (`A1:G23`), title extracted in B1, orientation detected in B2.
- Whatever fails validation is rejected at the boundary — never mid-chunk in the RAG. A structured error report is produced and added to the A1 summary.

---

### Phase C — Consolidation

#### C1 — Stack and load

Concatenate validated tables by aligning schemas; log schema drift (columns renamed, reordered, added across workbooks in the same series). Load to staging then promote to typed destination tables. Aggregates (totals, subtotals) are recomputed here from source data, never taken from the file.

---

### 5.5 LLM fallback

If an island passes phase A3 but fails in B3 or B5 (heuristics insufficient to detect the structure), the pipeline optionally activates strategy B (§3.2) on that island only. The island is rendered as an image (LibreOffice headless if available) and sent to the vision model configured for the team. The result is annotated as `source: llm_fallback` in the metadata to distinguish deterministic extraction from assisted extraction.

This fallback is disabled by default (`xlsx.llm_fallback: false`) and can be enabled per team profile.

---

## 6. Observability

At each pipeline step, the processor logs:

- number of islands detected and rejection threshold applied;
- orientation selected and heuristic confidence;
- number of header rows and index columns detected;
- number of merged ranges propagated;
- coverage rate per sheet (extracted cells / non-empty cells);
- failed validations and reason;
- LLM fallback activation (if triggered).

These metrics feed the A1 summary and are exposed as document metadata fields in the existing Knowledge Flow pipeline.

---

## 7. Open items

| # | Item | Priority |
|---|------|----------|
| 7.1 | Faithful rendering library (strategy B) — evaluate LibreOffice headless vs Python alternatives | P1 for strategy B |
| 7.2 | `xlsx.island_min_cells` threshold — calibrate on a corpus of real files | P1 before prod |
| 7.3 | `xlsx.max_inline_cells` threshold — above which, switch to the map+drill-down path (XLSX-DOC §6 v2) | P2 |
| 7.4 | `.xls` support (xlrd) — legacy binary format, not supported by openpyxl | P2 |
| 7.5 | `xlsx.preserve_formulas` option — store formulas in metadata outside the RAG chunk | P3 |
| 7.6 | Formatting-as-data extraction (cell colours → `status` column) | P3 |
| 7.7 | Skills contract definition for strategy C — dedicated RFC required | Future |

---

## 8. Verification plan

- **Unit tests** on the parser against a fixture corpus covering: multi-level merges, transposed tables, cross-tabulated tables, multiple islands per sheet, total rows, FR locale (dates and decimals), sparse matrices (> 90% empty cells), heterogeneous multi-sheet workbooks.
- **End-to-end test:** real workbook → A1 summary produced → annotated DataFrames → `output.md` written → vectorised → queryable via RAG.
- **LLM fallback test:** pathological island → fallback activation → `source: llm_fallback` annotation present in metadata.
- `make code-quality && make test` in `apps/knowledge-flow-backend`.

---

## 9. Decision requested

Approve:

1. Adoption of **strategy A** (deterministic reconstruction) as the primary Excel extraction path, with phases A, B, C described in §5.
2. The **LLM fallback** (§5.5) as an optional fallback mechanism, disabled by default.
3. **Freezing formulas** to values (`data_only=True`), with a logged warning for cells with no available calculated value.
4. ID **INGEST-02** for this RFC.

On confirmation: register the entry in `id-legend.yaml`, add the backlog item in `BACKLOG.md §INGEST`, and open the GitHub execution issue per the project task lifecycle.

# RFC: Extensible Document Processor Architecture (EDP)

**Status:** draft
**Author:** Timothé Le Chatelier
**Date:** 2026-06-22
**ID:** INGEST-01 *(new domain — see §12)*
**Scope:** `apps/knowledge-flow-backend` — processor contract, shared blocks, plugin system, Temporal integration, test harness
**Links:**

- `docs/swift/rfc/KNOWLEDGE-FLOW-SIMILARITY-SEARCH-RFC.md` (consumer of processed documents)
- `docs/swift/rfc/KNOWLEDGE-WORKSPACE-REWORK-RFC.md` (FRONT-09 — UI surface)
- blog post: *"Ingestion Shouldn't Be a Choice"* (2026-06-10, Timothé Le Chatelier)

**Contract impact:** additive on the existing `BaseInputProcessor` hierarchy; deprecates mode selection (Fast/Standard/Rich) as a user-visible concept; extends `configuration.schema.json` with new `processors` and `blocks` sections.

---

## 1. Decision

Replace the profile-scoped input processor mapping (`fast` / `standard` / `rich`) with a unified, format-oriented **Processor** that owns the complete document lifecycle — metadata extraction, content extraction, vectorization, deletion — and expose this contract as a **Python plugin interface** allowing external teams to register custom processors via a configuration file, without modifying Fred's source code. Shared algorithmic capabilities (OCR, image description, Markdown normalization) are promoted to **named, swappable blocks** accessible to any processor. Dispatch is extended beyond file extension to support custom matching predicates.

---

## 2. Problem

### 2.1 User-facing friction

Fred currently asks users to choose between Fast, Standard, and Rich modes at upload time. This requires knowing in advance the document's content type, intended use, and acceptable cost — information most users do not have. This choice creates support load and produces suboptimal results when the wrong mode is selected.

### 2.2 Cross-format inconsistency

The three profiles exist independently per format. A PPTX processed in "standard" mode has no equivalent to what "standard" means for a PDF. There is no cross-cutting definition of what a profile means — it is an implementation accident.

### 2.3 No extensibility contract

The existing `class_path` + `suffix` mapping in the configuration YAML is already a proto-plugin system, but there is no documented contract on what a processor must implement, no way to use shared capabilities (OCR, VLM) without importing internal modules, and no standard test harness for third-party processors. External teams cannot safely add processors without forking the backend.

### 2.4 Implicit shared blocks

`PaddleOCRmodel` and `build_image_describer` exist but are imported directly by individual processors. There is no registry, no versioning, and no way to swap an OCR backend without modifying processor code.

---

## 3. What already exists (extend, do not duplicate)

| Component | Location | Notes |
|---|---|---|
| `BaseInputProcessor` | `core/processors/input/common/base_input_processor.py` | Abstract base with `process_metadata`, `check_file_validity`, `extract_file_metadata`, `extract_guardrail_text` |
| `BaseMarkdownProcessor` | same file | Adds `convert_file_to_markdown` — Markdown extraction contract |
| `BaseTabularProcessor` | same file | DuckDB tabular contract; CSV/Excel remain as structured data, not Markdown |
| YAML profile mapping | `config/configuration_prod.yaml § processing` | Already maps suffix → `class_path`; profiles carry Temporal timeout parameters |
| `PaddleOCRmodel` | `core/processors/input/common/ocr/paddle_ocr.py` | Existing OCR block |
| `build_image_describer` | `core/processors/input/common/image_describer.py` | Existing VLM image description block |
| `PdfMarkdownProcessor` | `core/processors/input/pdf_markdown_processor/pdf2_markdown_processor.py` | Reference implementation (draft) |
| Output processors | `core/processors/output/` | Vectorization, tabular Parquet, summarizer — already separate from input processing |
| Temporal worker | `main_worker.py` | Registers activities; current timeout/retry config lives in profiles |

This RFC extends these components — it does not replace them.

---

## 4. Processor lifecycle contract

A **Processor** is the unit of work for a document, across its entire lifetime in the Knowledge Flow. It is responsible for four lifecycle tasks:

```
┌─────────────────────────────────────────────────────┐
│                     Processor                        │
│                                                      │
│  1. extract_metadata(file)  → DocumentMetadata       │
│  2. extract_content(file)   → ContentResult          │
│  3. vectorize(content)      → VectorizationResult    │
│  4. delete(document_uid)    → void                   │
└─────────────────────────────────────────────────────┘
```

### 4.1 Task 1 — Metadata extraction

Already implemented in `BaseInputProcessor.process_metadata`. No contract change; this RFC formalises it as Task 1 of the lifecycle.

Output: `DocumentMetadata` (existing `fred_core` model).

### 4.2 Task 2 — Content extraction

The content extraction task replaces the current `convert_file_to_markdown` / DuckDB split. The output type depends on the processor:

- `ContentType.MARKDOWN` — for document formats (PDF, DOCX, PPTX, images, TXT, MD, JSONL)
- `ContentType.TABULAR` — for structured formats (CSV, XLSX); the row payload is stored in
  PostgreSQL/Parquet, not vectorized into content chunks. Since 2026-07 (`RUNTIME-10`,
  `RAG-DATASET-DISCOVERY-RFC.md`), `TabularProcessor` optionally emits one small synthetic
  "dataset pointer" chunk (title + column names/types, no row data) into the shared vector
  index behind `storage.tabular_store.pointer_chunks_enabled` (default off) — this makes the
  *existence* of the dataset discoverable by semantic search; the payload itself is still
  never vectorized.

```python
class ContentResult:
    content_type: ContentType        # MARKDOWN | TABULAR
    markdown_path: Path | None       # set when content_type == MARKDOWN
    table_relation_sql: str | None   # set when content_type == TABULAR
    extras: dict                     # processor-specific metadata
```

### 4.3 Task 3 — Vectorization

Processors delegate to the shared vectorization pipeline (already in `output/vectorization_processor/`). A processor can override the chunking strategy by returning a custom `ChunkingHint` in `ContentResult.extras`. Default behaviour is unchanged.

### 4.4 Task 4 — Deletion

When a document is deleted, the processor is responsible for:

- Removing all chunks from the vector store (by `document_uid`)
- Deleting the Markdown artifact and the PostgreSQL table entry

A default implementation is provided in `BaseProcessor`; processors can override if they own additional storage.

---

## 5. Plugin system

### 5.1 Registration via configuration

The existing `input_processors` YAML list is extended to become the **processor registry**. Each entry maps a **trigger** to a processor class path.

A trigger can combine multiple conditions — all must be satisfied simultaneously. The more precise a trigger (the more conditions it has), the higher its specificity and priority (see §5.3).

```yaml
# config/configuration.yaml
processing:
  processors:

    # Specific trigger: filename pattern + extension
    # Matches "rapport-nov-2024.docx", "rapport-nov-2023.docx", etc.
    # Blocks declared under "blocks:" override the registry defaults (§6.1).
    - trigger:
        filename_pattern: "rapport-nov-20*"
        suffix: ".docx"
      class_path: "my_company.fred_plugins.RapportProcessor"
      blocks:
        ocr: paddle_v4
        image_describer: mistral_small

    # Extension-only trigger (DOCX catch-all)
    - trigger:
        suffix: ".docx"
      class_path: "knowledge_flow_backend.core.processors.docx.DocxProcessor"

    # Custom trigger via Python predicate
    - trigger:
        custom: "my_company.fred_plugins.triggers.is_encrypted_archive"
      class_path: "my_company.fred_plugins.EncryptedArchiveProcessor"

    # Extension-only trigger (PDF catch-all)
    - trigger:
        suffix: ".pdf"
      class_path: "knowledge_flow_backend.core.processors.pdf.PdfProcessor"
```

### 5.2 Plugin discovery

A custom processor is any Python class that:

1. Inherits from `BaseProcessor` (the new unified base — see §4)
2. Is importable from the Python environment where the Temporal worker runs

No entry points, no packaging constraints beyond importability. The class is loaded dynamically at worker startup via `importlib.import_module`.

### 5.3 Trigger resolution by specificity

When a file arrives, the runtime evaluates triggers in the following order:

1. Collect all triggers whose **all** conditions match the file
2. Among matches, retain the one with the **greatest number of conditions** — a `suffix + filename_pattern` trigger beats a `suffix`-only trigger
3. On equal specificity, the first in configuration file order wins
4. If no trigger matches → behaviour controlled by `processing.no_match_policy` (see below)

**Available trigger conditions** (all optional, combinable):

| Key | Type | Example | Description |
| --- | --- | --- | --- |
| `suffix` | string | `".pdf"` | File extension (case-insensitive) |
| `filename_pattern` | glob | `"rapport-nov-20*"` | Glob pattern applied to the bare filename; `*` = any sequence |
| `custom` | class_path | `"my.module.predicate"` | Python callable `(file_path: Path) -> bool` |

Glob syntax is intentionally simple: `*` (any sequence), `?` (one character), no `**` recursion.

**No-match policy (`no_match_policy`)**:

```yaml
processing:
  no_match_policy: reject   # "reject" (default) | "fallback"
  no_match_fallback_processor: "knowledge_flow_backend.core.processors.generic.GenericTextProcessor"
```

| Value | Behaviour |
| --- | --- |
| `reject` *(default)* | Document is refused with an explicit error (`StructuralProcessingError`) — no unknown processor runs silently |
| `fallback` | Document is processed by the processor declared in `no_match_fallback_processor` |

Fallback is opt-in: it only activates if `no_match_policy: fallback` is explicitly declared.

---

## 6. Shared algorithmic blocks

Shared blocks are named, versioned, and swappable capabilities. A processor declares the blocks it needs; the runtime resolves the implementation from the block registry.

### 6.1 Block registry (configuration)

```yaml
processing:
  blocks:
    ocr:
      default: paddle_v4          # used if a processor does not specify an OCR block
      paddle_v4:
        class_path: "knowledge_flow_backend.blocks.ocr.paddle.PaddleOCRBlock"
        config:
          use_gpu: false
      tesseract:
        class_path: "knowledge_flow_backend.blocks.ocr.tesseract.TesseractBlock"

    image_describer:
      default: fred_vlm
      fred_vlm:
        class_path: "knowledge_flow_backend.blocks.vision.FredVlmBlock"
      mistral_small:
        class_path: "knowledge_flow_backend.blocks.vision.MistralSmallVlmBlock"

    markdown_normalizer:
      default: standard
      standard:
        class_path: "knowledge_flow_backend.blocks.normalize.DefaultMarkdownNormalizer"
```

### 6.2 Block interface

Each block type defines a minimal interface:

```python
class OcrBlock(ABC):
    def predict(self, image_paths: list[str]) -> list[dict]: ...

class ImageDescriberBlock(ABC):
    def describe(self, image_base64: str) -> str: ...

class MarkdownNormalizerBlock(ABC):
    def normalize(self, text: str) -> str: ...
```

Processors receive resolved block instances via constructor injection (passed by the processor loader at startup).

### 6.3 Resolution and validation at startup

At worker startup, before accepting the first Temporal task, the loader performs the following checks for each registered processor:

1. **Block resolution**: for each block type (ocr, image_describer, markdown_normalizer), the value declared in the processor entry is resolved in the registry. If no value is declared, the block type's `default` key is used.
2. **Class existence**: the resolved block's `class_path` is imported; if the import fails, the worker refuses to start with an explicit message.
3. **Processor existence**: the processor's `class_path` is imported the same way.
4. **Registry consistency**: the `default` value of each block type points to a variant declared within that same type.

If any of these checks fail, the worker logs the error and stops immediately — it never starts in a partially configured state. This strict startup validation avoids discovering a broken configuration during document processing in production.

```text
[INGEST][Loader] Resolving blocks for DocxProcessor
[INGEST][Loader]   ocr → paddle_v4 (default) ✓
[INGEST][Loader]   image_describer → fred_vlm (default) ✓
[INGEST][Loader]   markdown_normalizer → standard (default) ✓
[INGEST][Loader] Resolving blocks for RapportProcessor
[INGEST][Loader]   ocr → paddle_v4 (declared) ✓
[INGEST][Loader]   image_describer → mistral_small (declared) ✓
[INGEST][Loader] Worker ready — 4 processors registered
```

### 6.4 Standard blocks

| Block type | Default | Available variants |
| --- | --- | --- |
| `ocr` | `paddle_v4` | `paddle_v4`, `tesseract` |
| `image_describer` | `fred_vlm` | `fred_vlm`, `mistral_small` |
| `markdown_normalizer` | `standard` | `standard` |
| `table_extractor` | `duckdb` | `duckdb`, `none` |

Additional variants can be added by declaring a new `class_path` under the block name — no core code change required.

---

## 7. Mode elimination

### 7.1 Current state

The `fast` / `standard` / `rich` profiles control:

- Which `input_processors` class is used per suffix
- Temporal activity timeout and retry parameters
- Whether OCR and image description are active (`process_images`, `do_ocr`)

### 7.2 Target

- **Profile as a user concept**: eliminated. Users no longer see "fast", "standard", "rich".
- **Profile as internal config**: timeout/retry parameters migrate to a single `worker_policy` block, independent of processing behaviour.
- **OCR / image description**: controlled per processor via the `blocks:` declaration in the processor entry (§5.1), not by a global profile.
- **PDF specifically**: the new `PdfProcessor` decides internally whether to use OCR/VLM based on document content (cascade logic from the blog post), not a user-selected mode. The Fast/Standard/Rich logic remains in code during the transition period but is not exposed.

---

## 8. Temporal integration

### 8.1 Current state

Each ingestion step (input processing, vectorization, output) is a **Temporal activity** registered in `main_worker.py`. Custom processors would today require modifying `main_worker.py` to register new activities.

### 8.2 Target

The worker startup sequence becomes:

1. Load configuration
2. Resolve all processor entries (instantiate classes, inject blocks)
3. Register each processor's lifecycle methods as Temporal activities, using the processor class name as the activity type prefix
4. Custom processors loaded via `class_path` are registered automatically — no `main_worker.py` modification required

Custom processor activities run **in the same Temporal worker** as built-in processors.

### 8.3 Timeout and retry

The timeout and retry policy is **global** — it applies identically to all Temporal activities, regardless of document format or processor used.

```yaml
processing:
  worker_policy:
    activity_timeout: 30m
    retry_initial_interval: 5s
    retry_backoff_coefficient: 2.0
    retry_maximum_interval: 2m
    retry_max_attempts: 3
    resource_error_delay_multiplier: 3.0
```

Retry behaviour is driven by the **Python exception type** raised by the processor, not by per-processor configuration. See §10 for the full classification (`TransientProcessingError`, `StructuralProcessingError`, `ResourceProcessingError`).

---

## 9. Logging and traceability policy

### 9.1 Objectives

Each step of a processor's lifecycle must produce structured logs sufficient to diagnose a quality or performance problem in production, without having to re-run the processing. Two dimensions are covered: **execution time** and, where possible, **RAM consumption**.

### 9.2 Expected log format

All processor logs use the existing application format (`%(asctime)s | %(levelname)s | [pid=%(process)d %(threadName)s] | %(message)s`). Processors enrich each message with a structured prefix:

```text
[INGEST][<ProcessorClass>][<task>] <message> | file=<name> uid=<document_uid> duration_ms=<N> ram_mb=<N>
```

Examples:

```text
[INGEST][PdfProcessor][extract_content] Extraction complete | file=report.pdf uid=abc123 duration_ms=4200 ram_mb=312
[INGEST][PdfProcessor][vectorize] Vectorization complete | file=report.pdf uid=abc123 chunks=47 duration_ms=890
[INGEST][PdfProcessor][delete] Deletion complete | file=report.pdf uid=abc123 duration_ms=120
```

### 9.3 Execution time measurement

`BaseProcessor` provides a `@timed_task` decorator that automatically wraps each lifecycle method and logs the duration in milliseconds at the end of its execution. Custom processors benefit from this without additional code.

```python
@timed_task("extract_content")
def extract_content(self, file_path: Path) -> ContentResult:
    ...
```

### 9.4 RAM consumption measurement

Memory consumption is measured via `tracemalloc` (Python stdlib) or `psutil.Process().memory_info().rss` depending on availability. It is logged **at DEBUG level only** to avoid overhead in production. The activation threshold is configurable:

```yaml
processing:
  observability:
    log_memory_usage: false       # enable in DEBUG/bench only
    memory_warn_threshold_mb: 500 # log WARNING if a processor exceeds this threshold
```

If `log_memory_usage: false`, only threshold breaches trigger a WARNING log — measurement remains active but silent below the threshold.

### 9.5 Cross-task traceability

The `document_uid` is propagated through all logs of the 4 lifecycle tasks. It serves as a correlation key to reconstruct the complete history of a document in log tools (Loki, ELK, etc.) with a simple query: `document_uid=<uid>`.

---

## 10. Intelligent retry policy

### 10.1 Limitations of the current policy

The current retry policy is uniform per profile (exponential backoff, fixed maximum attempt count). It does not distinguish between:

- A **transient** error (network timeout, pod restarted) → deserves a retry
- A **structural** error (corrupted file, unsupported format) → retry cannot succeed
- A **resource** error (OOM, GPU unavailable) → deserves a retry but with a longer delay

### 10.2 Error classification

Processors classify their exceptions into three categories via dedicated exception types:

```python
class TransientProcessingError(Exception):
    """Recoverable error — standard retry allowed."""

class StructuralProcessingError(Exception):
    """Permanent error — no retry. Document moves to FAILED status."""

class ResourceProcessingError(Exception):
    """Insufficient resource — retry with extended delay."""
```

`BaseProcessor` catches any unclassified exception and treats it as `TransientProcessingError` by default, to avoid blocking the pipeline on an unexpected exception.

### 10.3 Retry strategy by category

| Category | Temporal behaviour |
|---|---|
| `TransientProcessingError` | Standard exponential backoff (configurable in `worker_policy`) |
| `StructuralProcessingError` | `non_retryable_error_types` — Temporal does not retry |
| `ResourceProcessingError` | Retry with extended delay (×`resource_error_delay_multiplier` on the initial interval) |

### 10.4 Retry observability

Each retry attempt logs:

```text
[INGEST][PdfProcessor][extract_content] Retry attempt 2/3 | file=report.pdf uid=abc123 error=TransientProcessingError reason="OCR timeout" next_delay_s=10
```

The total number of retries consumed is included in the end-of-task log (`retries=N`), making it possible to detect structurally struggling processors even when they eventually succeed.

---

## 11. Test harness

### 11.1 Objectives

- A processor author must be able to test the 4 lifecycle tasks in isolation
- No Temporal, no live database, no vector store required
- Coverage of shared blocks (mockable interfaces)

### 11.2 Base test class

```python
class BaseProcessorTest:
    """
    Inherit from this class to get fixtures for the 4 lifecycle tasks.
    Override processor_class and sample_file_path.
    """
    processor_class: type[BaseProcessor]
    sample_file_path: Path

    def get_processor(self, blocks: dict | None = None) -> BaseProcessor:
        """Instantiate with mock or real blocks."""

    def test_metadata(self): ...              # validates DocumentMetadata fields
    def test_content_extraction(self): ...    # validates ContentResult type and path
    def test_extractor_output(self): ...      # validates raw extractor output
    def test_vectorization(self): ...         # validates that produced chunks are coherent
    def test_deletion_cleans_up(self): ...    # validates that no artifact is left behind
```

`test_extractor_output` targets the extraction method directly (`extract_content` — Task 2 from §4.2) with a known fixture file:

```python
def test_extractor_output(self):
    processor = self.get_processor(blocks={"ocr": NullOcrBlock()})
    result = processor.extract_content(self.sample_file_path)
    assert result.markdown_path is not None
    content = result.markdown_path.read_text()
    assert len(content) > 0, "Extractor must not produce an empty document"
    # Format-specific assertion: override in each test subclass
    self.assert_extractor_output(content)

def assert_extractor_output(self, content: str) -> None:
    """
    Override to validate the Markdown content produced by the extractor.
    Example: check for the presence of an expected section in the fixture.
    """
```

This makes it possible to test the extractor in isolation, without going through the full Temporal lifecycle, and to detect an extraction regression (empty document, truncated content, broken encoding) independently of the vectorization or deletion steps.

### 11.3 Block mocking

Each block interface has a `NullBlock` variant and a `FixtureBlock` variant shipped with the test utilities:

- `NullOcrBlock` — returns empty results; useful for testing paths without images
- `FixtureImageDescriberBlock(response="test caption")` — returns a fixed string

This allows unit tests to cover processor decision logic (when to call OCR, when to call VLM) without network calls.

### 11.4 Integration test pattern

A standard pytest fixture `live_processor_stack` starts a minimal in-memory stack (DuckDB, a temporary vector store stub) so that end-to-end processor tests can run offline in CI.

---

## 12. New domain code

No existing domain in `id-legend.yaml` covers the ingestion pipeline. Proposed addition:

```yaml
INGEST: "Knowledge Flow ingestion pipeline — document processors, shared blocks, plugin system, vectorization pipeline"
```

This RFC uses **INGEST-01**. To be added to `id-legend.yaml` before implementation begins.

---

## 13. Alternatives considered

### 13.1 Python entry points for plugins

`importlib.metadata` entry points require packaging the plugin as an installable distribution. Too heavyweight for the typical use case (internal team adding a processor). The `class_path` approach only requires importability. Rejected for the initial version; can be added later as an optional discovery mechanism.

### 13.2 Separate microservice per custom processor

Maximum isolation but requires the external team to manage their own Temporal worker, network policy, and deployment. Not the default — the default (same worker) covers the majority of use cases.

### 13.3 Monolithic `BaseProcessor` replacing all existing bases

`BaseMarkdownProcessor` and `BaseTabularProcessor` carry significant domain logic (Markdown normalisation helpers, DuckDB preview rendering). Rather than merging them, the new `BaseProcessor` adds the lifecycle contract as a thin wrapper layer; the two existing bases remain valid subclasses.

---

## 14. Impact on existing contracts

| Contract | Change |
|---|---|
| `configuration.schema.json` | Add `processing.processors[]` and `processing.blocks{}` sections; `processing.profiles` deprecated but not removed |
| `BaseInputProcessor` API | No change to existing methods; the new `BaseProcessor` wraps and extends |
| Temporal activity names | New naming convention `{ProcessorClass}.{task}` — additive, no existing activity renamed |
| `main_worker.py` | Dynamic registration loop replaces the static list — internal change, no API impact |
| Knowledge Flow ingestion API | The `mode` field on upload is removed in the scope of this RFC |

---

## 15. Open questions (for developer confirmation)

1. ~~**Configuration file location**~~ — **Decided**: all configuration (processors and blocks) is centralised in `configuration.yaml`. No separate file.
2. **Block versioning**: is a named variant in the config file sufficient, or do we need semantic version constraints (`ocr: paddle>=4.0`)?

## Purpose

Provide usable PDF/PPTX ingestion with stable source-page attribution and explicit extraction choices, while keeping optional dependency families out of the default distribution.

## ADDED Requirements

### Requirement: Default distributions exclude the optional PyMuPDF family

Ordinary development installs, package installs and standard final API/worker images SHALL exclude `pymupdf`, `pymupdf4llm`, `pymupdf-layout` and dependencies needed exclusively by that family. Default PDF/PPTX processing SHALL remain functional. Shared dependencies SHALL remain available to their other consumers.

#### Scenario: Fresh default install
- **WHEN** a developer runs ordinary `uv sync` or `make dev`, or an operator installs the default package or standard image
- **THEN** the installed inventory excludes the optional family and its exclusive dependencies
- **AND** API and worker startup and default PDF/PPTX ingestion succeed with their configured infrastructure available

#### Scenario: Independent storage choice
- **WHEN** Chroma is enabled without PyMuPDF, or PyMuPDF is enabled without Chroma
- **THEN** only the selected option and its required dependencies are added
- **AND** neither option enables the other

### Requirement: Engine activation requires explicit installation and configuration

The system SHALL support a documented `pymupdf` extra and explicit image build option. Installing the extra SHALL NOT change the configured engine. API and worker startup SHALL reject selections requiring unavailable optional packages before readiness or accepting processing work, across all selectable profiles and configured processor paths. Unknown engine values SHALL be rejected without silently choosing PyMuPDF. Omitted advanced PDF engine configuration SHALL select Docling.

#### Scenario: Optional engine selected but not installed
- **WHEN** a selectable profile or configured processor requires PyMuPDF and its required packages are absent
- **THEN** API and worker startup fail with the affected configuration setting and an actionable extra/image installation instruction
- **AND** the error is not hidden by a document extraction fallback

#### Scenario: Extra installed with default configuration
- **WHEN** the extra is installed but processing configuration remains at its defaults
- **THEN** extraction continues to use the default engines

#### Scenario: Explicit opt-in
- **WHEN** the extra or opt-in image is installed and a supported PyMuPDF processor is explicitly selected
- **THEN** that processor performs extraction and reports its selected engine

#### Scenario: Unrelated dependency failure
- **WHEN** a selected processor fails to load because of a broken binary or unrelated import
- **THEN** the failure retains its real cause instead of being reported as a missing optional extra

### Requirement: Fast PDF extraction preserves page-aware results

Default fast extraction SHALL preserve document page count, original 1-based page numbers, inclusive page selection with existing range clamping, optional page headings, whitespace normalization and character-limit reporting. Per-page output SHALL follow the existing complete-page truncation contract. A page-aware request SHALL NOT silently return an unpaginated whole-document result. Fast extraction SHALL retain readable text and table values; structured table relationships and scanned-page OCR SHALL remain available in advanced profiles.

#### Scenario: Subset of a multipage document
- **WHEN** extraction requests pages 2 through 4 with per-page results
- **THEN** returned text belongs only to those pages with original source page numbers and the full document page count

#### Scenario: Character limit cuts a page
- **WHEN** the combined result reaches the requested character limit within a page
- **THEN** combined text is limited and marked truncated
- **AND** the per-page list retains only complete pages contained in that result

#### Scenario: Unicode and tables
- **WHEN** a supported text PDF contains Unicode or tabular values
- **THEN** designated Unicode text and table values survive normalization with correct source-page attribution
- **AND** structured table extraction is available through an advanced profile

#### Scenario: Scanned PDF
- **WHEN** a scanned PDF is processed using an OCR-capable advanced profile with its models provisioned
- **THEN** text is extracted without requiring the PyMuPDF family

### Requirement: PPTX slide rendering remains usable under concurrent ingestion

PPTX processing SHALL preserve selected-slide image rendering without PyMuPDF, including original slide numbers, image dimensions and opaque PNG output. Concurrent PDF/PPTX work SHALL NOT cause native rendering collisions, mix outputs between documents or leave rendering resources running after failure.

#### Scenario: Selected slides
- **WHEN** a deck requests valid and out-of-range slide numbers
- **THEN** valid slides produce correctly numbered images containing their visible text/graphics
- **AND** out-of-range slides are skipped with the existing diagnostic behavior

#### Scenario: Concurrent advanced PDF and PPTX processing
- **WHEN** multiple documents are extracted and rendered concurrently
- **THEN** each result belongs to its own document and selected pages
- **AND** failures and timeouts clean up rendering resources without crashing unrelated ingestion

### Requirement: Distribution evidence and upgrades describe actual artifacts

CI SHALL exercise default and opt-in profiles, guard against direct/transitive reintroduction, and retain separate installed inventories and license/SBOM evidence for actual final artifacts. Documentation SHALL distinguish optional lockfile entries from shipped components, preserve required notices, and state that operators must establish rights for every enabled component. It SHALL NOT infer blanket license clearance from installation choices. Supported configurations, generated schemas and migration instructions SHALL agree with engine defaults and optional activation.

#### Scenario: Optional packages retained in lockfile
- **WHEN** the lockfile includes reproducible optional dependencies but the standard image excludes them
- **THEN** artifact evidence identifies the actual installed versions and image digest separately from lockfile findings
- **AND** no ignore rules or removed metadata conceal installed components

#### Scenario: Upgrade an existing PyMuPDF deployment
- **WHEN** an operator upgrades a configuration selecting PyMuPDF
- **THEN** the migration guide provides both an explicit opt-in image/configuration path and a supported non-PyMuPDF path
- **AND** describes changed extraction/chunk behavior without automatically re-ingesting existing documents

### Requirement: Replacement quality and resource use are verified

Both profiles SHALL be compared on a reproducible representative corpus against developer-approved quality, latency and memory gates before the implementation is declared complete. Validation SHALL cover text, multipage references, tables, Unicode/malformed text, OCR-capable scans and PPTX images. Intentional formatting/chunk differences and unverified boundaries SHALL be recorded.

#### Scenario: Corpus comparison fails an agreed gate
- **WHEN** a candidate loses required content, exceeds a resource threshold or cannot complete a required validation
- **THEN** the failure remains visible and the implementation is not declared complete without correction or explicit agreement to revised acceptance

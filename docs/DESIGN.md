# 📐 DESIGN.md – Ingestion Pipeline Structures

This document describes the design of core data structures in the Fred ingestion pipeline, with a focus on **when** and **why** they are used.

---

## 🧭 Push vs Pull Documents

Fred supports two ingestion modes:

### ➕ Push Documents

- The user **uploads a document** (e.g., PDF) through the API or UI.
- A `document_uid` is assigned immediately.
- A `DocumentMetadata` is created and saved **immediately**.
- The document is stored and retrievable from the backend.

> Push files always have `document_uid` and a stored metadata record.

### 📥 Pull Documents

- Represent **external files** (e.g., on disk, Git, or WebDAV).
- Initially discovered as `PullFileEntry` objects via catalog scan.
- Only when the user explicitly triggers processing is a `FileToProcess` created.
- **No metadata is stored until processing begins**.
- During processing, a virtual `DocumentMetadata` is generated and then persisted.

> Pull files have no metadata until the user triggers ingestion.

---

## ⚙️ Ingestion Mechanisms

Fred supports two ingestion entry points:

### 1. 🧩 Temporal-based Pipeline (recommended)

- Activities:
  - `extract_metadata_activity`
  - `process_document_activity`
  - `vectorize_activity`
- Supports staged, recoverable, asynchronous workflows
- Can be triggered manually or programmatically (via pipeline definitions)

> Unified handling of push and pull through `FileToProcess`.

### 2. 🚀 Direct Controller-based Ingestion

- REST endpoint accepts uploads and optionally processes immediately
- Used for fast/manual ingestion
- Still relies on the same structures (`DocumentMetadata`, etc.)

> Ideal for small uploads or test tools; same design structures apply.

---

## 🧱 Core Structures

### 1. `PullFileEntry`

**What**: Discovered file in a pull source (e.g., `/mnt/docs/report.pdf`)

**When**: Returned during catalog scan

**Why**: Transient structure used to let the user select a file to ingest

```python
class PullFileEntry(BaseModel):
    path: str            # Relative path in pull source
    size: int            # File size in bytes
    modified_time: float # Unix timestamp (mtime)
    hash: str            # Path-based stable hash (used for UID)
```

---

### 2. `FileToProcess`

**What**: Describes a document to be ingested

**When**: Created when user triggers ingestion (UI or API)

**Why**: Primary input to both the ingestion controller and Temporal pipeline

```python
class FileToProcess(BaseModel):
    source_tag: str
    tags: List[str] = []

    # Push
    document_uid: Optional[str] = None

    # Pull
    external_path: Optional[str] = None
    size: Optional[int] = None
    modified_time: Optional[float] = None
    hash: Optional[str] = None

    def is_push(self) -> bool
    def is_pull(self) -> bool
    @classmethod
    def from_pull_entry(...)
    def to_virtual_metadata(...) → DocumentMetadata
```

> Ingestion logic only needs this class as input.

---

### 3. `DocumentMetadata`

**What**: The master record of a document’s metadata and ingestion state

**When**: 
- Created immediately for push files
- Created virtually during pull ingestion, and saved after processing begins

**Why**: Tracks document identity, source, status, and metadata for retrieval and UI display

```python
class DocumentMetadata(BaseModel):
    document_name: str
    document_uid: str
    date_added_to_kb: datetime
    retrievable: bool

    # Pull-specific fields
    source_tag: Optional[str]
    pull_location: Optional[str]
    source_type: SourceType  # Enum: PUSH or PULL

    tags: Optional[List[str]]
    title, author, created, modified, etc.

    processing_stages: Dict[ProcessingStage, Literal["not_started", "in_progress", "done", "failed"]]

    def mark_stage_done(...)
    def set_stage_status(...)
    def is_fully_processed(...) → bool
    def get_display_name(...) → str
```

> This object lives in the metadata store and is the main UI reference.

---

## 🧼 Summary

| Step            | Push File                            | Pull File                             |
|------------------|--------------------------------------|----------------------------------------|
| Discovery        | Uploaded by user                     | Scanned from external source           |
| Initial metadata | Created and saved immediately        | Not created yet                        |
| Ingestion input  | `FileToProcess(document_uid=...)`    | `FileToProcess(external_path=...)`     |
| Metadata usage   | Retrieved from store                 | Created via `to_virtual_metadata()`    |
| Storage          | File and metadata saved              | Virtual metadata created, then saved   |

This unified design supports both push and pull documents without duplication, and is compatible with both Temporal workflows and simpler ingestion flows.


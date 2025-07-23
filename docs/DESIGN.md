# Document Ingestion & Tagging Design (July 2025)

## Overview

This note summarizes the design choices around document ingestion (`push` / `pull`), logical grouping via tags, and future extensibility for permissions and visibility in the document library.

---

## 1. Ingestion Modes

Documents in the system originate from two ingestion modes:

| Mode   | Description                                          | Upload via UI | Typical Use Cases                 |
|--------|------------------------------------------------------|----------------|-----------------------------------|
| push   | File is uploaded directly by the user                | ✅ Yes         | Session attachments, project files |
| pull   | File is discovered from a configured external source | ❌ No          | GitHub, WebDAV, internal folders   |

Pull sources are configured in `configuration.yaml`:

```yaml
pull_sources:
  local-docs:
    type: local_path
    base_path: ~/Documents
    description: "Personal local documents available for pull-mode ingestion"
```

The frontend allows browsing documents per pull source (e.g., dropdown or tabs), while `push` documents are viewed in a general-purpose library.

---

## 2. Tags: Logical Grouping

Each document can be associated with one or more **tags**, used to:

- Group documents by project, topic, or workflow (e.g., `"project-acme"`, `"security"`)
- Filter documents in the UI
- (In future) control permissions or visibility

✅ Tags apply to both push and pull documents  
✅ Tags are **independent** of ingestion type  
✅ Tags will be reused for workspace-level grouping

---

## 3. Data Model

Each document is represented as:

**Frontend TypeScript (simplified):**

```ts
interface KnowledgeDocument {
  document_uid: string;
  ingestion_type: "push" | "pull";
  source_tag: string | null;
  tags: string[];
  processing_stages: Record<string, "not_started" | "in_progress" | "done" | "failed">;
}
```

**Backend Python (Pydantic):**

```python
class DocumentMetadata(BaseModel):
    document_uid: str
    ingestion_type: Literal["push", "pull"]
    source_tag: Optional[str]
    tags: List[str]
    processing_stages: Dict[ProcessingStage, StageStatus]
```

---

## 4. UI Behavior

- 🔁 **Source Selector**  
  - Displays either the general push document library or a selected pull source
  - Disables upload button when in pull mode

- 🏷️ **Tag Filter**  
  - Always available and applies across ingestion modes

- 📥 **Upload Button**  
  - Only visible/active in push mode (and for users with upload permissions)

- 📊 **Document Table**  
  - Includes chips for ingestion type, processing stages, retrievability
  - Rows are filterable by tags, stages, and retrievability

---

## 5. Extensibility Ideas

- Add per-tag permissions (e.g., "ops team can view `project-infra`")
- Enable document sync status for pull-mode (e.g., `last_checked`, `hash_mismatch`)
- Introduce virtual "workspace" tags (like OpenUI) for team-based navigation
- Add tool-assisted mass tagging or ingestion suggestions

---

## ✅ Summary Table

| Concept          | Scope        | Purpose                         |
|------------------|--------------|---------------------------------|
| `ingestion_type` | Technical    | How the document entered the system |
| `tags`           | Logical      | How the document is used/grouped    |
| `source_tag`     | Pull-only    | Where the file was discovered      |
| Upload           | `push` only  | Not available in pull mode         |
| Filters          | Universal    | Work across all ingestion types    |

---

*Prepared for design discussion – July 2025*

# Eliccir Agent – Migration Progress from Legacy CIR Code

This document tracks the progress of migrating the legacy CIR (Crédit Impôt Recherche) report generation logic into the new `Eliccir` agent, built with a `StateGraph` flow.

---

## ✅ Achieved in New Design

- **Structured Workflow**
  - Legacy ad-hoc sequence in `Backend.py` replaced by a modular LangGraph pipeline (`_graph` in `Eliccir`).
  - Nodes: `retrieve` → `assess` → `outline` → `draft` → `compose` → `materialize_template` → `finalize_success`.

- **Prompt Design**
  - CIR-specific tone and constraints preserved from `TemplatePrompt` (novelty, uncertainty, systematic approach, knowledge creation).
  - Cleaner system messages and structured prompt building.

- **Document Retrieval**
  - Replaces legacy `rag_completion()` + Chroma with direct `knowledge_flow_url/vector/search` calls.
  - Wraps results into `DocumentSource` objects for downstream use.

- **Structured Outputs**
  - Uses Pydantic models:
    - `CIRAssessmentOutput`
    - `CIROutlineOutput`
    - `CIRSectionDraft`
  - Eliminates brittle text parsing from old pipeline.

- **Templating**
  - Legacy DOCX generation (`FillTemplate.py`) replaced with MCP `templates.instantiate` call.
  - Configurable via `default_template_id` / `default_template_version`.

- **Source Handling**
  - Maps retrieved documents into `ChatSource` for front-end source display.

---

## ⚠️ Not Yet Ported from Legacy

- **Glossary Extraction**
  - Legacy: `generer_glossaire()` + `Glossaire.py` updated global glossary after generation.
  - New: No glossary step; potential addition after `_draft` or `_compose`.

- **Image Selection**
  - Legacy: `getRelevantImages()` suggested relevant diagrams per section.
  - New: No image analysis or selection step.

- **Two-Pass Drafting (Reprompt)**
  - Legacy: `reprompt_processing()` expanded “Travaux et résultats” with more detail.
  - New: Single `_draft` step; no second-pass elaboration.

- **Bibliography / HAL Integration**
  - Legacy: `GetPDFs.py` + `set_biblio()` fetched and cited HAL references.
  - New: Bibliography not integrated.

- **Session Persistence**
  - Legacy: Saved intermediate results to session JSON (`DataManipulation.py`) for resuming in UI.
  - New: Relies on Fred session manager; partial outputs may not persist unless explicitly saved.

---

## 📌 Migration Gap Map

| New Eliccir Node            | Legacy Equivalent Function(s)                                       | Status  |
|-----------------------------|---------------------------------------------------------------------|---------|
| `retrieve`                  | `rag_completion()` / `generate_all_prompts()` document retrieval    | ✅ Done |
| `assess`                    | Eligibility logic via manual prompt steps                          | ✅ Done |
| `outline`                   | Outline generation (manual in legacy)                              | ✅ Done |
| `draft`                     | First-pass section drafting                                         | ✅ Done (no reprompt) |
| `compose`                   | Assembling markdown                                                 | ✅ Done |
| `materialize_template`      | `remplir()` from `FillTemplate.py`                                  | ✅ Done (via MCP) |
| `finalize_success`          | UI display + saving final outputs                                   | ✅ Done |
| *Glossary Extraction*       | `generer_glossaire()` + `Glossaire.py`                              | ❌ Missing |
| *Image Selection*           | `getRelevantImages()`                                               | ❌ Missing |
| *Two-Pass Drafting*         | `reprompt_processing()`                                             | ❌ Missing |
| *Bibliography / HAL*        | `set_biblio()` + `GetPDFs.py`                                       | ❌ Missing |
| *Session Persistence*       | `save_session_json()` + `DataManipulation.py`                       | ⚠️ Partial |

---

## 🎯 Next Steps

1. **Glossary Node**  
   - After `_draft` or `_compose`, run glossary extraction using legacy `create_CIR_glossaire()` and `update_global_glossaire()`.

2. **Optional Image Selection Node**  
   - Integrate diagram relevance ranking (`getRelevantImages()`).

3. **Reprompt Pass**  
   - Add optional `_elaborate` node for “Travaux et résultats” using plan → elaboration approach.

4. **Bibliography Integration**  
   - Add HAL/other citation retrieval to support references in reports.

5. **Ensure Session Persistence**  
   - Save intermediate and final outputs in a recoverable session format.

---

**Legend:**  
✅ Implemented  
⚠️ Partial / needs review  
❌ Missing


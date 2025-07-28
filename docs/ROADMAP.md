# 🗺️ Fred Roadmap – RAG Pipeline and Platform Readiness

---

## PHASE 1: Cleanup & Dev Hygiene (Short-term blockers)

###  Sanitization & Configuration
- [ ] Clarify and normalize usage of `configuration.yaml` vs `.env`
  - Ensure sensitive values (e.g., `OLLAMA_BASE_URL`) are strictly in `.env`
  - Update and validate `.env.example`
  - Document clearly in backend/frontend README

### Codebase Cleanup
- [ ] Remove unused code (backend & frontend)
- [ ] Review and close outdated GitHub issues
- [ ] Rebuild and verify `.devcontainer`
- [ ] Improve documentation structure
  - Identify missing/inconsistent info
  - Try using [`continue.dev`](https://continue.dev/) for iterative improvement

### Deployment Readiness
- [ ] Clean up and document `fred-deployment-factory`
- [ ] Ensure Kubernetes manifests are template-based and tested
- [ ] Optional: add staging or demo environment setup

---

## PHASE 2: Product Strategy (Structural Reflection)

### Use Case Integration
- [ ] Define strategy for integrating ad-hoc features (BidGPT, RAGS, L2PF)
  - Backend: plugin/tool/workflow interface?
  - Frontend: new page(s)? configuration-driven visibility?
- [ ] Prototype the flow for **BidGPT** as an example

---

## PHASE 3: RAG Pipeline Improvement

### 1. File Conversion Pipeline
- [ ] ✅ `.docx` → `.md` support confirmed (OK for L2PF)
- [ ] 🔍 Consider using **PDF as a pivot format**:
  - Pro: consistent rendering
  - Con: PDF→Markdown can be slow
- [ ] Implement **dual preview tab** in UI:
  - Markdown
  - PDF
- [ ] Improve:
  - Table rendering (currently uses HTML in Markdown)
  - Intra-document links in Markdown

### 2. Chunking & Embeddings
- [ ] Refine Markdown chunking strategy
  - Repeat table headers per chunk?
  - Consider semantic chunking heuristics
- [ ] Reuse or generalize PDF chunking logic from Romain
- [ ] Handle images:
  - Replace with alt-text or captions (Kevin's strategy)
  - Investigate image embeddings (Julien's experiments)

### 3. Agent RAG Logic
- [ ] Build baseline RAG agent (LangChain or standalone notebook)
- [ ] Extend to **agentic RAG**:
  - Question clarification if vague
  - Answer validation
  - Show reasoning steps
- [ ] Render agent steps in UI (streamed LangGraph metadata)
- [ ] Ensure support for:
  - OpenAI
  - Mistral
  - LLaMA (local SLMs)
- [ ] Define "SLM mode" for portable deployment
  - e.g., run 7B–10B model with 16GB RAM + 8 vCPU

---

## PHASE 4: Library & Document Management

### Document Libraries
- [ ] Finalize support for `push` and `pull` sources
- [ ] Enable:
  - Filter vector search by library
  - Select individual/multiple documents
  - Select one or multiple libraries
- [ ] Optional:
  - Require library descriptions
  - Add “Generate description” and “Summarize documents” buttons

### Security & Sharing
- [ ] Integrate library access with Keycloak (if enabled)
- [ ] Consider private/public library access scopes

---

## PHASE 5: Observability & Monitoring

### LLM Metrics
- [ ] Add integration with **Langfuse** or custom event logger
- [ ] Track and expose:
  - Token counts
  - Prompt templates
  - Latency per step
  - Agent/tool usage

### Classic Monitoring
- [ ] Export Prometheus-compatible metrics
- [ ] Add health endpoints and latency tracing
- [ ] Optional: Build lightweight monitoring UI/dashboard

---

## Resources

- Julien Meynard’s RAG experiments (images, advanced pipelines)
- Romain’s PDF chunking pipeline
- Kevin Denis’ approach for table/image enhancement
- LangChain + LangGraph tutorials on agentic RAG
- [Continue.dev](https://continue.dev/) for coding/documentation iteration

---

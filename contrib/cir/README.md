# CIR HippoRAG Service (standalone)

Thin FastAPI wrapper around the CIR HippoRAG library processor. This lives outside Knowledge Flow to avoid dependency clashes (e.g., `openai` pins).

## Quick start

```bash
cd contrib/cir
uv sync             # installs fred-core + FastAPI (no HippoRAG by default)
# HippoRAG upstream pin is broken; to force-install anyway:
# make hipporag  # runs pip --no-deps hipporag==2.0.0a4 after base sync
uv run uvicorn cir.main:app --reload --port 8205
```

Call the API (default port 8205):

```bash
curl -X POST http://localhost:8205/library/process \
  -H "Content-Type: application/json" \
  -d @- <<'EOF'
{
  "library_tag": "demo",
  "documents": [
    { "file_path": "/abs/path/doc.md", "metadata": { "identity": { "document_name": "doc.md", "document_uid": "uid-1" }, "source": { "source_type": "push", "source_tag": "uploads" } } }
  ]
}
EOF
```

- If HippoRAG is installed (see `make hipporag`), the processor builds the graph; otherwise it only bundles the corpus.
- Returned metadata is echoed back with a `hipporag` extension describing the bundle location/status.

### Settings (env)
- `HIPPORAG_MAX_WORDS_PER_CHUNK` (default 220)
- `HIPPORAG_LLM_BASE_URL`, `HIPPORAG_LLM_MODEL`, `HIPPORAG_EMBEDDING_MODEL`, `HIPPORAG_RERANK_PROMPT_PATH`, etc. (see `processor.py`)

## Notes
- Depends on `fred-core` only; Knowledge Flow can call this service over HTTP or import `cir.processor.CirLibraryOutputProcessor` directly from this package if installed in a separate env.

# CIR HippoRAG Service (standalone)

Standalone FastAPI service that runs a library-level output processor using HippoRAG. It lives outside Knowledge Flow to keep heavy/fragile dependencies isolated while KF remains the system of record for storage and metadata.

## What it does
- Accepts markdown previews + metadata for a library.
- Builds a corpus bundle and, if HippoRAG is installed, builds graph artifacts (embeddings + graph).
- Returns updated metadata (with `extensions.hipporag`) plus a bundle payload (inline base64 or upload to a presigned URL).
- Stateless by design: no internal content store; Knowledge Flow is expected to persist the bundle.

## How it works with Knowledge Flow
- API contract is typed in `fred_core.processors` (`LibraryProcessorRequest/Response`).
- KF fetches previews from its store, calls `/library/process` with `preview_markdown` + metadata, receives updated metadata + bundle, and stores the bundle in KF’s content store.
- Security optional: toggle `HIPPORAG_SECURITY_ENABLED` (default true).

## Why HippoRAG here
- HippoRAG builds relation-aware graphs that can improve retrieval across a library.
- Kept in `contrib` to avoid dragging its heavy/fragile deps into the main backend.
- We use our fork (fixed OpenAI pin, GPU dependency reduced by default) to avoid upstream pin issues and make installs workable on dev laptops; GPU installs still supported if needed.

## Quick start
```bash
cd contrib/cir
make run            # creates venv, installs dev+hipporag extras, runs uvicorn on 8205
```

Call the API (default port 8205):
```bash
curl -X POST http://localhost:8205/library/process \
  -H "Content-Type: application/json" \
  -d @- <<'EOF'
{
  "library_tag": "demo",
  "return_bundle_inline": true,
  "documents": [
    {
      "preview_markdown": "# Demo\nThis is a test doc.",
      "metadata": {
        "identity": { "document_name": "demo.md", "document_uid": "uid-1" },
        "source": { "source_type": "push", "source_tag": "uploads" }
      }
    }
  ]
}
EOF
```

- If HippoRAG is installed (`make run` installs the extra), the zip includes graph files; otherwise only corpus files.
- Use `return_bundle_inline: false` + `bundle_upload_url` for presigned upload instead of base64 in the response.

## Settings (env)
- `HIPPORAG_SECURITY_ENABLED` (default true)
- `HIPPORAG_LLM_MODEL`, `HIPPORAG_LLM_BASE_URL`, `HIPPORAG_EMBEDDING_MODEL`, `HIPPORAG_RERANK_PROMPT_PATH` (optional; falls back to HippoRAG default when available), etc. See `cir/config.py`.

## Notes on the fork
- Upstream HippoRAG had broken pins and GPU-heavy deps. Our fork pins `openai` to a real version and drops vllm by default. GPU installs are still possible by adjusting the torch/vllm overrides if needed.

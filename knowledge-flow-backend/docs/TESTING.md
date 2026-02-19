# Testing Guide

This document centralizes the tests added/reorganized around Markdown/PDF ingestion.

## 1) Markdown Profile Test (fast/medium/rich)

- Script: `tests/scripts/test_markdown_profiles.sh`
- Make target: `make markdown-profile-test`
- Input: recursive folder containing `.pdf`, `.docx`, `.pptx`
- Output: markdown files under `target/markdown-profile-tests` (default)

Example:

```bash
make markdown-profile-test \
  INPUT_DIR=/path/to/files \
  PROFILES=medium \
  OUTPUT_DIR=./target/markdown-medium \
  BASE_URL=http://localhost:8111/knowledge-flow/v1
```

## 2) `summary.tsv` Format

`summary.tsv` now includes:

- `run_id`
- `profile`
- `status`
- `file`
- `document_uid`
- `chars`
- `upload_http`
- `markdown_http`
- `stage`
- `upload_ms`
- `markdown_ms`
- `total_ms`
- `error`

Recommended usage:

- sort by total processing time: `sort -t $'\t' -k12,12nr summary.tsv | head`
- filter errors: `awk -F '\t' '$3 == "error"' summary.tsv`
- isolate stage-level errors: `awk -F '\t' '$9 != "done"' summary.tsv`

## 3) Offline Policy for PDF medium/rich (Docker prod)

To make PDF ingestion in medium/rich robust without Internet access:

- unified runtime cache under `/app/.cache`
- cross-encoder preloaded at image build time
- required Docling artifacts preloaded: `layout` (medium/rich), `tableformer` (rich), `easyocr` (rich)
- HF offline mode enabled through `HF_OFFLINE_STRICT` (default `1`)
- runtime offline variables: `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`

Reference files:

- `dockerfiles/Dockerfile-prod`
- `config/configuration_prod.yaml`

## 4) Practical Notes

- A larger Docker image does not directly mean higher runtime RAM usage.
- A larger image mostly means more storage use and longer pull/build times.
- If tests pass with Wi-Fi disabled in medium/rich, that is a strong validation that required artifacts are preloaded.

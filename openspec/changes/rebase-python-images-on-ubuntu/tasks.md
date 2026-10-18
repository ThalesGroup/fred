## 1. Dockerfiles

- [x] 1.1 Rebase fred-agents on Ubuntu 24.04 with uv-managed CPython 3.12.15.
- [x] 1.2 Rebase control-plane-backend the same way.
- [x] 1.3 Rebase knowledge-flow-backend the same way, with `libmagic1t64`, and drop the unused global uv install from its builder.

## 2. Verification

- [x] 2.1 Build every affected final image with `--pull --no-cache`. Rescan before and after with the same Trivy version and DB, all severities, and record the counts.
- [ ] 2.2 fred-agents: imports, PPT-filler PDF conversion, start-up and a real agent turn.
- [ ] 2.3 control-plane: start-up and `alembic upgrade head`.
- [ ] 2.4 Knowledge Flow: API and worker start-up; ingest legacy Office, xlsx with recalculation, DOCX with EMF, audio/video, and a PDF through Docling.

## 3. Delivery

- [x] 3.1 Migration note (impact none) naming the base change for derived images.
- [ ] 3.2 PR linked to #3167, with the scan comparison.

## Verification evidence

Trivy 0.75.0, one DB snapshot (2026-10-18), os+library, all severities. Published v3.7.0 images compared with local `--pull --no-cache` builds of this branch:

| Image | v3.7.0 CRIT/HIGH/MED/LOW (total) | Ubuntu CRIT/HIGH/MED/LOW (total) | Size |
|---|---|---|---|
| fred-agents | 1 / 67 / 147 / 246 (462) | 0 / 0 / 37 / 36 (73) | 1.67 -> 1.77 GB |
| control-plane-backend | 0 / 44 / 59 / 61 (165) | 0 / 0 / 22 / 4 (26) | 1.08 -> 1.17 GB |
| knowledge-flow-backend | 1 / 247 / 427 / 408 (1109) | 0 / 0 / 1013 / 77 (1090) | 8.73 -> 8.84 GB |

- In Knowledge Flow, 934 of the 1,090 remaining rows come from ImageMagick, which Ubuntu's Inkscape depends on (340 rows), and from the ffmpeg libraries (594 rows). Both packages are already slated for removal in #3161. The remaining library finding in each image is the known MEDIUM rustls finding in Temporal.
- All images run as `fred-user` (1000:1000) on Ubuntu 24.04.5 with Python 3.12.15; pip is absent from the base interpreter and the venv.
- fred-agents: the imports pass and a python-pptx deck converts to PDF through `convert_office_file_to_pdf` (LibreOffice 24.2.7). The entrypoint runs until it reports the missing configuration file.
- control-plane: the application and alembic import, and `alembic.ini` is present.
- Knowledge Flow:
  - the application, Docling and OpenCV import, and libmagic identifies a PDF;
  - xlsx recalculation returns the right formula value;
  - a `.doc` converts to `.docx` through `convert_doc_to_docx`;
  - Inkscape 1.2.2 exports a PNG, ffmpeg 6.1.1 writes a WAV, and pandoc 3.1.3 renders HTML.
- Not run yet: real deployment, agent turn, control-plane migrations against a database, Knowledge Flow end-to-end ingestions (including DOCX with EMF and audio transcription), arm64 build.

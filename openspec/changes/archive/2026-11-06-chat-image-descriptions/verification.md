# Verification

## Automated evidence

- Knowledge Flow `test_fast_lite_image_processor.py` (17), `test_svg_summary.py` (20), `test_fast_ingest_registry.py` (2); fred-runtime `test_react_prompting.py` (65), `test_document_read_scope.py` (9); frontend `useChatAttachments` (8) and batch (3) tests. Each hardening limit below has a test that fails without it.
- ruff, `ruff --select I`, basedpyright on touched files, `tsc`, prettier: pass.

## Hardening measurements (2026-11-08)

| Input | Before | After |
| --- | --- | --- |
| SVG `.a{` x40k / `url(` x40k / `width="1…1x"` 20 KB | 8.39 s / 1.16 s / 12.29 s | under 0.01 s |
| 81 MP PNG (258 KB file) | +931 MB | refused before decoding |
| 45 MP RGB / 42 MP RGBA PNG | +516 / +548 MB | +241 / +388 MB |

## Live checks

- Owner, 2026-11-06, pixtral-12b-2409: histogram follow-ups answered from the description, omissions reported as unknown; a 160 KB SVG floor plan ingested in about 12 s, facts first, beds misread as desks.
- Real LibreOffice + PDFium: a 24 px icon renders at 1569 px, a `10000cm` canvas is scaled, not cropped, an SVG holding only an external image is discarded as blank.

## Considered, not applied

- JPEG q90 for the vision payload: lossy for charts and text, tokens unchanged.
- Binding `max_tokens` on `VisionImageDescriber`: the owner chose to drop the unused parameter.
- A dedicated executor for vision calls: uploads would queue behind it.

## Not proven

Deep and Graph agents (out of scope); images one description cannot answer (`chat-image-pixels-every-turn`).

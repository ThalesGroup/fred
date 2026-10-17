## 1. Acceptance and reference corpus

Developer approved the complete approach and implementation on 2026-10-17. The design acceptance gates apply unchanged.

- [x] 1.1 Obtain developer confirmation of proposal, design and numerical acceptance gates before implementation; record the agreed scope and any amendments here.
- [x] 1.2 Assemble the 12-document corpus described in design, with redistributable provenance, hashes and reviewed expected text/page/table/image facts; verify coverage of all six fixture categories.
- [x] 1.3 Capture baseline extraction, page anchors, chunk counts, latency and process-tree RSS at the recorded base commit, using isolated environments and the specified repetition protocol; retain reproducible commands and raw results as validation artifacts.

## 2. Functional default extraction

- [x] 2.1 Replace fitz in the first lightweight PDF processor with pypdf and preserve its existing public adapter; verify multipage selection, clamping, page headings, normalization, limits, metadata, Unicode and malformed-input behavior with real fixtures.
- [x] 2.2 Keep MarkItDown for whole-document extraction without allowing fallback to discard page-aware requests; verify both whole-document and requested-page error paths and table-value preservation.
- [x] 2.3 Replace PPTX rasterization with pypdfium2 in an isolated child process and declare the direct dependency; verify scale/dimensions, selected and invalid slides, resource cleanup, failure/timeout behavior and simultaneous Docling/PPTX processing.
- [x] 2.4 Make optional PDF imports lazy, default advanced extraction to Docling and remove implicit PyMuPDF fallback; verify ordinary imports with the extra absent, explicit optional extraction with it present and unknown-engine rejection.
- [x] 2.5 Extend shared API/worker startup validation for optional processor selections; verify every selectable profile and configured legacy processor, missing-extra diagnostics, unchanged engine selection after installation, and preservation of unrelated import/binary failures.

## 3. Packaging, images and configuration

- [x] 3.1 Move the family behind the `pymupdf` extra and regenerate `uv.lock`; verify locked dependency edges, clean ordinary sync/Make development inventories, wheel installation without source overrides, and all four Chroma/PyMuPDF option combinations.
- [x] 3.2 Add the independent `INSTALL_PYMUPDF=false` build option and documented opt-in image variant through existing Docker/workflow paths; build fresh standard and opt-in final artifacts and verify their inventories, including both API and worker entrypoints.
- [x] 3.3 Align bundled YAML and Helm fast processors with the non-PyMuPDF path and regenerate backend/chart schemas from source; verify schema regeneration is clean and representative default/opt-in configurations validate.

## 4. Regression and artifact evidence

- [x] 4.1 Update existing processor fixtures that eagerly import fitz and split required default/opt-in CI coverage without `--all-extras`; verify real extraction tests run in each profile and default collection does not require PyMuPDF.
- [x] 4.2 Add installed-inventory and dependency-reachability assertions to prevent direct/transitive reintroduction; verify an intentionally reintroduced family dependency is detected and shared dependencies are retained.
- [ ] 4.3 Run provisioned integration CI for Docling OCR, LibreOffice PPTX conversion/rendering, actual API/worker startup and ingestion in both profiles; retain outputs and identify unavailable external/model prerequisites explicitly.
- [ ] 4.4 Compare both profiles with the frozen baseline corpus against every agreed gate, including four-document concurrency and child memory; record per-document metrics and intentional chunk/citation differences, resolving failed gates before completion.
- [x] 4.5 Produce digest-bound license/SBOM and installed-file inventories for final standard and opt-in images; verify excluded packages/exclusive dependencies are absent from standard artifacts, required notices remain present, and no ignore rules or metadata removal hide findings.

## 5. Documentation, review and delivery

- [x] 5.1 Update README, licensing audit, processing guide and affected feature descriptions; verify claims against installed artifact evidence and document rights/notices for the entire opt-in family and replacement libraries without blanket clearance claims.
- [x] 5.2 Add the production migration note with default and opt-in upgrade/rollback paths, worker draining and re-ingestion implications; verify `make migration-check` and consistency with generated schemas and Helm values.
- [x] 5.3 Run root `make code-quality`, Knowledge Flow offline tests, raw type checking where required by a baseline, and relevant configuration/image checks; record commands, results and limitations in the PR/tasks.
- [x] 5.4 Apply the full branch audit against the actual PR target and obtain an independent read-only review, including extraction contracts and native concurrency/resource handling; record base/head, coverage, findings/dispositions and re-verification in the PR.
- [ ] 5.5 Reconcile artifacts with verified behavior, sync the delta spec and archive only after all implementation/validation work is complete; verify strict OpenSpec validation and clean scoped Git diff.
- [x] 5.6 Push reviewable commits on the user-selected branch and open a draft PR titled `fix(#3159): make PyMuPDF explicitly optional`; link the issue, migration note, validation evidence and remaining limitations without closing historical issues/PRs.

## Verification record (2026-10-17)

Implementation and CI/docs are committed in c21afadda6 and 45a802474 on the developer-selected branch. Draft PR: https://github.com/ThalesGroup/fred/pull/3162 (target swift; review merge base a8b4228eb8064b01d26fca48f72886b0544341a6).

- Root `make code-quality` passed across all modules. Default Knowledge Flow `make test`: 1549 passed, 2 optional modules skipped, 45 integration tests deselected. Optional focused tests: 60 passed, 1 integration test deselected. Truncation correction: 25 passed. Raw type check: 0 errors, 7 existing warnings.
- Four isolated wheel environments (standard, Chroma, PyMuPDF, both) passed inventory/import checks without editable source overrides. Image-selection tests: 14 passed; intentional dependency-reintroduction test: 1 passed. Migration and Helm schema checks passed.
- Full author review against the above merge base covered runtime callers, packages/CI, configuration/schemas, tests and operator docs. Independent runtime review corrected a truncation-marker/page-boundary defect; packaging review corrected six CI/docs/helper defects. All were rechecked. Follow-up review of 45a802474 plus benchmark process-group/PIL cleanup found no actionable findings. Historical PR #2083 resource/error-handling findings were replayed.
- The frozen synthetic corpus has 12 documents. Default fast per-page token recall is 100%. Against the old configured fast processor, the maximum per-fixture median time ratio is 1.22 and peak process-tree RSS ratio is 0.67; at four concurrent documents, 1.22 and 0.67. Against the old lightweight attachment path, maximum ratios are 1.79 and 0.94. PPTX rendering maxima are 1.49 and 0.91 (four-way: 0.69 and 0.91). These are local measurements on a shared machine, including background build/quality contention, not dedicated-host performance guarantees.
- Chunk boundaries intentionally change: the 100-page document has 99 -> 100 chunks, table 2 -> 1, columns 4 -> 2; source page attribution remains intact. Raw outputs and citation examples are retained with local validation evidence.

Remaining acceptance is explicit: the image smoke exercises the real API factory, a scheduler-disabled worker, real Docling models and LibreOffice/PDFium, but no full network service lifespan or persisted ingestion. The PyMuPDF Markdown table representation fails the literal whitespace-token metric even on the baseline; designated table values are retained, but that is not a pass of the separate 98% gate. Do not archive or call every acceptance gate complete until these boundaries are resolved. Remote CI runs on the draft PR.

Final standard image: sha256:2cfa333b3775bc6f951891623585b50fef3ec19d3829a1adedbb2e9e295f8e67. Final optional image: sha256:4e1c25e9e4e49775175b337e3430c71d8003411fa6113c3724185b3cfde1704f. Trivy 0.75.0 license reports bind to these image IDs; CycloneDX and installed-file inventories are retained separately. Only the three optional family packages differ; no shared package was removed. The standard image's installed inventory and SBOM exclude the family. Examination of its 25 saved layers found only Fred's two optional adapter source files bearing the name, no family distribution/native library/cache. pypdf's license, PDFium's bundled notices (31 license paths) and docling-slim's license are present. MarkItDown's upstream wheel supplies MIT metadata but no separate license file; no metadata or notices were stripped.

Both final-image processor runs passed on all 12 documents. A further run with the baseline Knowledge Flow source mounted into the same provisioned optional image passed; Docling OCR/table outputs are identical across baseline and both final profiles. All six slide images pass dimensions/text/graphics checks. This compares processor behavior with real models, not external persistence.

Optional profile benchmark complete: all eight born-digital extraction results are byte-identical to baseline, sequentially and at four concurrent documents. Maximum sequential time/RSS ratios: 1.99/1.02; four-way: 0.77/1.01. No measured fixture exceeds the 2x time or 1.5x RSS ceilings. The literal optional-table text gate remains open; it is not silently replaced with baseline equivalence.

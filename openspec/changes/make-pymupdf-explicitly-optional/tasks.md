## 1. Acceptance and reference corpus

Developer approved the complete approach and implementation on 2026-10-17. The design acceptance gates apply unchanged.

- [x] 1.1 Obtain developer confirmation of proposal, design and numerical acceptance gates before implementation; record the agreed scope and any amendments here.
- [ ] 1.2 Assemble the 12-document corpus described in design, with redistributable provenance, hashes and reviewed expected text/page/table/image facts; verify coverage of all six fixture categories.
- [ ] 1.3 Capture baseline extraction, page anchors, chunk counts, latency and process-tree RSS at the recorded base commit, using isolated environments and the specified repetition protocol; retain reproducible commands and raw results as validation artifacts.

## 2. Functional default extraction

- [ ] 2.1 Replace fitz in the first lightweight PDF processor with pypdf and preserve its existing public adapter; verify multipage selection, clamping, page headings, normalization, limits, metadata, Unicode and malformed-input behavior with real fixtures.
- [ ] 2.2 Keep MarkItDown for whole-document extraction without allowing fallback to discard page-aware requests; verify both whole-document and requested-page error paths and table-value preservation.
- [ ] 2.3 Replace PPTX rasterization with pypdfium2 in an isolated child process and declare the direct dependency; verify scale/dimensions, selected and invalid slides, resource cleanup, failure/timeout behavior and simultaneous Docling/PPTX processing.
- [ ] 2.4 Make optional PDF imports lazy, default advanced extraction to Docling and remove implicit PyMuPDF fallback; verify ordinary imports with the extra absent, explicit optional extraction with it present and unknown-engine rejection.
- [ ] 2.5 Extend shared API/worker startup validation for optional processor selections; verify every selectable profile and configured legacy processor, missing-extra diagnostics, unchanged engine selection after installation, and preservation of unrelated import/binary failures.

## 3. Packaging, images and configuration

- [ ] 3.1 Move the family behind the `pymupdf` extra and regenerate `uv.lock`; verify locked dependency edges, clean ordinary sync/Make development inventories, wheel installation without source overrides, and all four Chroma/PyMuPDF option combinations.
- [ ] 3.2 Add the independent `INSTALL_PYMUPDF=false` build option and documented opt-in image variant through existing Docker/workflow paths; build fresh standard and opt-in final artifacts and verify their inventories, including both API and worker entrypoints.
- [ ] 3.3 Align bundled YAML and Helm fast processors with the non-PyMuPDF path and regenerate backend/chart schemas from source; verify schema regeneration is clean and representative default/opt-in configurations validate.

## 4. Regression and artifact evidence

- [ ] 4.1 Update existing processor fixtures that eagerly import fitz and split required default/opt-in CI coverage without `--all-extras`; verify real extraction tests run in each profile and default collection does not require PyMuPDF.
- [ ] 4.2 Add installed-inventory and dependency-reachability assertions to prevent direct/transitive reintroduction; verify an intentionally reintroduced family dependency is detected and shared dependencies are retained.
- [ ] 4.3 Run provisioned integration CI for Docling OCR, LibreOffice PPTX conversion/rendering, actual API/worker startup and ingestion in both profiles; retain outputs and identify unavailable external/model prerequisites explicitly.
- [ ] 4.4 Compare both profiles with the frozen baseline corpus against every agreed gate, including four-document concurrency and child memory; record per-document metrics and intentional chunk/citation differences, resolving failed gates before completion.
- [ ] 4.5 Produce digest-bound license/SBOM and installed-file inventories for final standard and opt-in images; verify excluded packages/exclusive dependencies are absent from standard artifacts, required notices remain present, and no ignore rules or metadata removal hide findings.

## 5. Documentation, review and delivery

- [ ] 5.1 Update README, licensing audit, processing guide and affected feature descriptions; verify claims against installed artifact evidence and document rights/notices for the entire opt-in family and replacement libraries without blanket clearance claims.
- [ ] 5.2 Add the production migration note with default and opt-in upgrade/rollback paths, worker draining and re-ingestion implications; verify `make migration-check` and consistency with generated schemas and Helm values.
- [ ] 5.3 Run root `make code-quality`, Knowledge Flow offline tests, raw type checking where required by a baseline, and relevant configuration/image checks; record commands, results and limitations in the PR/tasks.
- [ ] 5.4 Apply the full branch audit against the actual PR target and obtain an independent read-only review, including extraction contracts and native concurrency/resource handling; record base/head, coverage, findings/dispositions and re-verification in the PR.
- [ ] 5.5 Reconcile artifacts with verified behavior, sync the delta spec and archive only after all implementation/validation work is complete; verify strict OpenSpec validation and clean scoped Git diff.
- [ ] 5.6 Push reviewable commits on the user-selected branch and open a draft PR titled `fix(#3159): make PyMuPDF explicitly optional`; link the issue, migration note, validation evidence and remaining limitations without closing historical issues/PRs.

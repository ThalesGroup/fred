## 1. Production dependency environment

- [x] 1.1 Add a standalone locked production sync target to the shared Make recipe and verify it excludes the default dev group without changing `make dev`.
- [x] 1.2 Switch the three Python production Dockerfiles to the new target and verify their build commands use it.

## 2. OS package remediation

- [x] 2.1 Refresh final-stage OS packages in the three images and verify the apt commands are valid.
- [x] 2.2 Align both Knowledge Flow stages to Python 3.12.13 slim and verify their tags match.

## 3. Integration and delivery

- [x] 3.1 Add a migration note and verify deployment and rollback instructions are present.
- [x] 3.2 Run repository quality checks and verify the production dependency set and container builds. The targeted checks and all PR workflows passed; local root quality stopped on the existing uv bootstrap issue.
- [x] 3.3 Run the PR Trivy scanner, compare critical findings against the baseline JSON reports, and record residual risks in the draft PR.

## 4. Full-component follow-up

- [x] 4.1 Scan published control-plane and Knowledge Flow v3.6.1, attribute library findings, and reuse the recorded frontend/agents baseline.
- [x] 4.2 Refresh remaining Python bases, remove installed pip, and preserve Knowledge Flow document converters with headless Office packages.
- [x] 4.3 Remove Knowledge Flow's unused langchain meta-package, update patched Docling/MCP dependencies, and verify embedding imports and processors.
- [x] 4.4 Raise the shared Temporal security floor, relock all consumers, and validate SDK workflows, payloads and client/worker compatibility.
- [x] 4.5 Rebuild affected final images without cache, rescan all severities, and document every remaining critical/high library finding.
- [x] 4.6 Run affected offline suites, root quality checks, document conversion smoke checks and independent branch review; update migration guidance and tracking issues, then commit/push without a PR.
- [x] 4.7 Increment the patch version of every modified library, propagate corrected internal floors and lockfiles, and validate the package artifacts without publishing.

## Follow-up verification

- Published v3.6.1 / final image findings: frontend 161/0, agents 633/468,
  control-plane 181/165, Knowledge Flow 1185/1120. Four critical findings remain
  (libxml2 in two images and two ChromaDB findings), with no fixed version listed.
  Every remaining critical/high library finding is assessed in #3155; no ignore
  rules or metadata suppression. One medium embedded rustls finding remains in
  each Python image. Frontend npm retains its separate low KaTeX finding.
- Six Python offline suites: 7,663 passed; five user-search failures reproduced
  against prior source and Temporal 1.28.0. Root code-quality passed; raw
  basedpyright reports zero errors in six projects.
- Isolated real Temporal server: SDK success/failure workflows, production
  control-plane client/lifecycle workflow, Pydantic conversion and history replay.
- Final non-root images: imports, entrypoints, migration heads and PPT preview
  pass. Knowledge Flow legacy Office conversion, formula recalculation and actual
  Docling PDF/OCR/layout/table extraction pass offline, with extracted text and
  Markdown identical to the published baseline.
- All 13 Python packages built and validated without publication. Twelve modified
  libraries received patch increments; independent final-version wheel consumer
  resolves and all 16 Python lockfiles pass `uv lock --check`.
- Independent full branch review and metadata delta review: migration note and
  published core MCP constraint gap corrected; no remaining actionable finding.
  Review baseline: abc4e00a3afd21be83d87debda3d15be0ea4a202; implementation commits
  d360ac156 and c55205e41. User-local deployment/config files excluded.
- Scoped migration validation passed. Evidence: /tmp/fred-all-vuln-20261016/report.md.
  Tracking: #3149, #3150, #3152 and #3155. No PR, release, deployment, customer DB
  migration, live LLM turn, arm64 build or separate satellite image validation.

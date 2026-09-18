## 1. Offline-Safe CSV Encoding Selection

- [x] 1.1 Restrict DuckDB encoding normalization to UTF-8, UTF-16, and Latin-1 aliases, and verify focused normalization tests reject extension-backed Windows-1252 output.
- [x] 1.2 Transcode a detected non-native source before the first DuckDB validation while preserving delimiter and `source_path`, and verify the focused Windows-1252 inspection test observes only a UTF-8 validation call.
- [x] 1.3 Preserve the direct native-encoding path and its terminal UTF-8 fallback, and verify the existing valid, ragged, invalid-path, and double-failure processor tests pass.

## 2. Regression Coverage and Documentation

- [x] 2.1 Add a Windows-1252 semicolon-delimited fixture with accented text and verify the inspected options and rendered/read content remain correct without any DuckDB extension-backed encoding request.
- [x] 2.2 Update `docs/swift/platform/PROCESSING_GUIDE.md` with the offline CSV encoding boundary and verify the guide names the native encodings and pre-read UTF-8 transcode behavior.

## 3. Verification

- [x] 3.1 Run the focused CSV processor test module and verify all tests pass offline.
- [x] 3.2 Run `make code-quality` and `make test` from `apps/knowledge-flow-backend` and verify both complete successfully.
- [x] 3.3 Review the hot ingestion-path diff against `docs/CONVENTIONS.md` performance and concurrency rules, then perform an independent cold-diff review and record any findings or confirm none remain.
- [x] 3.4 Run `openspec validate fix-offline-cp1252-csv-ingestion --strict` and verify all change artifacts pass validation.

## Verification Evidence

- Focused CSV processor tests: 10 passed.
- Knowledge Flow `make code-quality`: all checks passed; Basedpyright reported 0 errors, 0 warnings, and 0 notes.
- Knowledge Flow `make test`: 1192 passed, 27 deselected.
- Performance review: no new blocking network call, KPI path, client, or shared state; the change removes DuckDB's extension-download attempt. The existing synchronous full-file transcode in fast extraction remains a documented non-goal.
- Independent cold-diff review: no actionable findings. The reviewer confirmed the existing full-file memory use and adjacent `.utf8` copy as the only residual out-of-scope risk.

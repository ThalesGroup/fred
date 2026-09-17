## 1. Offline-Safe CSV Encoding Selection

- [ ] 1.1 Restrict DuckDB encoding normalization to UTF-8, UTF-16, and Latin-1 aliases, and verify focused normalization tests reject extension-backed Windows-1252 output.
- [ ] 1.2 Transcode a detected non-native source before the first DuckDB validation while preserving delimiter and `source_path`, and verify the focused Windows-1252 inspection test observes only a UTF-8 validation call.
- [ ] 1.3 Preserve the direct native-encoding path and its terminal UTF-8 fallback, and verify the existing valid, ragged, invalid-path, and double-failure processor tests pass.

## 2. Regression Coverage and Documentation

- [ ] 2.1 Add a Windows-1252 semicolon-delimited fixture with accented text and verify the inspected options and rendered/read content remain correct without any DuckDB extension-backed encoding request.
- [ ] 2.2 Update `docs/swift/platform/PROCESSING_GUIDE.md` with the offline CSV encoding boundary and verify the guide names the native encodings and pre-read UTF-8 transcode behavior.

## 3. Verification

- [ ] 3.1 Run the focused CSV processor test module and verify all tests pass offline.
- [ ] 3.2 Run `make code-quality` and `make test` from `apps/knowledge-flow-backend` and verify both complete successfully.
- [ ] 3.3 Review the hot ingestion-path diff against `docs/CONVENTIONS.md` performance and concurrency rules, then perform an independent cold-diff review and record any findings or confirm none remain.
- [ ] 3.4 Run `openspec validate fix-offline-cp1252-csv-ingestion --strict` and verify all change artifacts pass validation.

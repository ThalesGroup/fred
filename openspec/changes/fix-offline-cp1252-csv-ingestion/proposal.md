## Why

Knowledge Flow currently asks DuckDB to read Windows-1252 CSV files directly, which makes DuckDB attempt to download its large `encodings` extension at runtime. Offline pods wait roughly two minutes for that download to fail, blocking the single API process before the existing UTF-8 fallback can run.

## What Changes

- Transcode CSV sources whose detected encoding is not one of DuckDB's native `utf-8`, `utf-16`, or `latin-1` encodings before the first DuckDB read.
- Remove the `cp1252` and `windows-1252` DuckDB aliases that currently opt into the extension-backed encoding path.
- Preserve the existing delimiter detection and UTF-8 fallback behavior for malformed or otherwise unreadable CSV files.
- Add an offline regression test proving a Windows-1252, semicolon-delimited CSV is parsed without ever asking DuckDB to use a non-native encoding.
- Document the native-encoding/transcoding boundary in the current Knowledge Flow processing guide.

## Capabilities

### New Capabilities

- `csv-ingestion`: Defines deterministic, offline-safe handling of CSV source encodings shared by attachment and corpus ingestion.

### Modified Capabilities

None.

## Impact

- Affected code: `CsvTabularProcessor` and its focused processor tests in `apps/knowledge-flow-backend`.
- Affected flows: chat attachment `/fast/ingest` and corpus CSV ingestion, which share the same processor.
- Documentation: Knowledge Flow's processing guide gains the CSV encoding rule.
- APIs and stored data formats are unchanged; unsupported source encodings continue to become temporary UTF-8 files before Parquet conversion.
- No DuckDB extension is added to the production image, avoiding the approximately 336 MB `encodings` dependency and runtime network access.

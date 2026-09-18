## Context

See `proposal.md` for the production failure. Both fast attachment ingestion and corpus ingestion reach `CsvTabularProcessor.inspect_read_options`, which detects the source encoding, detects the delimiter with Python, validates a DuckDB read, and returns a `CsvReadOptions` reused by preview and CSV-to-Parquet conversion.

DuckDB reads UTF-8, UTF-16, and Latin-1 without an extension. The current normalization table instead maps `cp1252` and `windows-1252` to `CP1252`, causing DuckDB to auto-install its `encodings` extension before the existing exception-driven UTF-8 fallback runs. The fix must therefore choose the fallback before any DuckDB operation.

## Goals / Non-Goals

**Goals:**

- Keep all encoding decisions in the shared CSV processor so attachment and corpus ingestion cannot drift.
- Ensure a detected extension-backed encoding is never included in DuckDB SQL.
- Preserve the existing direct path and fallback semantics for native encodings.
- Prove the decision at the DuckDB boundary, rather than relying on timing or a live network failure.

**Non-Goals:**

- Changing the synchronous `/fast/ingest` extraction architecture.
- Changing frontend handling of non-JSON proxy errors.
- Installing DuckDB's `encodings` extension in the production image.
- Changing connection policy for tabular query execution or disabling extension auto-install globally.
- Expanding the configured source-encoding candidates.

## Decisions

### Decide native support before validating with DuckDB

After Python detects the source encoding and delimiter, normalization will identify only UTF-8, UTF-16, and Latin-1 aliases as native. Any other detected encoding will be transcoded immediately and only the UTF-8 copy will be validated with DuckDB. The returned options will keep the detected delimiter, set `encoding="utf-8"`, and select the copy through `source_path`.

This reuses the existing transcoder and `CsvReadOptions.source_path` contract. It is preferred over catching DuckDB's unsupported-encoding error because the error is produced only after an auto-install network attempt, and over adding a new dependency because the standard library already handles Windows-1252.

### Remove extension-backed aliases from normalization

The `cp1252` and `windows-1252` entries will be removed from the DuckDB alias table. Native aliases remain centralized there. The pre-validation native-support check, not DuckDB's error message, becomes the gate deciding whether to transcode.

This is preferred over retaining the `CP1252` mapping behind a second conditional because an extension-backed DuckDB spelling is not a valid output of the offline-safe normalization contract and could be reused incorrectly later.

### Test the boundary deterministically

The focused processor test will write a semicolon-delimited Windows-1252 file containing a character that is invalid UTF-8, call the real inspection path, and observe validation calls. It will assert that DuckDB sees only the transcoded path with `utf-8`, then verify the result can be read and retains its columns and accented text. No test will intentionally issue a `CP1252` DuckDB query, because that would recreate the network-sensitive behavior the test is meant to prevent.

This is preferred over measuring elapsed time or relying on an unavailable extension server; both are environment-dependent and could turn an offline unit test into a two-minute hang.

### Keep global DuckDB hardening separate

The change will not set `autoinstall_known_extensions=false` across unrelated DuckDB connections. Preventing the unsupported encoding from reaching DuckDB fully removes this issue's runtime download path, while a global setting could affect explicit `httpfs` loading and tabular query behavior that require a broader audit.

## Risks / Trade-offs

- [The UTF-8 copy reads the complete source into memory, as the existing fallback already does] → Preserve the current helper in this focused fix; a streaming transcoder would be a separate performance change with its own tests.
- [Alias classification could regress when new source encodings are added] → Keep a small explicit native set and assert the DuckDB validation arguments for Windows-1252.
- [A native-encoding CSV can still fail for structural reasons] → Retain the existing exception-driven UTF-8 retry and terminal error logging.

## Migration Plan

Deploy as a normal Knowledge Flow code update; no data migration or configuration change is required. Rollback restores the prior behavior but also restores the offline runtime download attempt for Windows-1252 inputs.

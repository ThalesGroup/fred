## Purpose

Defines how Knowledge Flow ingests CSV files with deterministic source-encoding handling that remains functional in offline and air-gapped deployments.

## ADDED Requirements

### Requirement: CSV ingestion is offline-safe for legacy encodings
Knowledge Flow SHALL process a CSV whose detected source encoding is not natively supported by its tabular reader without downloading or loading an encoding extension at runtime.

#### Scenario: Windows-1252 attachment ingestion without network access
- **WHEN** a user attaches a semicolon-delimited Windows-1252 CSV while the Knowledge Flow runtime has no network access and no optional encoding extension installed
- **THEN** Knowledge Flow transcodes the source to UTF-8 before the first tabular-reader operation and successfully ingests the CSV

#### Scenario: Windows-1252 corpus ingestion without network access
- **WHEN** a Windows-1252 CSV enters the corpus ingestion pipeline while the Knowledge Flow runtime has no network access and no optional encoding extension installed
- **THEN** Knowledge Flow transcodes the source to UTF-8 before the first tabular-reader operation and successfully produces the same tabular dataset contract as a UTF-8 CSV

### Requirement: Native CSV encodings retain the direct read path
Knowledge Flow SHALL continue to pass CSV sources using a natively supported UTF-8, UTF-16, or Latin-1 encoding directly to the tabular reader, while preserving the existing UTF-8 fallback when that direct read fails.

#### Scenario: UTF-8 CSV ingestion
- **WHEN** a valid UTF-8 CSV is ingested
- **THEN** Knowledge Flow reads the original source directly without creating a transcoded copy

#### Scenario: Native read validation fails
- **WHEN** a CSV uses a natively supported encoding but the tabular reader rejects the source
- **THEN** Knowledge Flow transcodes the source to UTF-8, retries once using the transcoded copy, and propagates the error if that retry also fails

### Requirement: CSV delimiter and content are preserved by transcoding
Knowledge Flow MUST preserve the detected delimiter and decoded text content when it converts a legacy-encoded CSV to UTF-8.

#### Scenario: Semicolon-delimited accented content
- **WHEN** a Windows-1252 CSV contains semicolon-separated fields and accented characters
- **THEN** the resulting tabular data retains the semicolon-separated columns and the original decoded characters

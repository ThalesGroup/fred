## ADDED Requirements

### Requirement: Transfers survive a graceful stop
On a termination signal, the manager API SHALL stop accepting connections and let
in-flight requests, including uploads and downloads, finish within the configured
transfer deadline before exiting. The deployment SHALL allow at least that deadline.

#### Scenario: Rolling update during an upload
- **WHEN** the API receives SIGTERM while an upload is streaming
- **THEN** the upload completes with its normal receipt, new connections are refused, and the process exits afterwards

### Requirement: Storage failures are diagnosable without leaking data
An object-store failure SHALL keep the client response `503 storage_unavailable` and
SHALL log one server-side event naming the storage operation and error kind, without
object keys of other spaces, file names, credentials or provider response bodies.

#### Scenario: Provider refuses a read
- **WHEN** the provider rejects an original download
- **THEN** the client receives the neutral 503 and the log shows the failed operation and error kind

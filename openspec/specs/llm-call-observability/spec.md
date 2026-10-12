# LLM Call Observability Specification

## Purpose

Make ReAct and native Deep model-call failures diagnosable from safe operational telemetry, including streaming progress and concurrent child attribution.

## Requirements

### Requirement: Correlated model-call lifecycle

Each model invocation through the shared ReAct/Deep observability boundary SHALL emit a start and exactly one terminal diagnostic with an opaque call identifier, model, root/child role and outcome. Concurrent calls MUST retain isolated measurements. A support-reference diagnostic SHALL retain bounded links to the failed call identifiers when errors propagate through child delegation, exception causes or groups. Unknown ancestry SHALL remain unknown. Abrupt process termination is excluded from the terminal-delivery guarantee.

#### Scenario: Concurrent children with one broken stream
- **WHEN** two native Deep children stream concurrently and one fails
- **THEN** their call identifiers, counts and timings remain distinct and the resulting support-reference record identifies the failing call without attributing its failure to the successful sibling

#### Scenario: Cancellation
- **WHEN** a caller cancels an active model invocation
- **THEN** its terminal outcome is cancelled, active-call accounting is released exactly once, and cancellation propagates without retry or replacement by a telemetry failure

### Requirement: Streaming progress has explicit semantics

Diagnostics SHALL record observed chunk count, first-observed-chunk latency, maximum inter-chunk gap and time since last observed chunk at termination when these measurements exist. They SHALL distinguish before-first-chunk failures, failures after progress, non-streaming calls and unknown stages. SDK-provided chunk counts and timeout values SHALL be retained separately when available. Missing measurements and token usage MUST NOT be represented as zero. Chunk observations MUST NOT be described as token counts or proof of network silence.

#### Scenario: Stall after progress
- **WHEN** a stream produces chunks and then exceeds its configured chunk deadline
- **THEN** telemetry reports a streaming idle timeout, the observed progress and terminal silence, and the SDK timeout/count attributes when supplied

#### Scenario: No first chunk
- **WHEN** a stream exceeds its chunk deadline before producing a chunk
- **THEN** telemetry identifies a before-first-chunk timeout without inventing first-chunk latency or token usage

#### Scenario: Non-text progress
- **WHEN** observed chunks contain only tool-call deltas, reasoning or empty content
- **THEN** those observations advance the progress counters without retaining their content

### Requirement: Error categories and effective settings are safe

Failure telemetry SHALL distinguish streaming idle timeouts, transport phase timeouts, remote protocol errors, connection errors, rate limits, provider HTTP failures, cancellation and unknown failures. Effective streaming, timeout, retry and connection-limit settings and installed relevant library versions SHALL be available without exposing configuration dictionaries or secrets. Available upstream request identifiers SHALL be captured only from an explicit bounded allow-list and only where diagnostic policy permits them.

#### Scenario: Truncated HTTP response
- **WHEN** the upstream HTTP response closes before its body is complete
- **THEN** the model invocation reports a remote protocol error with its available progress and response metadata, without claiming which upstream component caused the closure

#### Scenario: Nested timeout cancellation
- **WHEN** a chunk deadline cancels an internal read and raises an outer streaming timeout
- **THEN** the outcome is a streaming timeout rather than a user cancellation

#### Scenario: Effective versus requested configuration
- **WHEN** requested transport settings differ from the already-active shared transport or a model setting overrides a default
- **THEN** diagnostics distinguish the effective settings from the requested values and do not claim ignored tuning took effect

### Requirement: Operational metrics support long-call diagnosis

The runtime dashboard SHALL expose terminal call rates by outcome/category/model/role, first-chunk and gap timing distributions, terminal silence, active-call counts and existing process/event-loop health. Existing call-latency consumers SHALL remain compatible. Labels SHALL use a fixed bounded schema from first emission; per-call and upstream identifiers MUST NOT enter Prometheus. New timing histograms SHALL include finite buckets above 120 seconds. Coverage exclusions SHALL be documented.

#### Scenario: Successful call precedes first error
- **WHEN** a process observes successes before its first stream failure
- **THEN** the failure category and role are still available in the exported metric labels and dashboard queries

### Requirement: Telemetry preserves execution and privacy

Instrumentation SHALL preserve existing timeout, retry, tool execution and streaming policies and SHALL work without content capture or a tracing backend. It MUST NOT log prompts, chunks, tool arguments/results, credentials, raw URLs, unbounded exception text or complete headers. It SHALL obey delegation restrictions. Per-chunk work SHALL use bounded in-memory state without per-chunk I/O or retained content. Telemetry failures SHALL NOT replace the model result or exception.

#### Scenario: Diagnostic sink fails
- **WHEN** a telemetry sink fails during a successful or failed model invocation
- **THEN** the original result or exception is preserved and call-local state is released

#### Scenario: Sensitive payloads and delegation
- **WHEN** injected request/response/error metadata contains secret and content sentinels, with either delegation mode
- **THEN** none appears in diagnostics, traces with capture disabled or operational metrics, and only policy-permitted bounded metadata is emitted

### Requirement: Shared runtime work preserves concurrent streaming progress

Cloud conversation-file listings and supported synchronous authored tools SHALL perform their blocking work outside the event loop used by concurrent model calls. Results, caller context and asynchronous tool execution SHALL remain compatible. Cancellation SHALL NOT automatically replay an already-started synchronous tool. Runtime diagnostics MUST NOT equate absence of observed chunks with proof of upstream silence. Tool-argument fragment optimizations SHALL preserve raw fragments, invalid-call metadata and completed arguments.

#### Scenario: Cloud listing during another model call
- **WHEN** a conversation lists many files and inferred directories while another model call is active
- **THEN** network and listing conversion work do not monopolize its event-loop thread, and the sorted listing preserves existing entries and metadata

#### Scenario: Synchronous authored tool
- **WHEN** a supported synchronous tool waits for blocking work
- **THEN** unrelated asynchronous work can progress and the tool observes the caller context, with its result or exception delivered once

#### Scenario: Asynchronous authored tool
- **WHEN** an asynchronous tool or callable needs the owner event loop
- **THEN** it continues executing on that loop with unchanged return and error behavior

#### Scenario: Tool arguments span streaming chunks
- **WHEN** an object argument arrives as multiple fragments, including a fragment that is not independently an object
- **THEN** the completed tool call has unchanged arguments and metadata, and malformed calls retain the same invalid-call classification

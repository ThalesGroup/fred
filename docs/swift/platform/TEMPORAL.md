# Temporal: scope and orchestration rules

For the implemented Knowledge Flow pipeline, read the
[ingestion architecture](../design/INGESTION.md). For agent execution, read the
[Runtime Execution Contract](../design/RUNTIME-EXECUTION-CONTRACT.md).
This page is a general decision guide, not a requirement to run agents under Temporal.

## Choosing the boundary

A single activity is appropriate when an operation already owns its internal
orchestration, retrying the whole operation is acceptable and its side effects
are safe to repeat. A dynamic agent execution need not become one Temporal
activity per model or tool call.

Multiple activities are appropriate when stable business stages need independent
retries, persisted intermediate results, durable waits or stage-level operational
visibility. Knowledge Flow uses metadata, extraction and output processing as
such stages; profile isolation applies only to extraction.

The [Capability Execution Flow RFC](../rfc/CAPABILITY-EXECUTION-FLOW-RFC.md)
explores durable orchestration inside capabilities. It is an open proposal,
not a description of the ingestion deployment or a shipped agent execution contract.

## Execution rules

- Workflows orchestrate deterministically. No direct database, file, network,
  model or CPU-heavy processing calls; use Temporal's workflow-safe primitives.
- Activities perform I/O and computation. Configure execution timeouts and retry
  policies for the operation; design side effects for retries and partial failure.
- Long-running activities heartbeat to report liveness and receive cancellation.
  A heartbeat does not prove useful progress, stop a computation or exclude
  overlapping attempts after a partition.
- Cancellation must reach the actual work. A cancelled coroutine does not stop
  its thread or subprocess automatically.
- Pass large inputs and outputs by shared-storage reference, not as workflow
  payloads. Temporary files are local to their worker.
- Waiting workflows do not reserve activity execution slots. Queue wait and
  activity runtime are separate operational signals.
- Human approval, where required, is a durable workflow wait rather than an
  activity holding resources while waiting for a person.

Progress and task persistence are application contracts, not implied by Temporal.
See the [Control Plane Product Contract](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md)
and the [Task Event Stream RFC](../rfc/TASK-EVENT-STREAM-RFC.md) for their respective
implemented boundaries and remaining proposals. Do not infer new event schemas,
mandatory workflow queries or HITL behavior from this decision guide.

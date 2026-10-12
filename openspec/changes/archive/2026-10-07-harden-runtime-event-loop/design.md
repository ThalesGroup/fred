## Context

See proposal.md. The developer authorized fixes following the read-only audit. A local socket probe established that loop starvation can expire LangChain's watchdog while bytes are ready; it did not reproduce a production cause.

## Goals / Non-Goals

Keep sibling requests schedulable while preserving filesystem results and tool contracts. No new executor, retry, timeout, logging transport, parser copy, or streaming-loop implementation. No claim of zero blocking in arbitrary extension code.

## Decisions

- MinIO/GCS already use `asyncio.to_thread`: include listing conversion/sort in that existing call. Directory sets are already deduplicated, so delete the repeated scans of the result list. Preserve directory markers, file/directory name collisions, metadata, prefix isolation and sort order.
- The SDK already depends on langchain-core: reuse its `is_async_callable` and `run_in_executor`, which copy context and translate StopIteration safely. Keep coroutine handlers on their owner loop; continue awaiting awaitables returned by synchronous factories. No automatic replay. Cancellation cannot forcibly terminate a running synchronous function, as with other executor-backed tools.
- Independently reviewed a guard on `langchain_core.messages.ai.parse_partial_json`, installed idempotently by the existing model factory. AIMessageChunk accepts only object arguments; right-trimming/closing cannot turn other prefixes into objects, so skip those attempts and preserve raw fragments/invalid metadata. Keep the public JSON utility unchanged and delegate object-prefixed fragments to upstream. Full metadata, merge and real HTTP streaming tests guard the private dependency reference. Fred's model integration owns this shim; reassess at the next langchain-core upgrade and remove when upstream resolves the cost. This does not bound malformed object-prefixed parsing or arbitrary large valid JSON. No parser copy or provider subclass.
- Console volume on the model path is four INFO records per successful invocation, not per chunk. The developer questioned the benefit of a logging overhaul; without measured backpressure, defer it and preserve the audit channel/guarantees.

## Risks / Trade-offs

Worker capacity is finite; offloading protects the event loop but does not guarantee throughput. Synchronous tools must use async handlers when they need the event loop. Synthetic performance observations are not production-load evidence. Dependency integration must be reviewed independently and guarded by end-to-end stream tests.

## Migration Plan

Local scoped commits only. Run offline tests, raw type checks, root quality and independent review. Update existing guidance and migration note. No new push until the developer agrees confidence is sufficient.

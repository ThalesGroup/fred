## Context

See proposal.md. The POC provides the shared detector and ReAct wrapper; Deep uses a separate middleware builder.

## Goals / Non-Goals

Recover model calls while preserving the existing frame and transport policies. No child graph claim, storage, new timeout setting, profile bump, concurrency control or retry UI.

## Decisions

Place retry after capability wrappers and before tracing: preparation runs once and each attempt produces telemetry. Retry the model node, not the whole agent graph, to avoid replaying tools. Keep existing model factory transport timeouts; scheduling budget does not terminate in-flight calls.

Reject an unaffordable provider hint rather than shortening its minimum delay. Ignore nonfinite hints; support HTTP dates. Prefer explicit status to broad message matching to avoid retrying unrelated failures.

## Risks / Trade-offs

- Configured provider SDK retries happen inside a runtime attempt; existing settings remain unchanged.
- Retry budget bounds scheduling; the final in-flight call can finish after it, subject to existing transport timeouts.
- Provider 429 is assumed to reject before streaming starts. Midstream application errors are not a replay guarantee.
- Native child middleware is integrated in the later extraction layer; issue #2535 remains open.

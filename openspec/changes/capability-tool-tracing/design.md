## Context

See proposal.md. The binder traces resolved tools; capability middleware bypasses it. The shared observability middleware already classifies returned failures for KPI and audit.

## Goals / Non-Goals

Preserve upstream typed-error handling and existing metrics. Do not implement native-child composition, custom subagents, retries, or filesystem storage.

## Decisions

Use the extracted shared asynchronous span context manager for binder and middleware, with a metadata marker to avoid duplicate spans. Making every tool source implement tracing separately would repeat lifecycle logic and miss middleware tools. Keep the active parent in the existing ContextVar so concurrent calls remain isolated. Mark returned failures at the existing classification site rather than duplicate classification.

## Risks / Trade-offs

Opt-in captured payloads can be large; reuse existing backend capture/truncation policy and add no unconditional serialization. No shared mutable cache or new I/O is introduced. Native-child middleware coverage is verified by the later integration layer, not claimed by this layer.

## Migration Plan

No schema migration. Revert the extraction commit to roll back.

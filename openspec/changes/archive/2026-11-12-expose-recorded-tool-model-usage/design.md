## Context

See proposal.md. ReAct already receives provider usage on completed model responses; tool rows currently omit it to prevent confusing full model prompts with tool-only cost (#2403).

## Goals / Non-Goals

Expose recorded API counters consistently in live and stored tabular details. Do not claim an isolated tool payload token count, change billing aggregation, estimate absent counters, or add trace queries to the UI path.

## Decisions

- Add optional `model_call_usage` to tool-call events and history metadata using one shared typed model, with nullable input/output, model response identifier, model name and batch tool count. Keep it distinct from billable `token_usage`. Preserve actual raw-provider zero and missing counters separately. Adapter-normalized zeros without raw presence stay unavailable; raw payloads take precedence, without changing billing normalization.
- Extract only reported nonnegative integer counters from existing provider metadata, once per completed model message. Attach the same scope to parallel tool calls, without summing it again. Existing final billing calculation is unchanged.
- Render compact API-model badges beside status/latency for the first model exchange AFTER the selected tool result, including the complete prompt. Forward the last per-call API usage on the final event/history row, separately from billed turn totals; intermediate tool-call metadata already records the other model responses. Resolve the next response by exchange and rank, never reuse the requesting call or a later turn. Display scope visibly for keyboard/touch users. Missing counters show unavailable. The developer clarified this association using session cb4c397a-2d64-474c-9fde-4f37661ee197 and chose API measurements only, without a tokenizer. Use existing shared JSON history for multi-pod replay; no new table or in-memory correctness state.
- Use one localized preview notice, retaining the bounded Prism preview and copy behavior. Scope full-copy wording to supported tools.
- For the developer's local session only, recover counters from existing configured trace observations whose model output contains the exact stored tool-call ID and name. Back up affected metadata and update conditionally in a transaction. Do not infer values from timings or neighboring model calls.

## Risks / Trade-offs

- Model usage covers the whole context and generated decision, not SQL execution: explicit API-model labeling and help prevent misattribution.
- Multiple tool calls share a model response: retain batch size and explain sharing; never add counters per tool into billing.
- Old records can lack usage: retain unavailable rather than guessed zero. Deploy SDK/runtime before the regenerated frontend; older readers ignore optional metadata.
- Work per model response is a fixed number of metadata fields; no new I/O, tokenization or payload scan. Existing persistence owns durability across replicas.

## Migration Plan

Normal additive deployment, no schema migration. Rollback may ignore the optional field. The local session recovery is an explicitly scoped diagnostic repair, not a production-wide backfill.

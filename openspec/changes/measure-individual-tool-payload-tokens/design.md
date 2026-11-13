## Context

See proposal.md for the requested behavior. `ToolCallRuntimeEvent.arguments` and tool-result content already travel through runtime/SSE/history; `model_call_usage` instead describes a complete model response. The current drawer correctly stopped displaying those global counters, but lacks individual payload counts.

A direct synthetic test against the configured Mistral provider resolved `mistral-small-latest` to `mistral-small-2603`. API prompt/completion counts were 100/20 then 105/2. The official Small 4 tokenizer (v15) counted the raw parameter JSON as 15 tokens and complete tool content as 46. Full prompt counts matched 100 and 105 after respecting the provider's omission of tool definitions for `tool_choice=none`. A separate 200-row/20-column result counted 66609 tokens; its five-row preview counted 1529. These local diagnostics establish the measurement boundary, not completed runtime integration.

Primary references: [Mistral Chat API](https://docs.mistral.ai/api/endpoint/chat), [official tokenizer API](https://mistralai.github.io/mistral-common/code_reference/mistral_common/tokens/tokenizers/mistral/) and [Small 4 model/tokenizer repository](https://huggingface.co/mistralai/Mistral-Small-4-119B-2603). The inspected historical model trace retains parsed arguments rather than the original parameter JSON; it does not establish an exact historical sent-payload count.

## Goals / Non-Goals

Goals: two auditable, independent text/JSON payload counts for every supported tabular call in David v3's managed runtime; consistent live/reloaded values; preserve the original drawer and all-column preview.

Non-goals: allocating shared prompts, generated reasoning, tool schemas or protocol framing to tools; changing provider billing, model selection or existing result limits; guessing unavailable historical counters; production backfill; claiming exact multimodal or arbitrary-provider support.

## Decisions

1. **Measure actual payloads at execution boundaries.** Capture the fully assembled original parameter JSON from the model response, matched by call ID, before runtime-injected credentials/scope. Count the complete text returned to the model after runtime rendering, including the actual model-visible error text. Never count SQL display formatting, five-row previews, UI metadata or an artificially reconstructed argument string. Missing original representation makes that direction unavailable. This avoids the rejected character ratio, model-total and neighboring-request-difference alternatives.

2. **Use a verified model/tokenizer binding.** Extend existing model-profile resolution rather than add a tool-specific model registry. Initially support Mistral Small 4 / 2603 with the official `mistral-common` tokenizer and a pinned tokenizer asset revision/checksum. Resolve aliases through existing model discovery/startup validation, record the resolved model and tokenizer identity, and never silently switch the execution model. Unknown mappings or a model mismatch disable the measurement rather than select a generic OpenAI encoding. Adding other models requires separately verified bindings.

3. **Keep per-call data separate from model usage.** Add an optional typed `tool_token_usage` payload to existing call/result runtime events and shared history metadata: independently optional `sent_tokens` and `received_tokens`, model/tokenizer identity, and `source=model_tokenizer`. The call event can supply sent tokens before the result arrives; the result supplies received tokens. Correlate by session/exchange/call ID, not timing or rank neighbors. Persist counts in existing JSON history, without new tables or raw-content duplication. Keep existing `model_call_usage` and conversation billing unchanged.

4. **Bound measurement overhead.** Load verified tokenizer assets during configured model startup, not on every tool call. Use bounded off-loop encoding and existing tool-result size bounds; compute each direction once and store only small metadata. No per-call download, provider request or trace-store lookup. Replicas share configuration and durable history, not process-local attribution state. Unavailable measurement must not fail tool execution. Validate worker saturation, cancellation and cross-instance history reload.

5. **Restore only the requested UI.** Read the selected call's own counts and show `Tokens envoyés` / `Tokens reçus` beside status/duration. Tooltips identify parameters versus complete returned content and tokenizer provenance. Running, missing or unsupported directions show a localized unavailable state, never invented zero. Keep the rejected scope paragraph absent and preserve SQL, colored JSON, five rows with every column, and complete copying. Unknown-tool redaction remains intact.

## Risks / Trade-offs

- Exact content tokenization is a different metric from API billing. Preserve explicit provenance and clear tooltips; never label the computed count as API-reported usage.
- Alias/tokenizer drift can invalidate counts. Verify the resolved model against pinned assets and fail unavailable on mismatch; persist identity for later audit.
- Old history may lack raw argument JSON or a verified model identity. Leave missing directions unavailable; do not retokenize with today's guessed model or re-run tools.
- Large content can block asynchronous execution. Require bounded off-loop work and focused concurrency/latency evidence before readiness.

## Migration Plan

Deploy the additive SDK/runtime/history contract with verified tokenizer assets, regenerate the frontend client, then deploy the drawer. Existing JSON rows remain readable. No database migration, permissions change, ingestion or production backfill. Roll back components normally; older readers ignore optional metadata. Planning is complete only after developer confirmation; implementation and its tests remain pending.

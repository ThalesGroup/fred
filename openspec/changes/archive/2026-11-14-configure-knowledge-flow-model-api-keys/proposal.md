## Why

Knowledge Flow currently uses `OPENAI_API_KEY` for its OpenAI-compatible chat, vision, embedding, and remote OCR calls. The newly merged remote reranker requires a separately named environment variable in model YAML. Operators cannot consistently assign separate credentials to these uses within one deployment or rely on one fallback key.

## What Changes

- Add optional `KNOWLEDGE_FLOW_CHAT_API_KEY`, `KNOWLEDGE_FLOW_VISION_API_KEY`, `KNOWLEDGE_FLOW_EMBEDDINGS_API_KEY`, `KNOWLEDGE_FLOW_OCR_API_KEY`, and `KNOWLEDGE_FLOW_RERANKER_API_KEY` environment variables for Knowledge Flow's corresponding model uses.
- For each OpenAI-compatible use, prefer its nonblank dedicated key and fall back to `OPENAI_API_KEY` when the dedicated key is absent or blank. Fail clearly when neither is available.
- Apply the same selection to remote OCR, which currently reads `OPENAI_API_KEY` separately from the shared model factory.
- Apply the same dedicated-key and `OPENAI_API_KEY` fallback to the remote reranker, removing its `settings.api_key_env` setting.
- Document the variables for local `.env` and Helm `dotenv` deployments and verify that API and worker processes receive the intended credentials.

## Capabilities

### Modified Capabilities

- `knowledge-flow-model-configuration`: Extend credential selection to the merged remote reranker. The existing `model-routing` specification governs Fred agent pod catalogs, which are outside this change.

## Impact

Knowledge Flow's model construction, remote OCR, and remote reranker paths, the shared `fred-core` model factory's OpenAI-compatible credential injection, focused offline tests, Knowledge Flow configuration documentation, generated configuration schemas, and Helm deployment examples. No database migration or Fred agent catalog change is planned. Tracking: [#3559](https://github.com/ThalesGroup/fred/issues/3559).

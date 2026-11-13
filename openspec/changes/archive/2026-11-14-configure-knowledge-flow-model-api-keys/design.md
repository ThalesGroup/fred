## Context

See `proposal.md` for the motivation and `specs/knowledge-flow-model-configuration/spec.md` for behavior. Knowledge Flow configures `chat_model`, `embedding_model`, optional `vision_model`, and optional `ocr_model` independently. Its chat, vision, and embedding clients use the shared `fred_core.model.factory`; remote OCR reads `OPENAI_API_KEY` directly. The shared factory currently checks `OPENAI_API_KEY` and lets the OpenAI wrappers read it implicitly. Knowledge Flow also validates the embedding credential during startup. The Helm chart supplies Knowledge Flow's `.env` from its `dotenv` Secret, which the extraction workers mount too.

## Goals / Non-Goals

**Goals:**

- Select a credential by Knowledge Flow model use without changing global process state or putting a secret in model YAML.
- Preserve existing deployments when only `OPENAI_API_KEY` is configured.
- Keep the shared model factory's existing callers and non-OpenAI providers working as before.

**Non-Goals:**

- Fred agent model catalogs, discovery, or platform model bindings.
- New runtime secret storage, per-request credential selection, or live rotation of a pod's environment.
- Changing Azure OpenAI, Azure APIM, Anthropic, or local-provider credential rules.

## Decisions

### Resolve role-specific variables in Knowledge Flow

A small Knowledge Flow credential resolver maps the four configuration roles to `KNOWLEDGE_FLOW_CHAT_API_KEY`, `KNOWLEDGE_FLOW_VISION_API_KEY`, `KNOWLEDGE_FLOW_EMBEDDINGS_API_KEY`, and `KNOWLEDGE_FLOW_OCR_API_KEY`. For an OpenAI-compatible role it reads the dedicated variable, then `OPENAI_API_KEY` if the dedicated value is absent or blank. It raises a role-specific configuration error if neither is nonblank. A dedicated value therefore works even when `OPENAI_API_KEY` is absent. Callers for other providers keep their existing authentication path.

This keeps the names tied to Knowledge Flow's four configured uses. Deriving names from model wire IDs would change credentials on model upgrades and cannot distinguish the same wire ID at different gateways. Adding a credential selector or secret value to `ModelConfiguration.settings` would broaden a shared, loosely typed configuration contract and risk copying secrets into logs or catalog projections.

### Inject the selected key into the existing model clients

Extend the shared factory entry points with an optional explicit OpenAI API key argument. Knowledge Flow supplies its selected value for chat, both vision construction paths, and embeddings; existing callers omit the argument and retain `OPENAI_API_KEY` behavior. The OpenAI-compatible branches pass the selected key explicitly to their SDK wrappers and accept it without requiring a global `OPENAI_API_KEY`. No code temporarily assigns to `os.environ`: overlapping requests can use different keys while retaining the shared HTTP client pools.

Remote OCR is a separate HTTP path selected by its Mistral model name. It uses the same role precedence for `KNOWLEDGE_FLOW_OCR_API_KEY` regardless of the configured provider label, preserving existing OCR selection. Its HTTP client receives the selected key for that OCR invocation.

The remote extractor is not currently called by the standard PDF ingestion pipeline, which continues to use local OCR. This change configures credentials for the extractor's existing invocation path and does not change which OCR engine ingestion selects.

### Preserve startup and deployment behavior

Knowledge Flow's embedding startup check uses the new resolution rule; it does not require `OPENAI_API_KEY` when `KNOWLEDGE_FLOW_EMBEDDINGS_API_KEY` is available. Optional model uses continue to resolve credentials when constructed. Add the four optional names to the Knowledge Flow Helm `dotenv` examples and the local configuration guide. The current chart mounts the same Knowledge Flow Secret into API and extraction workers, so no separate worker secret source is needed.

## Risks / Trade-offs

- A missing dedicated variable intentionally falls back to `OPENAI_API_KEY`, which can select a different account than the operator expected. Document the precedence and verify it in tests; this is the requested compatibility behavior.
- Environment-backed keys are fixed for a running pod, and the embedding client is cached. Rotation requires restarting affected API and worker pods, as it does today.
- Changing a shared factory affects other callers. Keep its new argument optional and test both explicit and legacy paths, including concurrent client construction and non-OpenAI providers.

## Migration Plan

Existing deployments need no configuration change. Operators may populate any dedicated variable in Knowledge Flow's local `.env` or deployed environment, including the Helm `dotenv` Secret, and restart affected pods. Leaving or clearing a dedicated variable restores `OPENAI_API_KEY` selection. Reverting the code restores the prior single-key behavior without a data migration.

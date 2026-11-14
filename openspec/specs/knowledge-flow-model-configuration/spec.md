# Knowledge Flow Model Configuration Specification

## Purpose

Defines how Knowledge Flow selects environment-provided credentials for its configured external models without coupling independent model uses to one API key.

## Requirements

### Requirement: Knowledge Flow selects an API key for each external model use

Knowledge Flow SHALL use `KNOWLEDGE_FLOW_CHAT_API_KEY` for its chat model, `KNOWLEDGE_FLOW_VISION_API_KEY` for its vision model, `KNOWLEDGE_FLOW_EMBEDDINGS_API_KEY` for its embedding model, `KNOWLEDGE_FLOW_OCR_API_KEY` for its remote OCR model, and `KNOWLEDGE_FLOW_RERANKER_API_KEY` for its remote reranker when the corresponding variable contains a nonblank value. For each configured OpenAI-compatible chat, vision, or embedding use and the remote OCR and reranker uses, an absent or blank dedicated variable SHALL cause Knowledge Flow to use `OPENAI_API_KEY`. If no applicable key is available, Knowledge Flow SHALL fail that use with a credential configuration error before sending a request. A key selected for one use SHALL NOT be substituted for another use. Existing credential behavior for other chat, vision, and embedding providers SHALL remain unchanged.

#### Scenario: Four distinct keys

- **GIVEN** the chat, vision, embeddings, and remote OCR uses are configured with nonblank dedicated variables
- **WHEN** Knowledge Flow constructs or invokes those models
- **THEN** each use authenticates with its corresponding key

#### Scenario: Five distinct keys

- **GIVEN** the five external model uses are configured with nonblank dedicated variables
- **WHEN** Knowledge Flow constructs or invokes those models
- **THEN** each use authenticates with its corresponding key

#### Scenario: Legacy key fallback

- **GIVEN** `OPENAI_API_KEY` is nonblank and one or more dedicated variables are absent or blank
- **WHEN** Knowledge Flow constructs or invokes the corresponding external model uses
- **THEN** those uses authenticate with `OPENAI_API_KEY`, while uses with dedicated keys retain their own keys

#### Scenario: No available key

- **GIVEN** a configured external model use has neither a nonblank dedicated key nor a nonblank `OPENAI_API_KEY`
- **WHEN** Knowledge Flow prepares that use
- **THEN** it reports a credential configuration error before contacting the model endpoint

#### Scenario: Another provider

- **GIVEN** a configured model uses a provider other than `openai`
- **WHEN** Knowledge Flow constructs the model
- **THEN** that provider retains its existing credential rules

#### Scenario: Explicit reranker variable

- **GIVEN** the remote reranker configures the removed `settings.api_key_env` field
- **WHEN** Knowledge Flow validates the model
- **THEN** it rejects the unknown setting

#### Scenario: Missing explicit reranker variable

- **GIVEN** `KNOWLEDGE_FLOW_RERANKER_API_KEY` is absent or blank
- **WHEN** Knowledge Flow validates the model or sends a reranking request
- **THEN** it uses `OPENAI_API_KEY` if nonblank

#### Scenario: Local reranker

- **GIVEN** no remote `reranker_model` is configured
- **WHEN** Knowledge Flow uses its local CrossEncoder
- **THEN** no reranker API key is required

### Requirement: Model credentials remain isolated across concurrent uses and processes

Knowledge Flow SHALL use the selected credential for the corresponding model client without changing process-wide environment variables during requests. Credential values SHALL NOT appear in model YAML configuration, public responses, or logs. The same environment-variable selection SHALL apply in Knowledge Flow API and worker processes that perform the corresponding model use.

#### Scenario: Concurrent uses

- **GIVEN** chat and vision use different dedicated keys in the same process
- **WHEN** their requests overlap
- **THEN** each request authenticates with its own key and the process environment remains unchanged

#### Scenario: Worker execution

- **GIVEN** a worker processes a document using embeddings or invokes the remote OCR extractor
- **WHEN** the configured model use is constructed in that worker
- **THEN** it follows the same dedicated-key and fallback rules as the API process

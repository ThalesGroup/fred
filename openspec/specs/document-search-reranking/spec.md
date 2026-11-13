# Document Search Reranking Specification

## Purpose

Defines how Knowledge Flow selects a reranking model and how an agent's document search reorders authorized passages while preserving its configured source scope.

## Requirements

### Requirement: Knowledge Flow selects its reranking model from deployment configuration

Knowledge Flow SHALL accept an optional `reranker_model` in the same provider, name and settings configuration shape as its other models. When absent, reranking SHALL use the image's local CrossEncoder. A configured remote model SHALL be used for all enabled reranking calls; an unavailable or invalid configured model SHALL produce an explicit error instead of silently changing models.

#### Scenario: No remote model configured
- **WHEN** Knowledge Flow receives a reranking request with no `reranker_model` configured
- **THEN** it uses the local CrossEncoder and returns the ranked authorized hits

#### Scenario: Remote model configured
- **WHEN** a valid remote `reranker_model` is configured and a reranking request succeeds
- **THEN** Knowledge Flow uses that model and returns its ranking

#### Scenario: Configured remote model fails
- **WHEN** the configured remote reranker is unreachable or returns an invalid result
- **THEN** Knowledge Flow returns a distinguishable reranker failure without returning a local reranking result

### Requirement: Agent document search has a default-on reranking control

The agent's advanced document access settings SHALL offer a boolean reranking control that defaults to on. Existing agent configurations without the field SHALL also read as on. Turning it off SHALL leave the search scope intact and return retrieval-ranked results without invoking a reranker.

#### Scenario: Newly configured agent
- **WHEN** a user adds document access to an agent without changing advanced settings
- **THEN** reranking is on for that agent's RAG searches

#### Scenario: Existing configuration without reranking field
- **WHEN** an existing agent configuration omits the reranking field
- **THEN** its next document search enables reranking

#### Scenario: User disables reranking
- **WHEN** a user turns off reranking in advanced agent settings and saves the agent
- **THEN** its document search returns retrieval-ranked results and does not call a reranker

### Requirement: Reranking occurs inside authorized RAG search

Enabled reranking SHALL reorder only a bounded pool of hits that passed the existing document and attachment visibility checks. It SHALL return at most the requested count, preserve each hit's identity, content, metadata and retrieval score, and preserve the search's source scope and attachment inclusion policy. Reranking SHALL NOT be available as an independent agent tool.

#### Scenario: Inaccessible hit in retrieval candidates
- **WHEN** retrieval returns both visible and inaccessible candidates
- **THEN** only visible candidates may be sent to a reranker or returned to the agent

#### Scenario: Mixed attachment and corpus scope
- **WHEN** an agent searches attachments and corpus together with reranking enabled
- **THEN** the result stays within both authorized scopes and retains the existing attachment inclusion policy

#### Scenario: No authorized hits
- **WHEN** a search produces no visible hits
- **THEN** no reranker is invoked and an empty result is returned

#### Scenario: Bounded result
- **WHEN** enabled reranking receives more candidates than the requested result count
- **THEN** it ranks a finite capped candidate pool and returns no more than the requested count

### Requirement: Existing reranking consumers remain compatible

Knowledge Flow SHALL keep its authenticated direct reranking endpoint and targeted similarity search behavior available. Both SHALL use the configured remote reranker when present and the local CrossEncoder otherwise; their authorization and result contracts SHALL remain valid. Reranking latency and outcome SHALL remain observable without logging passage content or credentials.

#### Scenario: Direct reranking caller
- **WHEN** an authorized caller uses the existing direct reranking endpoint
- **THEN** it receives ranked hits in its existing response shape

#### Scenario: Large direct reranking request
- **WHEN** an authorized direct REST caller sends more than 100 hits
- **THEN** Knowledge Flow ranks them in bounded model batches and preserves global score order without exposing the endpoint as an agent tool

#### Scenario: Targeted similarity caller
- **WHEN** a targeted similarity request has reranking enabled
- **THEN** it uses the same configured model selection while retaining its target restriction and result limit

#### Scenario: Operator inspects reranking telemetry
- **WHEN** local or remote reranking completes or fails
- **THEN** latency and outcome are recorded without passage text or credentials
